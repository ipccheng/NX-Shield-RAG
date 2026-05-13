#!/usr/bin/env python3
from __future__ import annotations
"""
nutanix_rag_search.py — RAG query engine for Nutanix knowledge base.
Flow: classify → Vector (curl embed) + FTS → RRF → Cross-Encoder (jina-reranker-v3) → score_multiplier() → Top 5
"""
import sys
import re
import json
import os
import subprocess
from pathlib import Path
from config import DB_PATH, JINA_API_KEY, JINA_EMBED_URL, JINA_RERANK_URL, DEEPSEEK_API_KEY, DEEPSEEK_URL, DEEPSEEK_MODEL, DEEPSEEK_TIMEOUT

# Tagged entity extraction (dynamic query-time)
# Handle both Mac mini (~/.openclaw/workspace/scripts/) and MacBook (~/.openclaw/scripts/)
_TAGGER_PATH = Path(__file__).resolve().parent
# Try workspace-relative first
_alt = _TAGGER_PATH.parent / "rag" / "nutanix" / "pipeline"
if _alt.exists():
    _TAGGER_PATH = _alt
if str(_TAGGER_PATH) not in sys.path:
    sys.path.insert(0, str(_TAGGER_PATH))
from tagger_v3 import extract_ecosystem_entities, extract_mentioned_products

NX_MODEL_RE = re.compile(r'nx-\d{4}[a-z]?(-\w+)?-g10', re.IGNORECASE)

KUZU_DB_PATH = os.path.expanduser(
    os.environ.get("KUZU_DB_PATH", "~/.openclaw/memory/kuzu-pro/nutanix_graph_v3")
)
SEARXNG_URL = os.environ.get(
    "SEARXNG_URL",
    "http://127.0.0.1:8888/search"
)
ALLOWED_DOMAINS_FILE = Path.home() / ".openclaw/workspace/scripts/allowed_domains.json"
RAG_DOCS_DIR = Path.home() / ".openclaw/workspace/rag/nutanix"


def get_graph_entities(query: str) -> dict:
    """Query Kuzu graph DB for entities connected to query terms.
    Returns a dict: entity_name -> list of rel_types.
    These entity names match LanceDB's ecosystem_entities / mentioned_products columns.
    """
    try:
        import kuzu
        db = kuzu.Database(KUZU_DB_PATH)
        conn = kuzu.Connection(db)
        # Combine query terms + tagger entities for broader coverage
        tagged = extract_ecosystem_entities(query) + extract_mentioned_products(query)
        terms = [t.upper() for t in set(query.split()) if len(t) > 2]
        all_terms = list({t.upper() for t in set(terms + [e.upper() for e in tagged])})
        entity_map = {}  # entity_name -> [rel_type, ...]
        for term in all_terms:
            try:
                result = conn.execute(
                    "MATCH (c:Chunk)-[r]->(e:Entity) "
                    "WHERE e.name CONTAINS $term "
                    "RETURN DISTINCT e.name, r.rel_type "
                    "LIMIT 100",
                    parameters={"term": term},
                )
                for row in result.get_all():
                    if row[0]:
                        if row[0] not in entity_map:
                            entity_map[row[0]] = []
                        if row[1] not in entity_map[row[0]]:
                            entity_map[row[0]].append(row[1])
            except Exception:
                continue
        return entity_map
    except Exception:
        return {}


def _call_deepseek(prompt: str) -> str:
    """Call DeepSeek via API. Returns content or empty string on failure."""
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.1,
    }
    curl_cmd = [
        "curl", "-s", "-X", "POST", DEEPSEEK_URL,
        "-H", "Content-Type: application/json",
        "-H", f"Authorization: Bearer {DEEPSEEK_API_KEY}",
        "-d", json.dumps(payload),
        "--max-time", str(DEEPSEEK_TIMEOUT),
    ]
    try:
        r = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=DEEPSEEK_TIMEOUT + 2)
        if r.returncode != 0:
            return ""
        d = json.loads(r.stdout)
        return d.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception:
        return ""


def _parse_gemma_topics(raw: str, valid_topics: list) -> list:
    """
    Parse Gemma's output into a list of valid topic strings.
    Handles: single topic, comma-separated, bullet points, numbered list.
    Skips any hallucinated topics not in valid_topics.
    """
    if not raw:
        return []
    # Remove common prefixes
    text = re.sub(r'^[\-\*\d.\s]+', '', raw, flags=re.MULTILINE)
    # Split on common delimiters
    candidates = re.split(r'[,;\n\|]+', text)
    found = []
    for c in candidates:
        c = c.strip().strip('"' ).strip("'")
        if not c:
            continue
        # Normalize: uppercase and replace spaces underscores/hyphens
        normalized = c.upper().replace(' ', '_').replace('-', '_')
        if normalized in valid_topics:
            found.append(normalized)
        # Also try exact match case-insensitive
        for t in valid_topics:
            if t.lower() == c.lower() or t.lower().replace('_', ' ') == c.lower():
                if t not in found:
                    found.append(t)
                break
    return found


def _deepseek_classify(query: str, valid_topics: list) -> list:
    """
    Classify query into Nutanix topics using DeepSeek.
    Falls back to empty list on any error — caller should use keyword fallback.
    """
    topics_str = ", ".join(sorted(valid_topics))
    prompt = (
        f"You are a Nutanix technical support classifier. "
        f"Given the user query below, pick the 1-3 best matching topics from the list. "
        f"Reply with ONLY topic names separated by commas, nothing else.\n\n"
        f"Query: {query}\n"
        f"Topics: {topics_str}"
    )
    raw = _call_deepseek(prompt)
    return _parse_gemma_topics(raw, valid_topics)


# ── Jina API helpers (curl subprocess — works around Python 3.14 SSL) ────────────

def jina_embed(query: str, model: str = "jina-embeddings-v5-text-small"):
    r = subprocess.run(
        ["curl", "--max-time", "15", "-s", "-X", "POST", JINA_EMBED_URL,
         "-H", f"Authorization: Bearer {JINA_API_KEY}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"model": model, "input": query})],
        capture_output=True, text=True)
    d = json.loads(r.stdout)
    return d["data"][0]["embedding"]


def jina_rerank(query: str, docs: list, top_n: int = 30) -> list:
    r = subprocess.run(
        ["curl", "--max-time", "15", "-s", "-X", "POST", JINA_RERANK_URL,
         "-H", f"Authorization: Bearer {JINA_API_KEY}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"model": "jina-reranker-v3", "query": query,
                           "documents": [d[:8000] for d in docs], "top_n": top_n})],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        return d.get("results", [])
    except Exception:
        return []


# ── Prompt Injection Guard (Tripwire) ──────────────────────────────────────────

try:
    from llm_guard.input_scanners import PromptInjection
    _guard_ml_available = True
except ImportError:
    _guard_ml_available = False

_GUARD_SCANNER = None
_GUARD_BLOCKED = "Query blocked: safety check failed. Please rephrase your question."
_GUARD_AUDIT_LOG = Path.home() / ".openclaw" / "workspace" / "rag" / "guard_audit.log"


def _get_guard_scanner():
    global _GUARD_SCANNER
    if _GUARD_SCANNER is None:
        _GUARD_SCANNER = PromptInjection()
    return _GUARD_SCANNER


# Patterns — TIER1 (strong injection, weight=3), TIER2 (moderate, weight=2), TIER3 (false-positive risk, weight=1)
_T1_PATTERNS = [
    (re.compile(r'\bDAN\b', re.I), 3, 'DAN'),
    (re.compile(r'\bjailbreak\b', re.I), 3, 'jailbreak'),
    (re.compile(r'ignore\s+all\s+previous\s+(instructions|commands)', re.I), 3, 'ignore_prev'),
    (re.compile(r'reveal\s+(your\s+)?(system\s+)?(instructions|prompt)', re.I), 3, 'reveal_sys'),
    (re.compile(r'(you\s+are\s+now|act\s+as|pretend\s+you\s+are)\s+DAN', re.I), 3, 'you_are_now_DAN'),
]
_T2_PATTERNS = [
    (re.compile(r'disregard\s+(all\s+)?(previous|your\s+)?(instructions|rules)?$', re.I), 2, 'disregard_rules'),
    (re.compile(r'forget\s+(everything|all\s+instructions|your\s+rules)', re.I), 2, 'forget_rules'),
    (re.compile(r'override\s+(safety|content\s+policy)', re.I), 2, 'override_safety'),
    (re.compile(r'(system|prompt)\s+leak', re.I), 2, 'prompt_leak'),
]
_T3_PATTERNS = [
    (re.compile(r'ignore\s+\w+', re.I), 1, 'ignore_phrase'),
    (re.compile(r'disregard\s+\w+', re.I), 1, 'disregard_phrase'),
    (re.compile(r'forget\s+\w+', re.I), 1, 'forget_phrase'),
    (re.compile(r'previous\s+\w+', re.I), 1, 'previous_phrase'),
]
_ALL_PATTERNS = (
    [(p, w, t, 'T1') for p, w, t in _T1_PATTERNS]
    + [(p, w, t, 'T2') for p, w, t in _T2_PATTERNS]
    + [(p, w, t, 'T3') for p, w, t in _T3_PATTERNS]
)


