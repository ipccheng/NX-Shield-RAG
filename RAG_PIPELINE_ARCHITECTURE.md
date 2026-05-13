# NX_Shield RAG Pipeline — Architecture & Documentation

> **Last updated:** 2026-05-13
> **Status:** Active
> **Script:** `nutanix_rag_search.py` (workspace/scripts/)
> **MCP Backend:** `nx_gateway_mcp.py` → spawns `nutanix_rag_search.py` as subprocess

---

## Overview

This document describes the Nutanix technical knowledge base RAG (Retrieval-Augmented Generation) pipeline used by **Sam** and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

The pipeline runs RAG + Ripgrep in parallel, then falls back through Slack and SearXNG web search if confidence is low.

---

## System Architecture

### High-Level Flow

```
QUERY
 │
 ▼
 ┌─────────────────────────────────────────────┐
 │  PARALLEL EXECUTION (ThreadPoolExecutor)    │
 │  1. DeepSeek topic classify                 │
 │  2. Jina embed (api.jina.ai)               │
 │  3. Kuzu graph walk (entity co-occurrence) │
 │  4. ripgrep /opt/homebrew/bin/rg (docs)    │
 └─────────────────────────────────────────────┘
 │
 ▼
 INTENT DETECTION + FILTER CONSTRUCTION
 │
 ▼
 ┌──────────────────────────────────────┐
 │  LANCEDB HYBRID SEARCH (nutanix_rag_v3_dedup)  │
 │  • Vector (IvfHnswPq, 1024-dim)     │
 │  • FTS (BM25)                        │
 │  • RRF merge (k=60)                  │
 └──────────────────────────────────────┘
 │
 ▼
 GRAPH BOOST (Kuzu entity co-occurrence)
   +0.15 to rrf_score for graph-verified docs
 │
 ▼
 CONTEXT EXPANSION (±2 neighbor chunks)
 │
 ▼
 CROSS-ENCODER RERANK (Jina reranker-v3, top 30→5)
 │
 ▼
 SCORE MULTIPLIER (topic weight + KB + subcategory)
 │
 ▼
 CONFIDENCE FILTER (CE score < 0.1 AND mult ≤ 1.0 → discard)
 │
 ▼
 FALLBACK WATERFALL (if low confidence)
   → query_slack_fallback() via slack-search-mcp
   → query_web_search() via SearXNG
 │
 ▼
 format_results() → LLM-readable output
```

---

## LanceDB Table (nutanix_rag_v3_dedup)

- **Path:** `~/.openclaw/memory/lancedb-pro/nutanix_rag_v3_dedup.lance`
- **Rows:** ~85,642 (deduplicated from ~129K)
- **Size:** ~1.2 GB
- **Embedding:** Jina AI `jina-embeddings-v5-text-small` (1024 dims)
- **Indexes:** IvfHnswPq vector index, BM25 FTS index, BTree on scalar columns

**Schema:**

| Field | Type | Description |
|---|---|---|
| `text` | string | Chunk content, ~8000 chars per chunk |
| `vector` | float[1024] | Jina embedding |
| `source` | string | Full URL or file path |
| `rel_path` | string | Relative file path |
| `access_level` | string | `public` or `internal` |
| `doc_type` | string | e.g. `official_doc`, `kb_article`, `battlecard` |
| `primary_product` | string | e.g. `AHV`, `AOS`, `Prism`, `General` |
| `mentioned_products` | string[] | Nutanix products found in text |
| `ecosystem_entities` | string[] | Competitors/partners (VMware, Red_Hat, etc.) |
| `versions` | string[] | e.g. `["AOS_7.5"]` |
| `content_types` | string[] | e.g. `["troubleshooting", "architecture"]` |
| `chunk_index` | int | Position in source document |
| `content_hash` | string | File-level dedup hash |
| `chunk_hash` | string | Chunk-level dedup hash |

---

## Query Paths

