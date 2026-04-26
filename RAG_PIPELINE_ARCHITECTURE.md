# NX_Shield RAG Pipeline — Architecture & Documentation

> **Last updated:** 2026-04-26
> **Author:** Sam (OpenClaw agent for Ivan)
> **Status:** Active — Mac mini as primary runtime, MacBook providing Gemma via Tailscale

---

## Overview

This document describes the Nutanix technical knowledge base RAG (Retrieval-Augmented Generation) pipeline. It is used by **Sam** (Ivan's primary assistant) and **NX_Shield** (engineer-facing support agent) to answer Nutanix product, KB, and troubleshooting questions.

---

## System Architecture

### High-Level Flow

```
DATA SOURCES
|
+-- portal.nutanix.com (CDP/Chrome)
+-- nutanix.dev / developers.nutanix.com
+-- GitHub Nutanix repos
+-- NCC docs, Files, Objects, Calm, Flow
+-- Local PDFs (MarkItDown -> markdown)
|
v
INGESTION PIPELINE
|
+-- embed_pipeline_v2.py (chunking + embedding)
+-- selective_embed.py (incremental updates)
+-- MarkItDown (PDF -> markdown)
|
v
LANCEDB (~98K rows, ~991 MB)
|
+-- Vector index (LanceDB)
+-- BM25 FTS index
|
v
QUERY INTERFACE
|
+-- Sam: direct Python import run_search()
+-- NX_Shield: MCP protocol via mcp_server.py
|
v
run_search() [7-stage pipeline]
|
+-- Stage 1: Gemma classification (MacBook Gemma via Tailscale, 3s timeout)
+-- Stage 2: Jina embed (api.jina.ai, 1024-dim)
+-- Stage 3: LanceDB hybrid search (vector + FTS + RRF)
+-- Stage 4: expand_for_rerank (±2 neighbor context via PyArrow)
+-- Stage 5: Jina cross-encoder rerank (top 30 → top 5)
+-- Stage 6: score_multiplier() + confidence filter
+-- Stage 7: format_results() -> LLM-readable output
|
v
format_results() -> LLM-readable output
```

### LanceDB Table

- **Path:** `~/.openclaw/memory/lancedb-pro/nutanix_rag_v2.lance`
- **Rows:** 170,708
- **Size:** ~1.2 GB
- **Embedding:** Jina AI `jina-embeddings-v5-text-small` (1024 dims)
- **Indexes:** LanceDB vector index + BM25 FTS index

**Schema fields:**

| Field | Type | Description |
|---|---|---|
| `text` | string | Chunk content, ~8000 chars per chunk |
| `vector` | float[1024] | Jina embedding |
| `products` | JSON array | e.g. `["AOS", "AHV"]` |
| `subcategory` | string | e.g. `NCC_HEALTH`, `STORAGE_FORMULA` |
| `folder` | string | Source folder path |
| `source` | string | Full URL or file path |
| `kb_number` | string | e.g. `KB-000001557` |
| `content_type` | string | e.g. `admin-guide`, `api-reference` |
| `chunk_index` | int | Position in source document |
| `total_chunks` | int | Total chunks in source document |

### Query Paths

| Agent | Method | Tool Call |
|---|---|---|
| Sam (main) | Direct Python import | `run_search()` |
| NX_Shield | MCP protocol | `mcp_server.py` -> `query_nutanix_docs` |

### 5-Stage Run_Search Pipeline

| Stage | Function | Input | Output | Duration |
|---|---|---|---|---|
| 1 | Gemma classification | query | topics | ~1s |
| 2 | Jina embed | query | emb_topic (1024-dim) | ~1s |
| 3 | LanceDB hybrid search | topics + emb_topic | top 30 candidates | ~0.5s |
| 4 | expand_for_rerank | candidates | `_expanded_text` (~24K chars) | **3-4s** |
| 5 | Jina CE rerank | `_expanded_text` | reranked top 5 | ~1s |
| 6 | Score multiplier + confidence filter | CE scores | boosted scores | ~0.01s |
| 7 | format_results() | boosted scores | formatted output | ~0.01s |

**Total pipeline latency:** ~6-8s per query (warm) — down from ~60s after expand_for_rerank fix

---

## Runtime Infrastructure

| Component | Host | IP | Notes |
|---|---|---|---|
| LanceDB + search | **Mac mini** | Tailscale | Primary runtime |
| Gemma 4 31B | **MacBook** | Tailscale | Classification only |
| Jina Embed API | Cloud | api.jina.ai | Vectorization |
| Jina Rerank API | Cloud | api.jina.ai | Semantic reranking |
| OpenClaw gateway | **Mac mini** | LAN | Agent orchestration |

---

## Stage-by-Stage Reference

---

### Stage 0 — Parallel Gemma + Jina Embed

**Purpose:** Simultaneously classify the query into Nutanix topics AND generate its embedding vector. Both are independent operations that can run in parallel.

**Tools:**

- **`classify(query)` → `["TOPIC1", "TOPIC2"]`**
  - **Type:** Query classification (Gemma 4 31B + keyword fallback)
  - **Endpoint:** `http://<macbook-tailscale>:1234/v1/chat/completions` (MacBook via Tailscale)
  - **Model:** `gemma4` (Q4_K_M, 19.89GB)
  - **Prompt:** "You are a Nutanix technical support classifier. Given the user query below, pick the 1-3 best matching topics from the list. Reply with ONLY topic names separated by commas, nothing else."
  - **Fallback:** If Gemma fails/times out, `QUERY_CLASSIFIERS` dict provides keyword-to-topic mapping (e.g. `"ncc health" → NCC_HEALTH`)
  - **Valid topics:** `NETWORKING`, `AHV_NETWORK`, `NCC_HEALTH`, `FLOW_SECURITY`, `FLOW_QUARANTINE`, `STORAGE_FORMULA`, `ERASURE_CODING`, `LCM_FIRMWARE`, `GPU_VGPU`, `STRETCH_CLUSTER`, `DATA_PROTECTION`, `CALM_BLUEPRINT`, `NDB_DATABASE`, `HARDWARE_SPEC`, etc.
  - **Output:** `["NCC_HEALTH"]` or `["FLOW_SECURITY", "FLOW_QUARANTINE"]`

- **`jina_embed(query)` → `[0.0123, -0.0456, ...]` (1024 floats)**
  - **Type:** Text vectorization
  - **Endpoint:** `https://api.jina.ai/v1/embeddings`
  - **Model:** `jina-embeddings-v5-text-small` (1024 dimensions)
  - **API key:** Stored in `nutanix_rag_search.py` (Jina key)
  - **Timeout:** 10s
  - **Output:** 1024-dimensional float vector

**Example input/output:**
```
Query: "NCC health check sysstats error"
  → classify(): ["NCC_HEALTH"]
  → jina_embed(): [0.02, -0.07, 0.11, ...]  (1024 floats)
```

---

### Stage 1 — Parallel Topic Searches

**Purpose:** For each topic returned by Stage 0, run a vector + FTS hybrid search against LanceDB. Topics run in parallel (ThreadPoolExecutor max_workers=3).

**Key concept: Products Pushdown Filter**

Before searching, a SQL filter is built from `SUBJECT_PRODUCTS_MAP`:

```python
target_products = SUBJECT_PRODUCTS_MAP.get(topic, [])
# e.g. topic="NCC_HEALTH" → ["NCC"]

prod_conditions = " OR ".join(
    f"lower(products) LIKE '%{p.lower()}%'" for p in target_products
)
filter_str = f"({prod_conditions}) OR products IS NULL"
```

This pre-filters LanceDB to only rows matching the relevant Nutanix product(s), dramatically reducing the search space.

**Fallback safety net:** `OR products IS NULL` ensures unlabeled rows are never excluded.

**Example products map entries:**
```python
SUBJECT_PRODUCTS_MAP = {
    "NCC_HEALTH":        ["ncc"],
    "FLOW_QUARANTINE":   ["flow"],
    "STORAGE_FORMULA":   ["AOS", "Volumes"],
    "CALM_BLUEPRINT":    ["calm"],
    "GPU_VGPU":          ["ahv", "nci"],
    "NDB_DATABASE":      ["nutanix database service", "era"],
    "LCM_FIRMWARE":     ["lcm"],
    "STRETCH_CLUSTER":  ["AOS", "ahv"],
}
```

**Per-topic search steps:**

1. **Build topic query:** Use `SPECIFIC_SEARCHES` dict to get the best search string for this topic, or fall back to the original query + topic name
2. **Vector search:** `t.search(emb_topic).where(filter_str).refine_factor(2).limit(fetch_n)` — fetch_n=100
3. **FTS search:** `t.search(search_q, query_type="fts").where(filter_str).limit(fetch_n)` — BM25
4. **RRF merge:** `rrf_merge([vector_r, fts_r], k=60, topic_weight)` — Reciprocal Rank Fusion combines both rankings

**Topic weights** (boost certain topics over others):
```python
TOPIC_WEIGHTS = {
    "STORAGE_FORMULA":   1.25,   # authoritative formula doc — high priority
    "ERASURE_CODING":    1.10,
    "HARDWARE_SPEC":      1.10,
    "NETWORKING":        1.05,
    "NCC_HEALTH":        1.05,
    ...
}
```

**Output per topic:** List of up to 100 results, each with:
- `source`, `text`, `products`, `subcategory`, `rrf_score`, `_score`

**Combined output:** All topic results merged, deduplicated by `source` (highest `rrf_score` wins), top 50 kept for reranking.

---

### Stage 2 — Context Expansion (`expand_for_rerank`)

**Purpose:** Replace each hit's tiny chunk (~8000 chars) with ±2 neighboring chunks from the same document. Gives the cross-encoder full localized context instead of a fragment.

**Why it matters:** Chunks are ~8000 chars. The best answer might span chunk boundaries. Expanding to ±2 neighbors gives ~24,000 chars of context, dramatically improving CE scoring accuracy.

**How it works:**

```python
# 1. Group results by rel_path, collect all chunk indices needed
files_to_fetch = {}
for r in results:
    path = r.get("rel_path", "")
    idx = r.get("chunk_index", 0)
    files_to_fetch[path].update(range(max(0, idx-window), idx+window+1))

# 2. Arrow-native filter (no vector search, no SQL IN())
full_table = t.to_arrow()
mask_path = pc.equal(full_table["rel_path"], path)
mask_idx = pc.is_in(full_table["chunk_index"], idx_list)
filtered = full_table.filter(pc.and_(mask_path, mask_idx))

# 3. Sort by chunk_index, merge texts
merged_text = "\n\n".join(texts)  # ~24K chars max

# 4. Attach as _expanded_text (NOT overwriting original text yet)
r["_expanded_text"] = merged_text
```

**Window:** ±2 chunks per side (configurable via `window=2`)

**⚠️ CRITICAL FIX (2026-04-26):** The original `.to_pandas()` approach deadlocked on LanceDB 0.27 (Python 3.9) due to PyArrow schema issues. Replaced with direct PyArrow column iteration — bypasses LanceDB's Pandas export entirely, reducing expand time from **54s → 3-4s** (**9× faster**).

**Memory approach:** Uses PyArrow `filter()` (columnar, memory-mapped) — does NOT re-run vector search. Reads existing data from disk.

**Output:** Results list with `_expanded_text` field added (up to 32,000 chars per result)

**Example:**
```
Original chunk (chunk 5): "...sysstats error on node..."
_expanded_text: "...NCC sysstats collection...sysstats error on node...node reboot required..."
                 (chunks 3, 4, 5, 6, 7 merged)
```

---

### Stage 3 — Cross-Encoder Rerank (`jina_rerank`)

**Purpose:** Use Jina's hosted listwise reranker to score the semantic relevance of each candidate to the query. The CE understands meaning, not just keyword overlap or vector distance.

**Tool:** `jina_rerank(query, docs, top_n=30)`

**Endpoint:** `https://api.jina.ai/v1/rerank`

**Model:** `jina-reranker-v3`
- Listwise reranker (considers all candidates together, not pairwise)
- 0.6B parameters
- Context window: 8192 tokens (~32K chars)
- State-of-the-art on BEIR benchmark

**API call:**
```python
curl -X POST https://api.jina.ai/v1/rerank \
  -H "Authorization: Bearer <key>" \
  -d '{"model": "jina-reranker-v3", "query": query, "documents": docs, "top_n": 30}'
```

**Input:** `_expanded_text` of each of the top 30 candidates (up to 32K chars each)

**Output:** Reranked list with `rerank_score` (CE relevance score, typically -1 to +1)

**Why listwise matters:** Pairwise rerankers score doc A vs doc B individually. Listwise considers the full ranking simultaneously, producing better global ordering.

**Failure fallback:** If all CE scores are effectively 0, falls back to RRF scores. This is rare.

---

### Stage 4 — Score Multiplier (`score_multiplier`)

**Purpose:** Boost scores of results that match the query's topic via metadata signals that the CE might miss.

**Three boost signals:**

| Signal | Condition | Multiplier |
|---|---|---|
| KB# exact match | `kb_number` (e.g. `KB-000001557`) found in result text | 2.0× |
| Subcategory match | result's `subcategory` == query's `target_subcat` | 1.5× |
| Products match | result's `products` contains any query topic product | 1.3× |

**Code:**
```python
def score_multiplier(result, kb_number, topic_weight, target_subcat, target_products):
    m = topic_weight  # e.g. 1.25 for STORAGE_FORMULA
    
    if kb_number and kb_number.lower() in result.get("text", "").lower():
        m *= 2.0
    if target_subcat and result.get("subcategory") == target_subcat:
        m *= 1.5
    if target_products:
        doc_products = result.get("_filled_products", result.get("products", []))
        if any(p in target_products for p in doc_products):
            m *= 1.3
    
    return min(m, 1.85)  # cap to prevent runaway scores
```

**Final score:** `final_score = CE_score × multiplier`

**Why this matters:** CE scores can be close between two results. A KB match or product match can be the tiebreaker that surfaces the authoritative doc.

---

### Stage 5 — Confidence Filter + Text Swap

**Purpose:** Remove low-quality results and prepare final output for the LLM.

**Confidence filter:**
```python
MIN_CE_SCORE = 0.1
confident = [r for r in reranked
             if not (r["_ce_score"] < MIN_CE_SCORE and r["_multiplier"] <= 1.0)]
```

Logic: exclude results where the CE thinks they're irrelevant (score < 0.1) AND they have no metadata boost. This removes "hallucinated-adjacent" chunks that sneaked through vector search.

**Text swap (CRITICAL FIX — 2026-04-18):**
```python
for r in final_results:
    if "_expanded_text" in r:
        r["text"] = r["_expanded_text"]  # LLM sees expanded context
```

Without this swap, the LLM would only see the original tiny chunk. The expanded context was used for CE scoring but never delivered to the user.

**Output:** Top 5 results, each with:
- `text` — full expanded context (up to ~24K chars)
- `source` — URL or file path
- `_score` — final CE × multiplier score
- `_ce_score` — raw CE score
- `_multiplier` — total metadata boost applied

---

### Output Format (`format_results`)

**Purpose:** Convert raw result dicts into human-readable formatted string.

```
Top 3 results:

[1] https://portal.nutanix.com/page/documents/details?targetId=...
    ce=0.572 × 1.50 = 0.858
    Title: NCC Health Check sysstats
    How to run NCC health checks and interpret sysstats output...

[2] https://portal.nutanix.com/page/documents/details?targetId=...
    ce=0.431 × 1.30 = 0.560
    Title: NCC log collection
    Steps to collect NCC logs for support escalation...
```

In Discord, URLs are wrapped in `<>` to prevent embed previews:
```
<https://portal.nutanix.com/page/documents/details?targetId=...>
```

---

## Key Data Structures

### `SUBJECT_PRODUCTS_MAP`
Maps Nutanix topic → relevant products for pushdown filter.
Used in Stage 1 to build LanceDB SQL filter.

### `SUBJECT_SUBCAT_MAP`
Maps topic → subcategory string.
Used in Stage 4 for subcategory match multiplier.

### `TOPIC_WEIGHTS`
Maps topic → float multiplier (default 1.0).
Used in Stage 1 RRF merge and Stage 4 score multiplier.

### `QUERY_CLASSIFIERS`
Keyword → topic mapping for fallback classification when Gemma is unavailable or times out.
Covers ~30+ patterns including "ncc health", "flow quarantine", "RF2", "vGPU", etc.

### `SPECIFIC_SEARCHES`
Topic → custom search query override.
Used for topics where a precise query string outperforms the original query.
Example: `STORAGE_FORMULA` → `"KB-000001557 RF2 RF3 N+1 storage capacity..."`

---

## Products Pushdown Filter — Deep Dive

**What it is:** A LanceDB SQL `WHERE` clause applied at search time to restrict which rows are scanned.

**Why it matters:** Without it, LanceDB scans all 98K rows. With it, LanceDB only scans rows tagged with the relevant product(s) — typically 5-20% of the DB.

**Example — NCC_HEALTH query:**
```sql
WHERE (lower(products) LIKE '%ncc%') OR products IS NULL
```

**Example — STORAGE_FORMULA query:**
```sql
WHERE (lower(products) LIKE '%aos%' OR lower(products) LIKE '%volumes%') OR products IS NULL
```

**Coverage:** 99.6% of rows have products filled. The `OR products IS NULL` ensures the remaining 0.4% (409 rows) are never excluded.

**Limitation:** Folder-based pushdown was considered but not implemented. Products pushdown handles the same use cases more reliably since folder tagging is less consistent than product tagging.

---

## Known Limitations & Trade-offs

1. **Gemma routing for short/generic queries:** "how do I configure volumes in AOS?" has no topic keyword match. Relies on Gemma to route to `STORAGE_FORMULA`. If Gemma fails, falls back to pure vector search.

2. **Volumes product ambiguity:** "volumes" alone is too generic (could be Docker, Kubernetes, Windows). Only fires on specific phrases: `volume group`, `iSCSI`, `nutanix volumes`.

3. **GitHub blueprints excluded for non-Calm topics:** 19.6K community blueprint chunks are filtered out for all topics except `CALM_BLUEPRINT`. This is intentional — they're reference architectures, not authoritative Nutanix docs.

4. **Context window cap:** Expanded text capped at ~32K chars. Very long documents may not fully fit. The ±2 chunk window is a balance between context richness and token budget.

5. **LanceDB compaction:** `compact_files()` requires `lance` Python library which isn't installed. The table is already 1 data file (compact from the start), so this is not currently an issue.

---

## MCP Server (NX_Shield Integration)

**File:** `mcp_server.py`

**Purpose:** Exposes `query_nutanix_docs` as an MCP tool so NX_Shield (separate OpenClaw agent) can query the RAG pipeline without direct file system access.

**Protocol:** MCP (Model Context Protocol) over stdin/stdout subprocess

**Security:** NX_Shield has no direct access to the workspace — it only calls the MCP tool, which runs `nutanix_rag_search.py` as a subprocess. This provides process-level isolation.

**stderr handling:** Diagnostic output from `nutanix_rag_search.py` goes to stderr and is discarded by the MCP server. Only the formatted results (stdout) are returned to NX_Shield.

**Timeout:** 60 seconds per query. If the pipeline takes longer, returns `"Search timed out after 60 seconds."`

---

## File Inventory

| File | Purpose |
|---|---|
| `nutanix_rag_search.py` | Core RAG pipeline (run_search, classify, embed, rerank) |
| `mcp_server.py` | MCP server exposing query_nutanix_docs to NX_Shield |
| `embed_pipeline_v2.py` | Batch embedding script (used for new content ingestion) |
| `selective_embed.py` | Selective embedding — only new files (hash-based dedup) |
| `embed_portal.py` | Portal-specific scraping + embedding script |
| `query_rag.py` | Thin logging wrapper — logs Sam's queries to query_log.jsonl |
| `fix_html_garbage.py` | Cleans up HTML artifacts in scraped content |

---

## Runtime Configuration

```python
DB_PATH = Path("~/.openclaw/memory/lancedb-pro").expanduser()
GEMMA_URL = "http://100.74.228.94:1234/v1/chat/completions"  # MacBook via Tailscale
JINA_API_KEY = "<your-jina-api-key>"
JINA_EMBED_URL = "https://api.jina.ai/v1/embeddings"
JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"
GEMMA_TIMEOUT = 3   # seconds (fail-fast to keyword fallback)
fetch_n = 100       # LanceDB rows fetched per topic
rerank_top = 30     # candidates sent to CE reranker (30 → 5)
limit = 5           # final results returned
```

---

## Debugging & Diagnostics

**Stderr output** (visible in exec logs):
```
Topics: ['NCC_HEALTH']
Query: NCC health check sysstats error

  [124] unique, reranking top 30...
  [1A] Expanding to ±2 neighbor context...
  [1B] Excluded 0 blueprint chunks (non-Calm topic)
```

**Query logging:** Sam's queries are logged to `rag/pipeline/query_log.jsonl` via `query_rag.py`. NX_Shield queries are NOT logged (privacy for external engineers).

**Manual test:**
```bash
python3 nutanix_rag_search.py "NCC health check sysstats error" 3
```

---

## Change Log

| Date | Change |
|---|---|
| 2026-04-26 | **expand_for_rerank fix:** `.to_pandas()` deadlock → PyArrow column iteration → 54s → 3-4s (**9× faster**) |
| 2026-04-26 | **GEMMA_TIMEOUT:** 10s → **3s** (fail-fast to keyword fallback) |
| 2026-04-26 | **Jina curl --max-time 15:** added to all Jina API calls |
| 2026-04-26 | **mcp_server.py:** `parse_known_args()` for MCP safety |
| 2026-04-26 | **rerank_top:** pipeline sends top 30 → returns top 5 (was 50→5) |
| 2026-04-26 | **DB rows:** 98,234 → **170,708** (MacBook/Mac mini sync) |
| 2026-04-26 | **memory-lancedb-pro:** removed from plugins.entries (using hindsight-openclaw) |
| 2026-04-26 | **fullqualitypath MCP:** removed — only `nutanix-rag-search-fastpath` remains |
| 2026-04-26 | **NX_Shield SOUL.md:** Max 2 RAG calls + synthesize-and-stop rule |
| 2026-04-26 | **Pipeline latency:** ~60s → **~6-8s** per query |
| 2026-04-17 | Products pushdown filter implemented |
| 2026-04-17 | Metadata fix pass: 24,910 rows updated (26.5% → 0.4% empty products) |
| 2026-04-17 | Gemini 4 31B semantic routing (MacBook via Tailscale) |
| 2026-04-17 | Parallel topic searches (ThreadPoolExecutor max_workers=3) |
| 2026-04-17 | Parallel Gemma + embed (ThreadPoolExecutor max_workers=2) |
| 2026-04-18 | Volumes classifier tightened (removed generic "volumes" keyword) |
| 2026-04-18 | Critical bug fix: `_expanded_text` → `text` swap at return |
| 2026-04-18 | Dead code removed: `expand_to_parent_window` (78 lines) |
| 2026-04-18 | NX_Shield SOUL.md: Rule 5 — must cite sources |
| 2026-04-18 | MacBook Gemma switched from MacBook → MacBook (Tailscale) |
| 2026-04-18 | Stale rebuild directories deleted: ~509MB freed |