def check_injection_guard(query: str) -> str | None:
    """
    Weighted regex tripwire for prompt injection detection.

    Score 0-1  🟢  Proceed — clean
    Score 2    🟡  Flag for audit — proceed (no block)
    Score 3+   🔴  Hard block

    Matching is non-overlapping: once a higher-weight pattern consumes a character
    range, lower-weight patterns cannot also fire on those same characters.
    This prevents double-counting where the same phrase triggers multiple patterns.

    llm-guard ML scanner: available if installed and dependencies met,
    otherwise falls back to regex-only (fail-open).

    Score 2 triggers are logged to guard_audit.log for human review.
    """
    import datetime

    # Collect all matches with offsets, sorted by weight descending
    matches: list[tuple[int, int, int, str]] = []
    for pat, weight, tag, tier in _ALL_PATTERNS:
        for m in pat.finditer(query):
            matches.append((m.start(), m.end(), weight, tag))
    if not matches:
        return None
    matches.sort(key=lambda x: -x[2])  # highest weight first

    # Non-overlapping: consume character ranges in weight order
    consumed: set[int] = set()
    total_score = 0
    matched_info: list[tuple[int, str]] = []
    for start, end, weight, tag in matches:
        chars = set(range(start, end))
        if not chars & consumed:  # no overlap with already-consumed
            consumed |= chars
            total_score += weight
            matched_info.append((weight, tag))

    # 🟢 Score 0-1: clean, proceed
    if total_score <= 1:
        return None

    # 🟡 Score 2: flag for audit, proceed (do not block normal conversation)
    if total_score == 2:
        try:
            _GUARD_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(_GUARD_AUDIT_LOG, "a") as f:
                f.write(f"[{datetime.now().isoformat()}] SCORE=2 | {query[:200]} | {matched_info}\n")
        except Exception:
            pass  # Non-blocking — never fail a query due to audit
        return None

    # 🔴 Score 3+: hard block
    print(f"[GUARD] Score={total_score} BLOCKED: {matched_info}", file=sys.stderr)
    return _GUARD_BLOCKED


# ── Security Identity ──────────────────────────────────────────────────────
# NX_AGENT_IDENTITY env var controls the security boundary.
# "nx_shield" → hard-filter to access_level='public' (everything else blocked)
# "sam" (or unset) → full access
NX_AGENT_IDENTITY = os.environ.get("NX_AGENT_IDENTITY", "sam").strip().lower()

# ── Topic-driven pre-filter map ────────────────────────────────────────────
# Maps topic → optional LanceDB .where() filters pushed down before search.
# Filters ONLY on the verified tagger_v3.py taxonomy.
# ── KB number map (for score_multiplier boost on authoritative results) ─────
_KB_MAP = {
    "STORAGE_FORMULA": "KB-000001557",
    "NCC_HEALTH":      "KB-000002469",
    "AHV_NETWORK":     "KB-000002090",
    "AHV_MEMORY":      "KB-000002456",
}

# ── Config ───────────────────────────────────────────────────────────────────────

# Topic-level weight applied at two stages:
#   Stage 1 (Pre-CE): boosts RRF score → affects which docs survive into Top-30 for CE
#   Stage 2 (Post-CE): applied to CE rerank_score → breaks ties at final output
TOPIC_WEIGHTS = {
    "STORAGE_FORMULA":   1.25,   # authoritative formula doc — high priority
    "ERASURE_CODING":    1.15,
    "PC_SCALE_OUT":      1.15,
    "CLUSTER_SIZING":    1.20,   # very common, high Slack volume
    "NCC_HEALTH":        1.15,   # diagnostic权威
    "NKE_COMPAT":        1.10,
    "LICENSING":         1.10,
    "DATA_PROTECTION":    1.15,
    "VEEAM_DATAPROTECTION": 1.15,   # Veeam backup/restore for Nutanix AHV
    "MOVE_MIGRATION":    1.20,   # high Slack volume
    "AHV_NETWORK":       1.15,
    "AHV_MEMORY":        1.15,
    "NETWORKING":        1.10,
    "STORAGE_NVME":      1.15,
    "STORAGE_EFFICIENCY":1.15,
    "MIXED_CLUSTER":     1.10,
    "FOUNDATION_IMAGING":1.10,
    "AHV_HBA":           1.10,
    "AHV_UEFI":          1.10,
    "LCM_FIRMWARE":      1.10,
    "NKP_CERTIFICATE":   1.10,
    "NKP_HELM":          1.10,
    "FLOW_SECURITY":     1.15,
    "FLOW_QUARANTINE":   1.15,
    "FILES_REPLICATION": 1.15,
    "OBJECTS_S3":        1.15,
    "GPU_VGPU":          1.20,   # emerging high-value topic
    "STRETCH_CLUSTER":   1.15,
    "NDB_DATABASE":      1.20,   # high Slack volume + specialized
    "NETWORK_ISOLATION": 1.10,
    "PC_FAILOVER":       1.15,
    "PRISM_ALERTING":    1.10,
    "PRISM_LACP":        1.10,
    "SECURITY_ENCRYPTION":1.10,
    "CALM_BLUEPRINT":    1.10,
    "HARDWARE_SPEC":     1.20,   # model-specific = authoritative
    "POWERFLEX":         1.20,   # Dell PowerFlex XC — distinct from PowerEdge
    "POWEREDGE":         1.15,   # Dell PowerEdge — OEM server compatibility
    "NIKE_SERVICE":      1.25,   # new topic for Nike metadata store / ChakrDB service
    "EXTERNAL_STORAGE":  1.25,   # Pure Storage FlashArray / Everpure external block storage
}

# Maps classifier topic → subcategory value for soft boosting
# When a doc's subcategory matches the target, +25% boost is applied in score_multiplier()
SUBJECT_SUBCAT_MAP = {
    "NCC_HEALTH":         "NCC",
    "AHV_NETWORK":        "AHV",
    "AHV_MEMORY":        "AHV",
    "CLUSTER_SIZING":     "AHV",   # hardware specs often tagged AHV
    "HARDWARE_SPEC":      "AHV",
    "FOUNDATION_IMAGING": "Foundation",
    "EXTERNAL_STORAGE":   "AHV",   # external storage whitepaper lives under AHV docs
    "CALM_BLUEPRINT":     "Calm",
    "PRISM_ALERTING":     "Prism",
    "PRISM_LACP":         "Prism",
    "NETWORKING":         "Prism",
    "NDB_DATABASE":        "NDB",
    "VEEAM_DATAPROTECTION": "Backup Jobs",
    "FLOW_SECURITY":      "Flow",
    "FLOW_QUARANTINE":    "Flow",
    "LCM_FIRMWARE":       "LCM",
    "NETWORK_ISOLATION":  "Prism",  # networking docs often tagged Prism
    "FILES_REPLICATION":  "Files",
    "OBJECTS_S3":         "Objects",
    "STRETCH_CLUSTER":    "AHV",
    "GPU_VGPU":           "AHV",
    "NKP_CERTIFICATE":    "NKP",
    "NKP_HELM":           "NKP",
    "NKE_COMPAT":         "NKE",
    "NIKE_SERVICE":      "Storage",
    "POWERFLEX":         "HARDWARE_SPEC",   # Dell PowerFlex specs → HARDWARE_SPEC subcategory
    "POWEREDGE":         "general",         # PowerEdge compat matrix → general
}