| Agent | MCP Tool | Identity | Rate Limit |
|---|---|---|---|
| Sam | `sam-gateway__master_search` | `sam` (unrestricted) | 3 calls/turn |
| NX_Shield | `gateway-mcp__master_search` | `nx_shield` (public only) | 2 calls/turn |

Both MCP servers run `nx_gateway_mcp.py` → `nutanix_rag_search.py` subprocess with `--identity` flag.

---

## 11-Stage Pipeline (run_search)

| Stage | Function | Duration |
|---|---|---|
| P0 | Parallel: DeepSeek classify + Jina embed + Kuzu graph + ripgrep | ~1-2s |
| 1 | Intent detection + filter construction | ~0.01s |
| 2 | LanceDB hybrid search (vector + FTS + RRF) | ~0.5s |
| 3 | Fallback retry (if < 3 unique results) | — |
| 4 | Deduplicate by source (keep highest RRF) | — |
| 5 | **Graph Boost** — Kuzu entity match, +0.15 to rrf_score | ~0.1s |
| 6 | expand_for_rerank (±2 neighbor context via PyArrow) | **3-4s** |
| 7 | Jina cross-encoder rerank (top 30 → top 5) | ~1s |
| 8 | score_multiplier() — topic weight, KB#, subcategory boost | ~0.01s |
| 9 | Confidence filter (CE < 0.1 AND mult ≤ 1.0 → discard) | ~0.01s |
| 10 | Swap expanded text into `text` field | — |

**Total pipeline latency:** ~6-8s per query (warm)

---

## Stage-by-Stage Reference

### P0 — Parallel Execution (ThreadPoolExecutor, max_workers=4)

Three operations run simultaneously:

**1. DeepSeek topic classify**
- Primary classifier (was Gemma, changed 2026-05-13)
- Model: `deepseek-chat` via `api.deepseek.com`
- Timeout: 10s
- Falls back to keyword-based intent detection if DeepSeek fails
- Output: list of topic strings (e.g. `["AHV", "CLUSTER_SIZING"]`)

**2. Jina embed**
- `https://api.jina.ai/v1/embeddings`
- Model: `jina-embeddings-v5-text-small` (1024 dims)
- Timeout: 10s

**3. Kuzu graph walk**
- Queries `~/.openclaw/memory/kuzu-pro/nutanix_graph_v3/`
- Extracts entities connected to query terms via `(Chunk)-[r]->(Entity)` relationships
- Entity names match LanceDB's `ecosystem_entities` / `mentioned_products` columns
- Used for Graph Boost in Stage 5

**4. ripgrep (parallel with RAG)**
- Runs: `/opt/homebrew/bin/rg -F -n -i -- <query> <RAG_DOCS_DIR>`
- RAG_DOCS_DIR: `~/.openclaw/workspace/rag/nutanix/`
- Timeout: 15s
- Output: up to 15 lines (250 chars each), fed into `format_results()` alongside RAG
- ripgrep result is passed to `format_results()` as `rg_text` parameter

### Stage 1 — Intent Detection + Filter Construction

Dynamically builds LanceDB `.where()` filter conditions from query + detected intent + agent identity.

**Three filter layers, AND-combined:**

1. **Security boundary** — `access_level = 'public'` for NX_Shield (hard-coded, overrules everything)
2. **Dynamic entities** — `extract_ecosystem_entities()` + `extract_mentioned_products()` from `tagger_v3` at query time
3. **Intent routing** — based on keyword + entity detection:

| Intent | Condition | Filter |
|---|---|---|
| `COMPETITIVE` | `vs`, `compare`, `better`, or ecosystem entity | `doc_type IN ('battlecard', 'competitive_intel', 'official_doc')` |
| `TROUBLESHOOTING` | `error`, `fail`, `crash`, `bug`, etc. | `content_types IN ('troubleshooting', 'faq')` |
| `API_DEV` | `API`, `SDK`, `REST`, `endpoint`, `code` | `doc_type IN ('api_spec', 'official_doc', 'code_repo')` |
| `HARDWARE` | `NX-`, `G10`, `spec`, `model`, `hardware` | `doc_type IN ('reference', 'official_doc')` |

