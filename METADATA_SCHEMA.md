# RAG Metadata Schema — Design & Structure

## Overview

Each chunk or page in the RAG database carries metadata used for **filtering**, **ranking**, **lineage**, and **answer-policy disclosure**. The historical v3 schema focused on `access_level`, `doc_type`, `primary_product`, `mentioned_products`, and `ecosystem_entities`. The active LanceDB search index keeps that lineage while adding richer source-family, confidentiality, migration, and page/document metadata.

---

## Active LanceDB Schema Snapshot (verified 2026-05-27)

| Item | Value |
|---|---|
| Search index | LanceDB active unified corpus |
| Table name | version-specific implementation detail |
| Index families | vector, full-text search, scalar metadata filters |
| `chunk_hash` | populated and unique in the active corpus |
| `unique_chunk_key` | populated and unique in the active corpus |

Important active metadata fields:

| Field | Purpose |
|---|---|
| `migration_source` | distinguishes native rows from imported lineage |
| `legacy_v3_chunk_hash` | preserves historical chunk lineage for imported evidence |
| `legacy_rel_path` / lineage path fields | preserves source path lineage where historical field names differ from current fields |
| `source_family` | routes broad evidence families such as portal, KB, Google Docs, xpress, team chat, and historical imports |
| `confidentiality` / `access_scope` | access/scope filtering |
| `search_text` | FTS target used by active search |
| `unique_chunk_key` | active unique row key |

Known K17 roadmap items:

| Priority | Item | Direction |
|---|---|---|
| P0 | `content_hash` gaps on legacy rows | side-by-side rebuild with `content_hash_v2` |
| P1 | missing `document_id`, sparse `section_id` | deterministic document/section IDs |
| P2 | missing parent/child context fields | parent/child chunking for context expansion |
| P3 | missing normalized product/version/source-authority fields | add `products`, `versions`, `source_authority`, `authority_score` |
| P4 | index changes | benchmark before adding indexes; current scalar filters are already fast |

---

## Historical v3 Schema Fields

| Field | Type | Description |
|---|---|---|
| `access_level` | string | `public` or `internal` — controls whether a chunk is visible to external users (NX_Shield) |
| `doc_type` | string | High-level document category derived from top-level folder |
| `primary_product` | string | Primary Nutanix product this doc is about (path-based, with frequency fallback) |
| `mentioned_products` | list[string] | All Nutanix products mentioned in the chunk text |
| `ecosystem_entities` | list[string] | Competitors/partners mentioned (VMware, Red Hat, HPE, etc.) |
| `versions` | list[string] | Product version strings extracted from text (e.g. `AOS_6.5`, `AHV_20220304`) |
| `content_types` | list[string] | Content subtypes detected from path + text (api-reference, troubleshooting, release-notes, etc.) |

---

## Field Design Rationale

### `access_level` — Internal vs Public

**Why:** NX_Shield serves external engineers. Some source material (internal Slack, Google Docs, WhatsApp) must not be exposed outside.

**How it works:** Top-level folder names in the source directory determine access level. If the chunk lives under `slack/`, `whatsapp/`, `internal/`, or `google-docs/` → `internal`. Everything else → `public`.

```python
INTERNAL_FOLDERS = {"slack", "whatsapp", "internal", "google-docs", "inbound", ...}
# NX_Shield pre-filters on access_level="public" at query time
```

### `doc_type` — Document Category

**Why:** Users ask different question types — battlecards for competitive, KB articles for troubleshooting, API specs for developers. Mapping doc type upfront lets us route queries to the right content faster.

**How it works:** Top-level folder maps to doc type. Portal docs → `official_doc`, KB articles → `kb_article`, `xpress-md` → `battlecard`, `scraped` → `web_capture`, etc.

```
doc_type_map = {
    "portal": "official_doc",
    "kb_articles": "kb_article",
    "xpress-md": "battlecard",
    "broadcom-vmware": "competitive_intel",
    "slack": "team_chat",
    "nutanix.dev": "tech_blog",
    "github": "code_repo",
    ...
}
```

### `primary_product` — Primary Nutanix Product

**Why:** Most searches are product-specific. Knowing the primary product lets us pre-filter before the embedding search, improving accuracy and speed.