# Subcategory → products mapping (fallback when products field is empty).
# Used at query time to fill in missing product metadata for scoring.
SUBCATEGORY_PRODUCTS_MAP = {
    "Prism":      ["Prism Central"],
    "Prism Central": ["Prism Central"],
    "AHV":        ["AHV"],
    "AOS":        ["AOS"],
    "Calm":       ["Calm"],
    "NDB":        ["Nutanix Database Service"],
    "NKE":        ["NKE"],             # Nutanix Kubernetes Engine (active)
    "Karbon":     ["NKE"],             # Karbon = old name for NKE (obsolete)
    "NKP":        ["NKP"],             # Nutanix Kubernetes Platform (active)
    "Kommander":  ["NKP"],             # Kommander = old name for NKP (obsolete)
    "D2IQ":       ["NKP"],             # D2IQ = old name for NKP (obsolete)
    "NCC":        ["NCC"],
    "Flow":       ["Flow"],
    "LCM":        ["LCM"],
    "Files":      ["Files"],
    "Objects":    ["Objects"],
    "Foundation": ["Foundation"],
    "NCI":        ["NCI"],
    "Volumes":    ["Volumes"],
    "Move":       ["Move"],
    "Era":        ["Era"],
    # ── Additional subcategories found in DB ──
    "KB Article": ["AOS"],
    "NC2":        ["NC2"],
    "Support Services": ["Support"],
    "Infrastructure|Management": ["Prism"],
    "Kubernetes|Platform": ["NKP"],
    "Disaster-Recovery|Business-Continuity": ["AOS"],
    "Self-Service|Cloud-Management": ["Calm"],
    "processor|hypervisor": ["AHV"],
    "AI|LLM":     ["AOS"],
    "HPE":        ["HPE"],
    "Dell":       ["Dell"],
    "hardware|platform": ["HPE", "Dell"],
    "Restore":   ["AOS"],
    "Backup Jobs": ["AOS"],
    "Backup Workers": ["AOS"],
    "NCM":       ["NCM"],
    "v4 API":     ["AOS"],
    "architecture": ["AOS"],
    "Citrix":     ["VMware"],
    "X-Ray":     ["AOS"],
}

# Maps classifier topic → products values for soft boosting.
# When a doc's products list intersects with the target topic's products → ×1.3
# Case-insensitive matching (both sides lowercased) for enterprise metadata resilience.
SUBJECT_PRODUCTS_MAP = {
    # ── Storage ──
    "STORAGE_FORMULA":    ["AOS", "Volumes"],
    "ERASURE_CODING":     ["AOS"],
    "STORAGE_NVME":       ["AOS"],
    "STORAGE_EFFICIENCY": ["AOS"],
    # ── Compute / AHV ──
    "CLUSTER_SIZING":     ["AHV", "AOS"],
    "AHV_NETWORK":        ["AHV"],
    "AHV_MEMORY":         ["AHV"],
    "AHV_HBA":            ["AHV", "AOS"],
    "AHV_UEFI":           ["AHV"],
    "GPU_VGPU":           ["AHV", "NCI"],
    "STRETCH_CLUSTER":    ["AOS", "AHV"],
    # ── Prism Central ──
    "PRISM_ALERTING":     ["Prism"],
    "PRISM_LACP":         ["Prism"],
    "NETWORKING":         ["Prism"],
    "NETWORK_ISOLATION":   ["Prism"],
    "PC_SCALE_OUT":       ["Prism"],
    "PC_FAILOVER":        ["Prism"],
    # ── Calm / Self-Service ──
    "CALM_BLUEPRINT":     ["Calm"],
    # ── NDB / Database ──
    "NDB_DATABASE":       ["NDB", "Era"],
    # ── Flow ──
    "FLOW_SECURITY":      ["Flow"],
    "FLOW_QUARANTINE":     ["Flow"],
    # ── LCM / Foundation ──
    "LCM_FIRMWARE":       ["LCM"],
    "FOUNDATION_IMAGING": ["Foundation"],
    # ── NKP / Karbon ──
    "NKP_CERTIFICATE":    ["NKP"],
    "NKP_HELM":           ["NKP"],
    "NKE_COMPAT":         ["NKE"],
    # ── Nike / ChakrDB ──
    "NIKE_SERVICE":      ["AOS", "Storage", "Prism"],
    # ── Storage primitives ──
    "FILES_REPLICATION":  ["Files"],
    "OBJECTS_S3":         ["Objects"],
    # ── NCC ──
    "NCC_HEALTH":         ["NCC"],
    # ── Cross-product ──
    "LICENSING":          ["AOS"],
    "DATA_PROTECTION":      ["AOS", "AHV"],
    "VEEAM_DATAPROTECTION": ["Veeam", "AHV"],
    "MOVE_MIGRATION":     ["Move"],
    "SECURITY_ENCRYPTION": ["NCC", "NCM"],
    "HARDWARE_SPEC":      ["AOS", "AHV", "HPE"],
    "POWERFLEX":         ["AOS", "AHV", "PowerFlex", "Dell"],
    "POWEREDGE":         ["AOS", "AHV", "PowerEdge", "Dell"],
}

# ── Intent filter map ────────────────────────────────────────────────────────
# Replaces hardcoded SPECIFIC_SEARCHES strings with intent buckets.
# The vector search uses the RAW user query (embedding handles semantics).
# Filters narrow the candidate pool by doc_type / content_type / metadata.
INTENT_FILTER_MAP = {
    "COMPETITIVE":      {"doc_type": ["battlecard", "competitive_intel", "official_doc"]},
    "TROUBLESHOOTING":  {"content_types": ["troubleshooting", "faq"]},
    "API_DEV":          {"doc_type": ["api_spec", "official_doc", "code_repo"]},
    "HARDWARE":         {"doc_type": ["reference", "official_doc"]},
    "ENABLEMENT":       {"doc_type": ["enablement", "tech_blog"]},
}

# Keyword patterns for intent detection (no Gemma call needed for routing)
_INTENT_PATTERNS = [
    (re.compile(r'\b(vs|versus|compare|vs\.|better|compete|competition|cheat sheet|battlecard)\b', re.I), "COMPETITIVE"),
    (re.compile(r'\b(errors?|fai(lure|l|ls|led)|issues?|troubleshoot|fix(es)?|debug|problems?|crash(es)?|bugs?|warning(s)?|alert(s)?|broken|stuck|down|timeout)\b', re.I), "TROUBLESHOOTING"),
    (re.compile(r'\b(API|SDK|REST|endpoint|developer|code|github|terraform|ansible|python)\b', re.I), "API_DEV"),
    (re.compile(r'\b(spec|model|NX-\d+|G10|Gen\d+|specs|hardware|dimension|form factor)\b', re.I), "HARDWARE"),
]


def _detect_intents(query: str) -> list:
    """Detect intent buckets from query keywords + ecosystem entities."""
    q = query.lower()
    intents = []
    for pattern, intent in _INTENT_PATTERNS:
        if pattern.search(q):
            intents.append(intent)
    # If query mentions a competitor, always add COMPETITIVE intent
    competitors = extract_ecosystem_entities(query)
    if competitors and "COMPETITIVE" not in intents:
        intents.append("COMPETITIVE")
    return intents


def build_search_filters(user_query: str, intents: list, identity: str) -> tuple:
    """
    Build LanceDB .where() filter conditions dynamically from query + intent + identity.
    Returns (filter_conditions_list, has_non_security_filters).
    """
    filter_conditions = []

    # 1. HARD SECURITY BOUNDARY — overrules everything
    if identity == "nx_shield":
        filter_conditions.append("access_level = 'public'")

    # 2. Dynamic ecosystem entity extraction (competitors, partners)
    competitors = extract_ecosystem_entities(user_query)
    if competitors:
        comp_list = ', '.join(f"'{c}'" for c in competitors)
        filter_conditions.append(f"array_has_any(ecosystem_entities, [{comp_list}])")

    # 3. Dynamic product mention extraction
    products = extract_mentioned_products(user_query)
    if products:
        prod_list = ', '.join(f"'{p}'" for p in products)
        filter_conditions.append(f"array_has_any(mentioned_products, [{prod_list}])")

    # 4. Intent-based doc_type / content_type filters
    has_intent_filters = False
    seen_doc_type = any("doc_type" in fc for fc in filter_conditions)
    seen_content_type = any("content_types" in fc for fc in filter_conditions)
    for intent in intents:
        intent_filter = INTENT_FILTER_MAP.get(intent, {})
        if "doc_type" in intent_filter and not seen_doc_type:
            dt_list = ', '.join(f"'{d}'" for d in intent_filter["doc_type"])
            filter_conditions.append(f"doc_type IN ({dt_list})")
            seen_doc_type = True
            has_intent_filters = True
        if "content_types" in intent_filter and not seen_content_type:
            ct_list = ', '.join(f"'{c}'" for c in intent_filter["content_types"])
            filter_conditions.append(f"array_has_any(content_types, [{ct_list}])")
            seen_content_type = True
            has_intent_filters = True

    has_non_security = (len(competitors) > 0 or len(products) > 0 or has_intent_filters)
    return filter_conditions, has_non_security