**Fallback:** If filtered results < 3 unique sources, retry with only the security boundary filter.

### Stage 2 — LanceDB Hybrid Search

Single hybrid search combining vector similarity + FTS via RRF merge:

```python
vector_q = t.search(emb_query).where(filter_str).refine_factor(2).limit(fetch_n)
fts_q = t.search(raw_query, query_type="fts").where(filter_str).limit(fetch_n)
results = rrf_merge([vector_r, fts_r], k=60)
```

### Stage 3 — Fallback Retry

If filtered search returns < 3 unique sources, retry with only `access_level` security filter (dropping product/type filters).

### Stage 4 — Deduplicate by Source

Keep highest RRF score when the same source appears multiple times.

### Stage 5 — Graph Boost (Kuzu)

```python
if graph_entities:
    for r in rrf_sorted:
        matched = [e for e in graph_entities if fuzzy_match(e, r)]
        if matched:
            r["rrf_score"] += 0.15  # structural co-occurrence bonus
            r["_graph_verified"] = True
```

- Kuzu entity names are granular (`NCC_GUIDE_V5_3`); LanceDB names are short (`NCC`)
- Fuzzy matching: checks both `e.upper() in p.upper()` and vice versa

### Stage 6 — Context Expansion (expand_for_rerank)

Same as before — replaces each hit's chunk with ±2 neighboring chunks from the same document. Uses PyArrow column iteration — no vector search.

**Window:** ±2 chunks per side. **Duration: 3-4s** (main latency driver).

### Stage 7 — Cross-Encoder Rerank (Jina reranker-v3)

Jina's hosted listwise reranker scores semantic relevance. Falls back to RRF scores if all CE scores are 0.

### Stage 8 — Score Multiplier

**Three boost signals (applied to CE score or RRF if CE failed):**

| Signal | Condition | Multiplier |
|---|---|---|
| KB# exact match | KB number found in source or text | up to 1.3× |
| Subcategory match | doc's `primary_product` matches topic's subcategory | up to 1.15× |
| Products match | doc's `mentioned_products` intersect topic's products | up to 1.2× |

**Cap:** 1.4× maximum to preserve CE semantic primacy.

**Note:** Topics from DeepSeek/Gemma are used ONLY for score boosting in Stage 8. They do NOT route search — the embedding handles query semantics, filters handle metadata routing. If topic classification fails entirely, search works normally with `topic_weight=1.0`.

### Stage 9 — Confidence Filter

- Filters out results where CE score < 0.1 AND multiplier <= 1.0
- Swaps `_expanded_text` into main `text` field for LLM delivery
- Returns top 5 results with scores, citations, and expanded context

### Stage 10 — Format + Fallback Waterfall

`format_results()` is called from `main()` with both RAG results and ripgrep text. If RAG confidence is low (all CE scores < 0.10):

1. **Slack fallback** — `slack-search-mcp__slack_search` via port 8005
2. **SearXNG web fallback** — `http://127.0.0.1:8888/search` with allowed domains filter

---

## Topic Classifier (DeepSeek, not Gemma)

**Was Gemma, updated 2026-05-13.** DeepSeek is now the primary topic classifier:

```python
# config.py
CLASSIFIER_MODEL = "deepseek"  # was "gemma"
DEEPSEEK_API_KEY = "..."
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TIMEOUT = 10
```

Gemma (local LM Studio on MacBook at `100.74.228.94:1234`) is retained as a **local fallback** if the DeepSeek API is unreachable. The `tagger_v3` keyword patterns always work as a final fallback.

---

## Ripgrep (Parallel with RAG)