**How it works:** Two-stage assignment:
1. **Path-based** — Portal subdirectory maps to product (e.g. `portal/ahv/` → `AHV`, `portal/nutanix_database_service/` → `NDB`)
2. **Frequency fallback** — If the path returns `General` (non-portal content), count product mentions in text and pick the most frequent one

```python
# Path-based (primary method)
if "ahv" in path_lower: return "AHV"
if "nutanix_database_service" in path_lower: return "NDB"

# Frequency fallback (for non-portal docs)
if primary_product == "General":
    counts = {name: count_in_text(pattern) for name, pattern in NUTANIX_PRODUCTS.items()}
    primary_product = max(counts, key=counts.get) if counts else "General"
```

### `mentioned_products` — All Nutanix Products in Text

**Why:** A document about AOS might mention Prism, Calm, and NCC. This list captures the full product landscape of a chunk, useful for broad competitive queries.

**How it works:** Regex search across `NUTANIX_PRODUCTS` dictionary for every product name/pattern. No limit — all found products are listed.

```python
NUTANIX_PRODUCTS = {
    "AOS": r"\bAOS\b",
    "AHV": r"\bAHV\b",
    "Prism": r"\bPrism Central?\b|\bPrism\b",
    "NKP": r"\b(NKP|Nutanix Kubernetes Platform)\b",
    "NDB": r"\b(NDB|Nutanix Database Service)\b",
    "Files": r"\bNutanix Files\b",
    ...
}
```

### `ecosystem_entities` — Competitors & Partners

**Why:** Competitive intelligence queries (VMware vs AHV, Red Hat vs Nutanix AI) need to know which competitors are mentioned in a document.

**How it works:** Regex search across `ECOSYSTEM_ENTITIES` dictionary.

```python
ECOSYSTEM_ENTITIES = {
    "VMware": r"\bVMware\b|ESXi|vSAN|vSphere|VCF\b|VVF\b|Aria|vRealize|NSX[\s-]?[TX]|Horizon|vCenter",
    "Broadcom": r"\bBroadcom\b",
    "Red_Hat": r"Red[\s_]?Hat|OpenShift|Ansible|OpenStack|Ceph\b",
    "HPE": r"\bHPE\b|SimpliVity|Alletra|Nimble\b|ProLiant|Moonshot",
    "Pure_Storage": r"Pure[\s_]?Storage|FlashArray|FlashBlade",
    "Microsoft": r"\bMicrosoft\b|Hyper[\s-]?V|Azure\b|AVS\b",
    ...
}
```

### `versions` — Product Version Strings

**Why:** Users ask about specific versions (AOS 6.5, AHV 20220304). Version extraction enables version-specific search.

**How it works:** Regex patterns per product, up to 5 versions per chunk.

```python
versions = []
patterns = {
    "AOS": r"\bAOS\s+(\d+\.\d+(?:\.\d+)?)\b",
    "AHV": r"\bAHV\s+(\d+\.\d+(?:\.\d+)?)\b",
    "Prism_Central": r"\bPrism Central\s+(\d+\.\d+(?:\.\d+)?)\b|PC\s+(\d+\.\d+)",
    ...
}
# Extracts e.g. ["AOS_6.5", "AOS_7.0", "AHV_20220304"]
```

### `content_types` — Content Subtype Detection

**Why:** A Prism admin guide and a Prism troubleshooting KB are both about Prism but serve different intents. Detecting content type helps route to the right document.

**How it works:** Dual detection — path patterns + text regex. A file named `security-advisory` always gets `security-advisory`; otherwise, look for API, FAQ, architecture, presentation patterns in the text.

```python
# Path-based (high confidence)
if "security_advisory" in path: return ["security-advisory"]

# Text-based (pattern matching)
if re.search(r"(API\b|SDK\b|REST|endpoint)", text): content_types.append("api-reference")
if re.search(r"(error|issue|fix|debug|troubleshoot|KB\b)", text): content_types.append("troubleshooting")
if re.search(r"(release\b|GA\s|EOSL|EOL\b)", text): content_types.append("release-notes")
```

---

## Data Flow