QUERY_CLASSIFIERS = {
    # ── Storage ────────────────────────────────────────────────────────────────
    "storage": "STORAGE_FORMULA", "usable": "STORAGE_FORMULA", "effective": "STORAGE_FORMULA",
    # Specific Nutanix Volumes (iSCSI block storage) product terms
    "volume group": "STORAGE_FORMULA", "volume groups": "STORAGE_FORMULA",
    "iSCSI": "STORAGE_FORMULA", "iscsi": "STORAGE_FORMULA",
    "nutanix volumes": "STORAGE_FORMULA", "nutanix volume": "STORAGE_FORMULA",
    "RF2": "STORAGE_FORMULA", "RF3": "STORAGE_FORMULA", "N+1": "STORAGE_FORMULA", "N+2": "STORAGE_FORMULA", "utilization": "STORAGE_FORMULA",
    "storage capacity": "STORAGE_FORMULA", "capacity planning": "STORAGE_FORMULA", "max storage": "STORAGE_FORMULA",
    "erasure coding": "ERASURE_CODING", "erasure-coding": "ERASURE_CODING", "EC-X": "ERASURE_CODING", "ec-x": "ERASURE_CODING",
    "deduplication": "ERASURE_CODING", "dedup": "ERASURE_CODING",
    "compression": "STORAGE_EFFICIENCY", "compression ratio": "STORAGE_EFFICIENCY",
    "storage efficiency": "STORAGE_EFFICIENCY", "data reduction": "STORAGE_EFFICIENCY", "efficiency ratio": "STORAGE_EFFICIENCY",
    # ── Cluster & Compute Sizing ──────────────────────────────────────────────
    "prism central": "PC_SCALE_OUT", "PC ": "PC_SCALE_OUT", "scale out": "PC_SCALE_OUT", "scale-out": "PC_SCALE_OUT",
    "expand PC": "PC_SCALE_OUT", "HA": "PC_SCALE_OUT", "resilien": "PC_SCALE_OUT", "size L": "PC_SCALE_OUT", "size XL": "PC_SCALE_OUT",
    "pc sizing": "CLUSTER_SIZING", "PC sizing": "CLUSTER_SIZING", "PC small": "CLUSTER_SIZING", "PC medium": "CLUSTER_SIZING", "PC large": "CLUSTER_SIZING",
    "vcpu": "CLUSTER_SIZING", "pcpu": "CLUSTER_SIZING", " cpu core": "CLUSTER_SIZING", "cores per node": "CLUSTER_SIZING",
    "overcommit": "CLUSTER_SIZING", "overcommit ratio": "CLUSTER_SIZING", "sizer": "CLUSTER_SIZING",
    "cluster sizing": "CLUSTER_SIZING", "node sizing": "CLUSTER_SIZING", "applied weight": "CLUSTER_SIZING",
    # ── Health & Diagnostics ─────────────────────────────────────────────────
    "NCC": "NCC_HEALTH", "ncc": "NCC_HEALTH", "health check": "NCC_HEALTH", "sysstats": "NCC_HEALTH", "ncc-health": "NCC_HEALTH",
    "check-node-health": "NCC_HEALTH", "ncc show": "NCC_HEALTH", "ncc-health check": "NCC_HEALTH",
    # ── Licensing ─────────────────────────────────────────────────────────────
    "NKE": "NKE_COMPAT", "Karbon": "NKE_COMPAT", "NKE PC": "NKE_COMPAT", "NKE compatibility": "NKE_COMPAT",
    "license": "LICENSING", "licensing": "LICENSING", "elastic": "LICENSING", "Buffalo": "LICENSING",
    "license expiry": "LICENSING", "license enforcement": "LICENSING",
    # ── Data Protection ───────────────────────────────────────────────────────
    "snapshot": "DATA_PROTECTION", "protection domain": "DATA_PROTECTION", "protection_domain": "DATA_PROTECTION",
    "replication": "DATA_PROTECTION", "DR ": "DATA_PROTECTION", "CCLM": "DATA_PROTECTION",
    "cross cluster live migration": "DATA_PROTECTION", "metro": "DATA_PROTECTION", "metro availability": "DATA_PROTECTION",
    "nutanix move": "MOVE_MIGRATION", "move vm": "MOVE_MIGRATION", "vm migration": "MOVE_MIGRATION",
    "cross cluster migration": "MOVE_MIGRATION", "l2 migration": "MOVE_MIGRATION", "workload migration": "MOVE_MIGRATION",
    "pc failover": "PC_FAILOVER", "prism central failover": "PC_FAILOVER", "PC ha": "PC_FAILOVER", "PC HA": "PC_FAILOVER",
    "prism central dr": "PC_FAILOVER", "prism central disaster": "PC_FAILOVER",
    # ── Networking ────────────────────────────────────────────────────────────
    "AHV networking": "AHV_NETWORK", "virtual switch": "AHV_NETWORK", "vswitch": "AHV_NETWORK",
    "VLAN": "AHV_NETWORK", "NIC bonding": "AHV_NETWORK", "ethernet": "AHV_NETWORK",
    "link aggregation": "AHV_NETWORK", "LACP": "AHV_NETWORK", "SR-IOV": "AHV_NETWORK", "sriov": "AHV_NETWORK", "network offload": "AHV_NETWORK",
    "BGP": "NETWORKING", "VLAN": "NETWORKING", "LACP": "NETWORKING", "trunk": "NETWORKING", "mellanox": "NETWORKING", "floating IP": "NETWORKING", "DMZ": "NETWORKING",
    "subnet": "NETWORK_ISOLATION", "ipam": "NETWORK_ISOLATION", "dhcp": "NETWORK_ISOLATION", "ip address": "NETWORK_ISOLATION",
    "network isolation": "NETWORK_ISOLATION", "network segmentation": "NETWORK_ISOLATION",
    "stretch cluster": "STRETCH_CLUSTER", "stretched": "STRETCH_CLUSTER", "metro witness": "STRETCH_CLUSTER",
    "witness": "STRETCH_CLUSTER", "cross availability": "STRETCH_CLUSTER", "cross site": "STRETCH_CLUSTER",
    # ── Memory ────────────────────────────────────────────────────────────────
    "AHV memory": "AHV_MEMORY", "FNS memory": "AHV_MEMORY", "memory overcommit": "AHV_MEMORY",
    "overcommit": "AHV_MEMORY", "boot": "AHV_MEMORY", "affinity": "AHV_MEMORY", "anti-affinity": "AHV_MEMORY",
    "CVM memory": "AHV_MEMORY", "cvm memory": "AHV_MEMORY", "memory reservation": "AHV_MEMORY",
    # ── Nike / ChakrDB ──
    "Nike": "NIKE_SERVICE", "ChakrDB": "NIKE_SERVICE", "vnode": "NIKE_SERVICE", "vdisk store": "NIKE_SERVICE",
    "Stargate": "NIKE_SERVICE", "Medusa": "NIKE_SERVICE", "Odin ntnx": "NIKE_SERVICE",
    # ── External Storage (Pure Storage / FlashArray / Everpure) ───────────
    "pure storage": "EXTERNAL_STORAGE", "flasharray": "EXTERNAL_STORAGE",
    "everpure": "EXTERNAL_STORAGE", "external block storage": "EXTERNAL_STORAGE",
    # ── Storage Hardware ─────────────────────────────────────────────────────
    "NVMe": "STORAGE_NVME", "nvme": "STORAGE_NVME", "SSD HDD": "STORAGE_NVME", "mixed cluster": "STORAGE_NVME", "node expand": "STORAGE_NVME",
    "mixed cluster": "MIXED_CLUSTER", "nvme hdd": "MIXED_CLUSTER", "ssd hdd": "MIXED_CLUSTER", "hybrid": "MIXED_CLUSTER",
    "L4": "HARDWARE_SPEC", "A16": "HARDWARE_SPEC", "L40S": "HARDWARE_SPEC", "RTX Pro": "HARDWARE_SPEC",
    # ── Imaging & Firmware ───────────────────────────────────────────────────
    "Foundation": "FOUNDATION_IMAGING", "foundation": "FOUNDATION_IMAGING", "host imaging": "FOUNDATION_IMAGING",
    "IPMI": "FOUNDATION_IMAGING", "ipmi": "FOUNDATION_IMAGING", "BMC": "FOUNDATION_IMAGING", "bmc": "FOUNDATION_IMAGING",
    "Redfish": "FOUNDATION_IMAGING", "redfish": "FOUNDATION_IMAGING", "clusterconfig": "FOUNDATION_IMAGING", "PXE": "FOUNDATION_IMAGING", "ISO boot": "FOUNDATION_IMAGING",
    "foundation error": "FOUNDATION_IMAGING", "foundation timeout": "FOUNDATION_IMAGING",
    "HBA": "AHV_HBA", "hba": "AHV_HBA", "MAC address": "AHV_HBA", "MAC addr": "AHV_HBA",
    "node boot": "AHV_HBA", "host boot": "AHV_HBA", "CVM boot": "AHV_HBA", "CCLM": "AHV_HBA", "cclm": "AHV_HBA",
    "UEFI": "AHV_UEFI", "uefi": "AHV_UEFI", "guest VM": "AHV_UEFI",
    "firmware": "LCM_FIRMWARE", "firmware upgrade": "LCM_FIRMWARE", "BIOS": "LCM_FIRMWARE", "bios upgrade": "LCM_FIRMWARE", "HPE firmware": "LCM_FIRMWARE", "Dell firmware": "LCM_FIRMWARE",
    # ── Kubernetes ──────────────────────────────────────────────────────────
    "kubernetes certificate": "NKP_CERTIFICATE", "kube certificate": "NKP_CERTIFICATE", "certificate error": "NKP_CERTIFICATE",
    "CAPI": "NKP_CERTIFICATE", "capi error": "NKP_CERTIFICATE", "kube-system": "NKP_CERTIFICATE", "k8s cluster": "NKP_CERTIFICATE",
    "helm install": "NKP_HELM", "helm chart": "NKP_HELM", "NKP install": "NKP_HELM", "NKP deploy": "NKP_HELM",
    "kommander": "NKP_HELM", "d2iq": "NKP_HELM",
    # ── Security ─────────────────────────────────────────────────────────────
    "Flow policy": "FLOW_SECURITY", "flow SEP": "FLOW_SECURITY", "security policy": "FLOW_SECURITY", "VM isolation": "FLOW_SECURITY",
    "flow quarantine": "FLOW_QUARANTINE", "quarantine": "FLOW_QUARANTINE", "isolate vm": "FLOW_QUARANTINE", "app policy": "FLOW_QUARANTINE",
    "microsegmentation": "FLOW_QUARANTINE", "app rule": "FLOW_QUARANTINE",
    "SEC dashboard": "SECURITY_ENCRYPTION", "NCM": "SECURITY_ENCRYPTION", "ncm": "SECURITY_ENCRYPTION", "encryption key": "SECURITY_ENCRYPTION",
    # ── Apps & Data ─────────────────────────────────────────────────────────
    "Files tiering": "FILES_REPLICATION", "file tiering": "FILES_REPLICATION", "Files failover": "FILES_REPLICATION",
    "file failover": "FILES_REPLICATION", "Files replication": "FILES_REPLICATION", "share snapshot": "FILES_REPLICATION",
    "Objects S3": "OBJECTS_S3", "S3 bucket": "OBJECTS_S3", "Objects endpoint": "OBJECTS_S3", "bucket MSP": "OBJECTS_S3",
    "Era": "NDB_DATABASE", "era": "NDB_DATABASE", "ERA": "NDB_DATABASE",
    "ndb": "NDB_DATABASE", "era database": "NDB_DATABASE",
    "database service": "NDB_DATABASE", "nutanix database": "NDB_DATABASE", "db provisioning": "NDB_DATABASE",
    "postgres": "NDB_DATABASE", "postgresql": "NDB_DATABASE", "oracle database": "NDB_DATABASE", "sql server": "NDB_DATABASE",
    "database clone": "NDB_DATABASE", "db server": "NDB_DATABASE",
    "era provisioning": "NDB_DATABASE", "era clone": "NDB_DATABASE", "era migration": "NDB_DATABASE",
    "era pitr": "NDB_DATABASE", "era backup": "NDB_DATABASE",
    "database-as-a-service": "NDB_DATABASE", "dbaaas": "NDB_DATABASE",
    "Calm blueprint": "CALM_BLUEPRINT", "blueprint DSL": "CALM_BLUEPRINT", "Calm error": "CALM_BLUEPRINT", "blueprint debugging": "CALM_BLUEPRINT",
    # ── Alerting ─────────────────────────────────────────────────────────────
    "Prism alert": "PRISM_ALERTING", "prism alert": "PRISM_ALERTING", "alert email": "PRISM_ALERTING", "SNMP": "PRISM_ALERTING", "snmp": "PRISM_ALERTING",
    "LACP": "PRISM_LACP", "lacp": "PRISM_LACP", "bridge bonding": "PRISM_LACP", "network bond": "PRISM_LACP", "uplink": "PRISM_LACP",
    # ── Hardware ─────────────────────────────────────────────────────────────
    "NX-8170": "HARDWARE_SPEC", "NX-8150": "HARDWARE_SPEC", "NX-3035": "HARDWARE_SPEC", "NX-3060S": "HARDWARE_SPEC",
    "NX-1175": "HARDWARE_SPEC", "NX-8155AS": "HARDWARE_SPEC",
    "DL380 Gen12": "HARDWARE_SPEC", "DL360 Gen12": "HARDWARE_SPEC", "DL385 Gen12": "HARDWARE_SPEC", "DL380a Gen12": "HARDWARE_SPEC",
    "HPE DL380": "HARDWARE_SPEC", "HPE DL360": "HARDWARE_SPEC", "HPE Gen12": "HARDWARE_SPEC", "ProLiant Gen12": "HARDWARE_SPEC",
    "DL380 12LFF": "HARDWARE_SPEC", "DL380 24 NVMe": "HARDWARE_SPEC", "DL360 10 NVMe": "HARDWARE_SPEC", "DL360 20 NVMe": "HARDWARE_SPEC",
    "system specs": "HARDWARE_SPEC", "system specifications": "HARDWARE_SPEC",
    "hardware spec": "HARDWARE_SPEC", "hardware specifications": "HARDWARE_SPEC",
    "node power": "HARDWARE_SPEC", "BTU": "HARDWARE_SPEC", "power consumption": "HARDWARE_SPEC",
    "memory configuration": "HARDWARE_SPEC", "CPU cores": "HARDWARE_SPEC",
    "Intel Xeon": "HARDWARE_SPEC", "DDR5": "HARDWARE_SPEC", "NVMe": "HARDWARE_SPEC",
    "hybrid storage": "HARDWARE_SPEC", "hybrid": "HARDWARE_SPEC", "2U2N": "HARDWARE_SPEC", "1U1N": "HARDWARE_SPEC",
    "vGPU": "HARDWARE_SPEC", "GPU": "HARDWARE_SPEC",
    # ── Dell PowerFlex XC ─────────────────────────────────────────────────
    "PowerFlex XC": "POWERFLEX", "powerflex xc": "POWERFLEX", "XC670": "POWERFLEX", "XC6715": "POWERFLEX",
    "XC770": "POWERFLEX", "XC7725": "POWERFLEX", "Dell PowerFlex": "POWERFLEX", "powerflex": "POWERFLEX",
    "Dell XC": "POWERFLEX", "NCP PowerFlex": "POWERFLEX",
    # ── Dell PowerEdge ──────────────────────────────────────────────────────
    "PowerEdge R": "POWEREDGE", "poweredge r": "POWEREDGE", "Dell PowerEdge": "POWEREDGE", "PowerEdge C6620": "POWEREDGE",
    "R640": "POWEREDGE", "R740": "POWEREDGE", "R750": "POWEREDGE", "R660": "POWEREDGE", "R760": "POWEREDGE",
    "Dell OEM node": "POWEREDGE", "PowerEdge compatibility": "POWEREDGE",
    # ── Troubleshooting patterns (common phrasing that slips through) ──────────
    # These catch natural-language queries that don't use product jargon
    "why is my cluster": "STORAGE_FORMULA",
    "out of space": "STORAGE_FORMULA", "disk full": "STORAGE_FORMULA", "storage full": "STORAGE_FORMULA",
    "storage latency": "STORAGE_NVME", "slow storage": "STORAGE_NVME", "high disk": "STORAGE_NVME",
    "cluster slow": "CLUSTER_SIZING", "cluster performance": "CLUSTER_SIZING", "performance issue": "CLUSTER_SIZING",
    "VM slow": "AHV_NETWORK", "VM performance": "AHV_NETWORK", "VM latency": "AHV_NETWORK",
    "cannot connect": "NETWORKING", "connectivity issue": "NETWORKING", "cannot ping": "NETWORKING",
    "network issue": "NETWORKING", "network problem": "NETWORKING", "connection refused": "NETWORKING",
    "VM won t start": "AHV_UEFI", "VM failing": "AHV_UEFI", "VM crash": "AHV_UEFI",
    "guest VM": "AHV_UEFI", "VM boot": "AHV_UEFI", "VM not starting": "AHV_UEFI",
    "alert not firing": "PRISM_ALERTING", "alert missing": "PRISM_ALERTING", "alert email": "PRISM_ALERTING",
    "email not sent": "PRISM_ALERTING", "notification": "PRISM_ALERTING",
    "upgrade": "LCM_FIRMWARE", "upgrade failed": "LCM_FIRMWARE", "update": "LCM_FIRMWARE",
    "migration failed": "MOVE_MIGRATION", "migrate VM": "MOVE_MIGRATION",
    "authentication": "SECURITY_ENCRYPTION", "auth": "SECURITY_ENCRYPTION", "login failed": "SECURITY_ENCRYPTION",
    "antivirus": "FILES_REPLICATION", "AV": "FILES_REPLICATION",
    "backup": "DATA_PROTECTION", "restore": "DATA_PROTECTION",
    # ── Veeam / Nutanix AHV Backup ──
    "veeam": "VEEAM_DATAPROTECTION", "veeam backup": "VEEAM_DATAPROTECTION",
    "veeam restore": "VEEAM_DATAPROTECTION", "veeam instant recovery": "VEEAM_DATAPROTECTION",
    "veeam ahv": "VEEAM_DATAPROTECTION", "veeam nutanix": "VEEAM_DATAPROTECTION",
    "Veeam": "VEEAM_DATAPROTECTION", "Veeam Backup": "VEEAM_DATAPROTECTION",
    "veeam plugin": "VEEAM_DATAPROTECTION", "veeam workers": "VEEAM_DATAPROTECTION",
    "veeam backup copy": "VEEAM_DATAPROTECTION", "veeam retention": "VEEAM_DATAPROTECTION",
    "veeam snapshot": "VEEAM_DATAPROTECTION", "veeam chain": "VEEAM_DATAPROTECTION",
    "multi-cluster": "STRETCH_CLUSTER", "stretch": "STRETCH_CLUSTER", "stretched": "STRETCH_CLUSTER",
    "witness": "STRETCH_CLUSTER", "arbitration": "STRETCH_CLUSTER",
    "unauthorized": "SECURITY_ENCRYPTION", "permission denied": "SECURITY_ENCRYPTION",
    "unhealthy": "NCC_HEALTH", "degraded": "NCC_HEALTH", "alarm": "NCC_HEALTH",
    "troubleshoot": "NCC_HEALTH", "diagnostic": "NCC_HEALTH", "debug": "NCC_HEALTH",
    "resize": "CLUSTER_SIZING", "scale up": "CLUSTER_SIZING", "scale down": "CLUSTER_SIZING",
}