Ripgrep runs in parallel with the RAG search in `main()`. It uses the **Homebrew-installed rg** (`/opt/homebrew/bin/rg`), not the system `rg`:

```bash
/opt/homebrew/bin/rg -F -n -i -- "<query>" ~/.openclaw/workspace/rag/nutanix/
```

Ripgrep results (`rg_text`) are passed directly to `format_results()` and injected into the LLM output alongside RAG results — not merged into the RAG candidate pool.

---

## Confidence and the Fallback Waterfall

```
RAG confidence OK?
  ├── YES → return top 5 RAG results (+ ripgrep context)
  └── NO (all CE scores < 0.10) → Slack fallback
        ├── Slack has results? → return Slack results
        └── Slack empty? → SearXNG web fallback
              ├── Web has results? → return Web results
              └── All failed → return "No results found"
```

Ripgrep results are always included in the output regardless of RAG confidence — they serve as additional lexical context.

---

## Key Data Structures

### `INTENT_FILTER_MAP`
Maps 4 intent buckets to `doc_type` / `content_type` filters. Applied dynamically based on keyword detection.

### `_INTENT_PATTERNS`
Keyword regex patterns for intent detection: COMPETITIVE, TROUBLESHOOTING, API_DEV, HARDWARE.

### `TOPIC_WEIGHTS`
Maps topic → float multiplier. Used in Stage 8 for post-hoc score boosting.

### `SUBJECT_PRODUCTS_MAP`
Maps topic → relevant products. Used in `score_multiplier()` for products-match boost.

### `SUBJECT_SUBCAT_MAP`
Maps topic → subcategory string. Used in `score_multiplier()` for subcategory-match boost.

### `_KB_MAP`
Maps topic → KB article number. Used in `score_multiplier()` to boost KB-matching results.

---

## Runtime Infrastructure

| Component | Host | Notes |
|---|---|---|
| LanceDB + search | Mac mini | `nutanix_rag_v3_dedup` |
| Kuzu graph DB | Mac mini | `nutanix_graph_v3` |
| DeepSeek API | Cloud | Topic classification primary |
| Jina Embed API | Cloud (api.jina.ai) | Vectorization |
| Jina Rerank API | Cloud (api.jina.ai) | Semantic reranking |
| SearXNG | Mac mini (:8888) | Web search fallback |
| Slack MCP | Mac mini (:8005) | Slack search fallback |
| OpenClaw gateway | Mac mini | Agent orchestration |

---

## LanceDB Backup

The LanceDB database is included in the daily OpenClaw backup (3 AM). Backup tar archives `~/.openclaw/` which contains both the LanceDB directory and source document repository.

**Manual backup:**
```bash
tar -czf ~/rag_backups/nutanix_rag_v3_dedup-$(date +%Y%m%d).tar.gz \
  ~/.openclaw/memory/lancedb-pro/nutanix_rag_v3_dedup.lance/
```

**Restore:**
```bash
tar -xzf YYYYMMDD-openclaw-backup.tar.gz -C /Users/ipccheng/
```

---

## Changelog

### 2026-05-13
- **Full pipeline rewrite** — docs were reverted to previous architecture
- Updated classifier: Gemma → **DeepSeek** (primary)
- Updated pipeline stages: 7 → **11 stages** (added parallel ripgrep, graph boost stage, confidence filter stage)
- Added ripgrep documentation (Stage P0-4)
- Added Slack and SearXNG fallback waterfall documentation
- Added `format_results()` confidence-based fallback flow
- Updated Kuzu boost documentation (Stage 5, +0.15 to RRF before CE)
- Clarified topic classifier is for boosting ONLY, not routing
- Updated rerank_top: Sam 50→5, NX_Shield 30→5
- Updated table references: `nutanix_rag_v3` → `nutanix_rag_v3_dedup`

### 2026-05-12
- Added Kuzu graph DB integration for entity-based boosting
- Deduplication: ~129K → ~85K chunks