```
Source file
    │
    ▼
tagger_v3.py (apply_v3_tags)
    │
    ├── access_level ── path → "public" | "internal"
    ├── doc_type ───── path → DOC_TYPE_MAP[top_folder]
    ├── primary_product ─ path → PORTAL_PRODUCT_MAP[subdir] (fallback: frequency)
    ├── mentioned_products ── text → NUTANIX_PRODUCTS regex
    ├── ecosystem_entities ─ text → ECOSYSTEM_ENTITIES regex
    ├── versions ───────── text → version regex patterns
    └── content_types ─── path + text → pattern detection
    │
    ▼
LanceDB chunk (with metadata columns)
    │
    ▼
nutanix_rag_search.py
    ├── Pre-filter: access_level, doc_type, primary_product
    ├── Embedding search (vector similarity)
    └── Re-rank: topic score + source match
```

---

## Pre-Filter vs Rerank

The metadata serves two stages of the search pipeline:

1. **Pre-filter (fast, at query time):** `access_level`, `doc_type`, `primary_product` are used to narrow the candidate set before embedding search. This is the biggest accuracy lever — ~30% of docs are tagged with a specific product.

2. **Rerank (scoring boost):** `mentioned_products`, `ecosystem_entities`, `versions`, `content_types` are used in the rerank scoring to boost relevant documents.

---

## Folder → Product Mapping (Selected)

| Portal Subdirectory | Primary Product |
|---|---|
| `ahv` | AHV |
| `aos` | AOS |
| `prism` / `prism_central` | Prism |
| `nutanix_database_service` | NDB |
| `files` | Files |
| `objects` | Objects |
| `nkp` / `nutanix_kubernetes_platform` | NKP |
| `ncc` | NCC |
| `flow_*` | Flow |
| `lcm` | LCM |
| `move` | Move |
| `cloud_clusters_(nc2)` | NC2 |
| `api_reference` / `developers_nutanix_com` | v4_API |
| `security_advisories` / `aos_security` | AOS |

---

## Notes

- **`access_level` is the NX_Shield isolation mechanism** — external engineers only see `public` chunks. Internal material (Slack, WhatsApp, etc.) is never served to NX_Shield.
- **Frequency fallback exists because non-portal docs** (battlecards, scraped content) don't follow the portal folder structure. Without it, `primary_product` would default to `General` for most battlecards.
- **Version extraction is approximate** — it catches standard patterns like `AOS 6.5` and `AHV 20220304`, but complex version strings may be missed. This is a known limitation.
- **`content_types` is multi-valued** — a document can be both `release-notes` and `api-reference` if both patterns are detected.

---

## Before and After — v2 to v3

### Why the Schema Changed

The original `nutanix_rag_v2` database had a simpler metadata schema with `category`, `subcategory`, and `products` fields. During the v3 rebuild, the schema was redesigned for two reasons:

1. **Messy data** — 1,374 rows had `products` as plain text strings (`"NCP_Pure_Storage"`) instead of JSON arrays. 66 rows had empty `category`. Cleaning individual rows was fragile.
2. **Poor filtering utility** — v2 lacked consistent `access_level`, `doc_type`, and `primary_product` fields, making pre-filtering at query time unreliable.

Rather than patch v2's metadata, the decision was made to redesign the schema from scratch during the v3 rebuild.

### v2 Schema

| Field | Type | Issues |
|---|---|---|
| `category` | string | ~66 rows empty, inconsistent values |
| `subcategory` | string | rarely populated |
| `products` | string (non-JSON) | 1,374 rows had plain text like `"NCP,HPE,Dell"` instead of `["NCP", "HPE", "Dell"]` |
| `primary_product` | string | often defaulted to `General` for non-portal docs |
| `mentioned_products` | string | not a proper list |

### v3 Schema (Current)

| Field | Type | Notes |
|---|---|---|
| `access_level` | string | `public` \| `internal` — isolation mechanism |
| `doc_type` | string | 15+ document types mapped from top-level folder |
| `primary_product` | string | Path-based with frequency fallback — near 100% populated |
| `mentioned_products` | list[string] | All Nutanix products found via regex — no limit |
| `ecosystem_entities` | list[string] | **New in v3** — competitors and partners |
| `versions` | list[string] | **New in v3** — version strings like `AOS_6.5` |
| `content_types` | list[string] | **New in v3** — content subtype detection |

### Data Quality After v3

| Metric | v2 (before cleanup) | v3 |
|---|---|---|
| `primary_product` populated | ~66% | ~100% |
| `doc_type` populated | partial | ~100% |
| `access_level` | did not exist | ~100% |
| `mentioned_products` non-null | partial | ~100% |
| `ecosystem_entities` | did not exist | ~100% |
| Version extraction | manual | automatic per chunk |