def is_blueprint(result: dict) -> bool:
    """True if this result is a GitHub community blueprint (not authoritative Nutanix doc)."""
    src = result.get("source", "")
    return "github/repos/blueprints" in src.lower()


def get_effective_products(result: dict) -> list:
    """
    Return the doc's products list using V3 native Arrow list fields.
    Falls back in order: mentioned_products → primary_product → old products (JSON).
    """
    # V3 native list
    mp = result.get("mentioned_products", [])
    if isinstance(mp, list) and mp:
        return mp
    # V3 primary_product
    pp = result.get("primary_product", "")
    if pp and pp != "General":
        return [pp]
    # Legacy V2 fallback
    raw = result.get("products", "[]")
    try:
        prod_list = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        prod_list = []
    if prod_list:
        return prod_list
    # Fallback via subcategory (V2 compat)
    subcat = result.get("subcategory", "")
    if subcat and subcat != "general":
        mapped = SUBCATEGORY_PRODUCTS_MAP.get(subcat, [])
        if mapped:
            return mapped
    # Fallback via category (V2 compat)
    cat = result.get("category", "")
    if cat:
        cat_products = {
            "Support": ["Support"],
            "enablement": ["AOS"],
            "enablement-essentials": ["AOS"],
            "gts-2026": ["AOS"],
            "nutanix-technical": ["AOS"],
            "xpress-competitive": ["AOS"],
            "solutions": ["AOS"],
            "kb_articles": ["AOS"],
            "nutanix_validated_designs": ["AOS"],
            "compatibility": ["AOS"],
        }
        return cat_products.get(cat, [])
    return []


def classify(query: str) -> list:
    """
    Hybrid topic classification: DeepSeek primary, keyword fallback.
    Topics are used ONLY for post-hoc score_multiplier() boosting (not search routing).

    DeepSeek handles natural-language phrasing that slips past keyword matching.
    Keyword classifier serves as fallback when:
      - DeepSeek is unreachable / times out
      - DeepSeek returns no valid topics
      - DeepSeek output is ambiguous

    Results are merged (union) to avoid false negatives.
    """
    valid_topics = list(TOPIC_WEIGHTS.keys())

    # Primary: DeepSeek semantic classification
    gemma_topics = _deepseek_classify(query, valid_topics)

    # Fallback: keyword classifier (handles Gemma failures gracefully)
    q = query.lower()
    kw_topics = list({t for kw, t in QUERY_CLASSIFIERS.items() if kw.lower() in q})

    if not kw_topics:
        # Only DeepSeek result available
        return gemma_topics
    if not gemma_topics:
        # Only keyword result available
        return kw_topics

    # Both found — merge, preferring DeepSeek's ordering
    # (DeepSeek is better at multi-topic queries; keywords fill gaps)
    merged = gemma_topics.copy()
    for t in kw_topics:
        if t not in merged:
            merged.append(t)
    return merged


# ── Retrieval ─────────────────────────────────────────────────────────────────

def rrf_merge(results_by_method: list, k: int = 60, topic_weight: float = 1.0) -> list:
    """
    RRF merge — returns flat sorted list with rrf_score embedded in each doc.
    topic_weight is applied multiplicatively to all RRF increments for this topic,
    boosting authoritative topics so their docs more likely enter the CE pool.
    """
    scores = {}
    for method_results in results_by_method:
        for rank, r in enumerate(method_results, 1):
            src = r.get("source", "")
            rrf_increment = (1.0 / (k + rank)) * topic_weight
            if src not in scores:
                scores[src] = {
                    "rrf_score": 0.0,
                    "best_score": 0.0,
                    "doc": dict(r),
                }
            scores[src]["rrf_score"] += rrf_increment
            if r["_score"] > scores[src]["best_score"]:
                scores[src]["best_score"] = r["_score"]
                scores[src]["doc"] = dict(r)

    flat_docs = [s["doc"] for s in scores.values()]
    flat_docs.sort(key=lambda d: -d.get("rrf_score", 0))
    return flat_docs


# ── Scoring ────────────────────────────────────────────────────────────────────

def score_multiplier(result: dict, kb_number: str = "", topic_weight: float = 1.0, target_subcat: str = "", target_products: list = None) -> float:
    """
    Returns a composite multiplier applied to CE output. Capped at 1.4 to preserve
    CE's semantic primacy while allowing enough headroom for KB + metadata boosts.
    Stage 2 (Post-CE): Breaks ties when CE returns near-equivalent scores.
    Hard cap at 1.4 ensures CE semantic primacy is never overridden.
    """
    source = result.get("source", "").lower()
    pp = result.get("primary_product", "").lower()
    text = result.get("text", "").lower()

    m = topic_weight
    if kb_number and kb_number.lower() in source:
        m *= 1.3
    elif kb_number and kb_number.lower() in text:
        m *= 1.15
    if "kb-" in source:
        m *= 1.1
    # Soft boost: doc's primary_product matches the target topic's subcategory
    if target_subcat and pp == target_subcat.lower():
        m *= 1.15
    # Penalty: doc has "General" primary_product but topic expects specific product
    if target_subcat and pp in ("", "general"):
        m *= 0.75
    # Products boost: doc's mentioned_products intersect target topic's products
    if target_products:
        doc_products = result.get("_filled_products", result.get("mentioned_products", []))
        if isinstance(doc_products, list):
            doc_lower = [str(p).lower() for p in doc_products]
            target_lower = [str(p).lower() for p in target_products]
            if any(p in target_lower for p in doc_lower):
                m *= 1.2
    return min(m, 1.4)


def rerank(query: str, results: list, top_n: int = 30) -> list:
    """Cross-encoder rerank with jina-reranker-v3. Uses Jina's native index mapping.

    Expanded text (_expanded_text) is used when available — up to 32000 chars.
    jina-reranker-v3 supports 8192 tokens (~32K chars), so 32000 is the safe ceiling.
    """
    if not results:
        return results
    docs = [r.get("_expanded_text", r.get("text", ""))[:32000] for r in results]
    rerank_results = jina_rerank(query, docs, top_n=top_n)

    for r in results:
        r["rerank_score"] = 0.0

    for item in rerank_results:
        orig_idx = item.get("index")
        score = item.get("relevance_score", 0.0)
        if isinstance(orig_idx, int) and 0 <= orig_idx < len(results):
            results[orig_idx]["rerank_score"] = score

    return results


# ── Context Expansion (Windowed Retrieval) ───────────────────────────────────

import pyarrow as pa
import pyarrow.compute as pc


# ── Context Expansion ────────────────────────────────────────────────────────
# ── Context Expansion ────────────────────────────────────────────────────────
# Uses native PyArrow pushdown filter via t.to_lance() — bypasses LanceDB's
# async wrapper that caused the 54s deadlock when concurrent queries were running.
# pc.field("rel_path").isin(paths) pushdown is evaluated in Rust before data leaves NVMe.
# Immune to LanceDB Bug #2217 (no .where() used).
def expand_for_rerank(results: list, t, window: int = 2) -> list:
    """
    Expands context window by ±2 chunks. Uses t.to_arrow() in-memory filter
    since it takes only ~0.2s (not the 54s bug case — that's only when called
    from within LanceDB's background loop after concurrent searches).
    Bypasses the async deadlock by loading all rows first, then filtering in Python.
    """
    # 1. Extract unique file paths from results
    paths_set = {r.get("rel_path") for r in results if r.get("rel_path")}
    if not paths_set:
        return results

    # 2. Load full table (~0.2s, fast enough)
    try:
        arr = t.to_arrow()
    except Exception as e:
        print(f"  [Warning] Context expansion failed: {e}", file=sys.stderr)
        return results

    # 3. Build per-file chunk index using column iteration
    docs_by_path = {path: {} for path in paths_set}

    rel_path_col = arr.column('rel_path').to_pylist()
    chunk_idx_col = arr.column('chunk_index').to_pylist()
    text_col = arr.column('text').to_pylist()

    for rp, c_idx, txt in zip(rel_path_col, chunk_idx_col, text_col):
        if rp in docs_by_path and c_idx is not None:
            docs_by_path[rp][c_idx] = txt

    # 4. Reconstruct ±2 window for each result
    for r in results:
        path = r.get("rel_path")
        c_idx = r.get("chunk_index")

        if path in docs_by_path and c_idx is not None:
            file_chunks = docs_by_path[path]
            expanded_pieces = []

            # Stitch chunk i-2, i-1, i, i+1, i+2 together
            for i in range(c_idx - window, c_idx + window + 1):
                if i in file_chunks:
                    expanded_pieces.append(file_chunks[i])

            if expanded_pieces:
                r["_expanded_text"] = "\n\n".join(expanded_pieces)

    return results


# ── Main search ────────────────────────────────────────────────────────────────

def run_search(query: str, limit: int = 5, fetch_n: int = 100, rrf_k: int = 60, rerank_top: int = 50, identity: str = NX_AGENT_IDENTITY):
    import lancedb
    import concurrent.futures
    import warnings as _w
    _w.filterwarnings("ignore")

    # Pre-check: llm-guard prompt injection
    blocked = check_injection_guard(query)
    if blocked:
        return [{"error": blocked}]

    # ── BUG #2217 WORKAROUND: Guard against empty/1-char FTS searches ──
    clean_query = re.sub(r'[^\w\s]', '', query).strip()
    if len(clean_query) < 2:
        print("[WARNING] Query too short, avoiding LanceDB Bug #2217.", file=sys.stderr)
        return [{"error": "Your query is too short. Please ask a more detailed Nutanix question."}]

    db = lancedb.connect(str(DB_PATH))
    t = db.open_table("nutanix_rag_v3_dedup")

    # ── PARALLEL: DeepSeek classify + embed + Kuzu graph walk simultaneously ──
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f_topics = ex.submit(classify, query)
        f_emb = ex.submit(jina_embed, query)
        f_graph = ex.submit(get_graph_entities, query)
        topics = f_topics.result()
        emb_query = f_emb.result()
        graph_entities = f_graph.result()

    print(f"Topics: {topics}", file=sys.stderr)
    print(f"Query: {query}\n", file=sys.stderr)

    # ── Dynamic intent detection + filter construction ────────────────────────
    intents = _detect_intents(query)
    print(f"Intents: {intents}", file=sys.stderr)
    filters, has_filters = build_search_filters(query, intents, identity)

    def _search_with_filters(use_filters: list) -> list:
        """Single search with given filter conditions. Returns RRF-merged results."""
        if use_filters:
            filter_str = " AND ".join(f"({fc})" for fc in use_filters)
            vector_q = t.search(emb_query).where(filter_str).refine_factor(2).limit(fetch_n)
            fts_q = t.search(query, query_type="fts").where(filter_str).limit(fetch_n)
        else:
            vector_q = t.search(emb_query).refine_factor(2).limit(fetch_n)
            fts_q = t.search(query, query_type="fts").limit(fetch_n)

        vector_r = list(vector_q.to_list())
        for r in vector_r:
            r["_score"] = 1 - r.get("_distance", 0)
        fts_r = []
        try:
            fts_r = list(fts_q.to_list())
        except Exception as e:
            print(f"  [Warning] FTS Bug #2217 triggered, using vector-only: {e}", file=sys.stderr)
        for r in fts_r:
            r["_score"] = r.get("_score", 0)
        results = rrf_merge([vector_r, fts_r], k=rrf_k)
        for r in results:
            r["_search"] = "filtered"
        return results

    # ── Primary search with full filters ─────────────────────────────────────
    all_results = _search_with_filters(filters)

    # ── Fallback: if filtered search returned < 3 unique results, retry with security-only ──
    if has_filters and len(set(r.get("source") for r in all_results)) < 3:
        print(f"  [Fallback] Only {len(all_results)} results with filters — retrying with security-only", file=sys.stderr)
        security_only = [fc for fc in filters if "access_level" in fc]
        all_results = _search_with_filters(security_only if security_only else [])

    # ── Deduplicate by source — keep highest rrf_score across all appearances
    seen = {}
    for r in all_results:
        src = r.get("source", "")
        if src not in seen:
            seen[src] = r
        else:
            existing_rrf = seen[src].get("rrf_score", 0)
            new_rrf = r.get("rrf_score", 0)
            if new_rrf > existing_rrf:
                seen[src] = r
    unique = list(seen.values())

    # Sort by boosted RRF score then take top rerank_top for reranking
    rrf_sorted = sorted(unique, key=lambda x: -x.get("rrf_score", 0))[:rerank_top]
    print(f"  [{len(unique)}] unique, reranking top {len(rrf_sorted)}...", file=sys.stderr)

    # ── Graph Boost: add structural signal from Kuzu entity co-occurrence ──────
    # Kuzu returns entity names connected to query terms.
    # Match these against LanceDB's ecosystem_entities and mentioned_products columns.
    if graph_entities:
        print(f"  [Graph] {len(graph_entities)} entity types verified by Kuzu graph", file=sys.stderr)
        for r in rrf_sorted:
            row_entities = set()
            row_entities.update(r.get("ecosystem_entities") or [])
            row_entities.update(r.get("mentioned_products") or [])
            row_entities_up = {e.upper() for e in row_entities}
            # Fuzzy match: Kuzu entities are granular ("NCC_GUIDE_V5_3"), LanceDB has short names ("NCC")
            matched_ents = [e for e in graph_entities
                            if any(e.upper() in p.upper() or p.upper() in e.upper()
                                   for p in row_entities)]
            is_verified = len(matched_ents) > 0
            r["_graph_verified"] = is_verified
            r["_graph_entities"] = matched_ents
            if is_verified:
                r["rrf_score"] = r.get("rrf_score", 0) + 0.15
    else:
        for r in rrf_sorted:
            r["_graph_verified"] = False
            r["_graph_entities"] = []

    # ── 1A: Expand to ±2 neighbor context BEFORE cross-encoder ───────────────
    # Merge chunk ± window neighbors into one text block so the CE scores
    # the full localized context, not a single 8000-char fragment.
    # Uses Arrow native filter — no vector search, no SQL IN() workarounds.
    print(f"  [1A] Expanding to ±2 neighbor context...", file=sys.stderr)
    expand_for_rerank(rrf_sorted, t, window=2)

    # Cross-encoder rerank — CE is final semantic arbiter within the Top-30 pool
    reranked = rerank(query, rrf_sorted, top_n=rerank_top)

    # Fallback to RRF if cross-encoder completely fails (all scores are 0)
    api_failed = all(abs(r.get("rerank_score", 0)) < 1e-9 for r in reranked)
    if api_failed:
        print("  [Warning] Cross-encoder returned no scores — falling back to RRF scores.", file=sys.stderr)

    # ── 1B: Filter GitHub blueprints for non-Calm topics ──────────────────────────
    # Blueprints are community reference architectures, not authoritative Nutanix docs.
    # Only include them for Calm-related topics.
    if not any(t in ["CALM_BLUEPRINT"] for t in topics):
        before = len(unique)
        unique = [r for r in unique if not is_blueprint(r)]
        print(f"  [1B] Excluded {before - len(unique)} blueprint chunks (non-Calm topic)", file=sys.stderr)

    # Stage 2: Get KB number and subcategory for multiplier from first matching topic
    kb_number = ""
    primary_topic = topics[0] if topics else ""
    topic_weight = TOPIC_WEIGHTS.get(primary_topic, 1.0)
    target_subcat = SUBJECT_SUBCAT_MAP.get(primary_topic, "")
    target_products = SUBJECT_PRODUCTS_MAP.get(primary_topic, [])
    if topics:
        kb_number = _KB_MAP.get(topics[0], "")

    for r in reranked:
        # Apply Stage 2 multiplier to CE score (breaks ties in CE's favor)
        # Also fill missing products from subcategory (1C)
        if get_effective_products(r):
            r["_filled_products"] = get_effective_products(r)
        mult = score_multiplier(r, kb_number, topic_weight, target_subcat, target_products)
        base_score = r.get("rrf_score", 0) if api_failed else r.get("rerank_score", 0)
        r["_score"] = base_score * mult
        r["_multiplier"] = mult
        r["_ce_score"] = r.get("rerank_score", 0)

    # Filter out low-confidence garbage: CE thinks doc is irrelevant AND no metadata boost
    MIN_CE_SCORE = 0.1
    confident = [r for r in reranked
                 if not (r["_ce_score"] < MIN_CE_SCORE and r["_multiplier"] <= 1.0)]
    confident.sort(key=lambda x: -x.get("_score", 0))
    if len(confident) < limit:
        print(f"[WARNING] Only {len(confident)}/{limit} results met confidence threshold.", file=sys.stderr)

    # Swap expanded context into main text field so LLM sees full localized content
    final_results = confident[:limit]
    for r in final_results:
        if "_expanded_text" in r:
            r["text"] = r["_expanded_text"]

    return final_results


def format_results(results: list, query: str, enable_slack: bool = True, enable_web: bool = True) -> str:
    if not results:
        # Tier 2: Slack fallback
        if enable_slack:
            slack_result = query_slack_fallback(query)
            if not slack_result.startswith("No results found"):
                return slack_result
        # Tier 3: Web fallback
        if enable_web:
            web_result = query_web_search(query)
            if not web_result.startswith("No results found"):
                return web_result
        return "No results found."

    # Check if ALL results have low confidence
    low_confidence = all(r.get("_ce_score", 0) < 0.10 for r in results)
    if low_confidence:
        # RAG results are weak — try Slack
        if enable_slack:
            slack_result = query_slack_fallback(query)
            if not slack_result.startswith("No results found"):
                return slack_result
        # Slack also weak/nothing — try Web
        if enable_web:
            web_result = query_web_search(query)
            if not web_result.startswith("No results found"):
                return web_result

    lines = [f"Query: {query}", "", f"Top {len(results)} results:"]
    for i, r in enumerate(results, 1):
        src = r.get("source", "unknown")
        txt = r.get("text", "").replace("&#xA0;", " ").replace("&amp;", "&").replace("\n", " ").strip()
        graph_tag = " [GRAPH]" if r.get("_graph_verified") else ""
        lines.append(f"\n[{i}] {src}{graph_tag}")
        lines.append(f"    ce={r.get('_ce_score',0):.3f} × {r.get('_multiplier',1):.2f} = {r.get('_score',0):.3f}")
        lines.append(f"    {txt[:600]}...")
    return "\n".join(lines)


def query_slack_fallback(query: str) -> str:
    """Query Slack when RAG returns no results."""
    try:
        result = subprocess.run(
            ["slk", "search", query, "10"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return f"No results found.\n\n(Slack search also failed: {result.stderr[:100]})"
        lines = result.stdout.splitlines()[1:10]  # Skip header, get up to 10 results
        if not lines:
            return "No results found."
        slack_results = []
        for line in lines:
            if "] " in line:
                slack_results.append(line.split("] ", 1)[1][:400])
        if not slack_results:
            return "No results found."
        output = [f"Query: {query}", "", f"Slack search ({len(slack_results)} results):"]
        for i, r in enumerate(slack_results, 1):
            output.append(f"\n[{i}] slack")
            output.append(f"    {r}")
        return "\n".join(output)
    except Exception as e:
        return f"No results found.\n\n(Slack fallback error: {str(e)[:100]})"


def query_web_search(query: str) -> str:
    """Query SearXNG web search as final fallback."""
    try:
        import urllib.request
        import urllib.parse
        req = urllib.request.Request(
            f"{SEARXNG_URL}?q={urllib.parse.quote(query)}&format=json&engines=google,bing,duckduckgo&qtime=0",
            headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            web_results = data.get("results", [])

        allowed_domains = []
        if ALLOWED_DOMAINS_FILE.exists():
            with open(ALLOWED_DOMAINS_FILE) as f:
                allowed_domains = json.load(f).get("domains", [])

        filtered = []
        for r in web_results[:10]:
            url = r.get("url", "").lower()
            if not allowed_domains or any(d.lower() in url for d in allowed_domains):
                filtered.append(
                    f"Title: {r.get('title')}\nURL: {r.get('url')}\nSnippet: {r.get('content', '')}"
                )

        if not filtered:
            return "No results found."

        output = [f"Query: {query}", "", f"Web search ({len(filtered)} results):"]
        for i, r in enumerate(filtered, 1):
            output.append(f"\n[{i}] {r}")
        return "\n".join(output)
    except Exception as e:
        return f"No results found.\n\n(Web search error: {str(e)[:100]})"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Universal Nutanix RAG search engine with fallback waterfall.")
    parser.add_argument("--rerank-top", type=int, default=50)
    parser.add_argument("--identity", type=str,
                        help="Agent identity (sam | nx_shield). Overrides NX_AGENT_IDENTITY env var.")
    parser.add_argument("--no-slack-search", action="store_true",
                        help="Disable Slack fallback.")
    parser.add_argument("--no-web-search", action="store_true",
                        help="Disable Web (SearXNG) fallback.")
    parser.add_argument("query", type=str)
    parser.add_argument("limit", type=int, nargs="?", default=5)
    args = parser.parse_args()
    identity = (args.identity or NX_AGENT_IDENTITY).strip().lower()
    results = run_search(args.query, args.limit, rerank_top=args.rerank_top, identity=identity)
    print(file=sys.stderr)
    print(format_results(
        results, args.query,
        enable_slack=not args.no_slack_search,
        enable_web=not args.no_web_search
    ))


if __name__ == "__main__":
    main()
