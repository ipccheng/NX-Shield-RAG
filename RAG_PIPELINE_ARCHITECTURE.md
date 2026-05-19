# NX_Shield RAG Pipeline — Architecture & Documentation

> **Last updated:** 2026-05-19
> **Status:** Active
> **Script:** `nutanix_rag_search.py` (workspace/scripts/)
> **MCP Backend:** `universal_gateway_mcp.py` → `nutanix_rag_search.py` subprocess via `subprocess.run()`

---

## Overview

This document describes the Nutanix technical knowledge base RAG (Retrieval-Augmented Generation) pipeline used by **Sam**, **Neo**, and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

The pipeline performs intent classification + query recomposition via DeepSeek, then runs parallel embedding and multi-channel search. **Two routing modes:**

- **[SINGLE]** — generates 3 linguistic rewrites of the original query; each rewrite acts as a tiebreaker at low weight (0.3)
- **[COMPARISON]** — decomposes "A vs B" / "differences between X and Y" queries into 2–4 distinct sub-queries, one per product or approach; each sub-query runs as a primary search at full weight (1.0) with both Vector and FTS

Ripgrep runs in parallel with the RAG search. Fallback waterfall: Slack CLI → SearXNG web search on low confidence.

---

## System Architecture

### High-Level Flow

```
QUERY
 │
 ▼
 ┌──────────────────────────────────────────────────────────────┐
 │  PARALLEL Stage 1 (ThreadPoolExecutor, max_workers=3)       │
 │  1. DeepSeek topic classify                                 │
 │  2. LLM routing — generate_routing() → intent + queries    │
 │  3. Kuzu graph walk (entity co-occurrence)                 │
 └──────────────────────────────────────────────────────────────┘
 │
 ▼
 jina_embed_batch([orig + 3 variants])  ← 1 API call
 │
 ▼
 ┌──────────────────────────────────────────────────────────────┐
 │  PARALLEL Stage 2 (search channels, ThreadPoolExecutor)   │
 │                                                              │
 │  [SINGLE] mode:                                             │
 │    Channel 1: Original → Vector search    (weight=1.0)      │
 │    Channel 2: Original → FTS search       (weight=1.0)     │
 │    Channel 3–5: Rewrites 1–3 → Vector   (weight=0.3 each) │
 │                                                              │
 │  [COMPARISON] mode:                                         │
 │    Original → de-prioritised (weight=0.3)                   │
 │    Each sub-query ×2: Vector (1.0) + FTS (1.0)            │
 │                                                              │
 │  → rrf_merge(channel_weights=[...])                         │
 │    Accumulation key: chunk_hash (not source)                │
 │    Post-RRF dedup: keep highest rrf_score per source        │
 └──────────────────────────────────────────────────────────────┘
 │
 ▼
 FALLBACK RETRY (if < 3 unique results) — security-only filter
 │
 ▼
 GRAPH BOOST (Kuzu entity co-occurrence)
   +0.15 to rrf_score for graph-verified docs
 │
 ▼
 expand_for_rerank (±2 neighbor chunks via t.to_arrow())
 │
 ▼
 CROSS-ENCODER RERANK (Jina reranker-v3, top 50→5)
 │
 ▼
 score_multiplier() — KB#, subcategory, products, mentioned_products
 │
 ▼
 CONFIDENCE FILTER (CE score < 0.1 AND mult ≤ 1.0 → discard)
 │
 ▼
 FALLBACK WATERFALL (if low confidence)
   → query_slack_fallback() via slk CLI
   → query_web_search() via SearXNG direct HTTP
 │
 ▼
 ripgrep (parallel with RAG — not in pipeline, fed to format_results)
 │
 ▼
 format_results() → LLM-readable output
```

---

## LanceDB Table (nutanix_rag_v3_dedup)

- **Path:** `~/.openclaw/memory/lancedb-pro/nutanix_rag_v3_dedup.lance`
- **Rows:** ~71,765 (deduplicated from ~129K — dedup ran 2026-05-14)
- **Size:** ~1.2 GB
- **Embedding:** Jina AI `jina-embeddings-v5-text-small` (1024 dims)
- **Indexes:** IVF_HNSW_SQ vector index (metric=cosine, m=20, ef=300), BM25 FTS index, BTree on scalar columns

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
| `chunk_index` | int | Position in source document (`None` for unchunked docs) |
| `content_hash` | string | File-level dedup hash |
| `chunk_hash` | string | Chunk-level dedup hash |

---

## Query Paths

All agents route through the same MCP gateway on their respective host:

| Agent | MCP Tool | Host | Identity | Rate Limit |
|---|---|---|---|---|
| Neo | `neo__master_search` | MacBook :8010 | `neo` | 3 calls/turn |
| Sam | `sam-gateway__master_search` | Mac mini :8010 | `sam` | 3 calls/turn |
| NX_Shield | `gateway-mcp__master_search` | Mac mini :8010 | `nx_shield` (public only) | 2 calls/turn |

All MCP servers run `universal_gateway_mcp.py` → `nutanix_rag_search.py` subprocess via Python `subprocess.run()`.

---

## 13-Stage Pipeline (run_search)

| Stage | Function | Duration |
|---|---|---|
| S1 | Parallel: DeepSeek classify + generate_routing + Kuzu graph | ~1-2s |
| S2 | jina_embed_batch — 1 API call, 4 vectors (orig + 3 rewrites) | ~0.5s |
| S3 | Multi-channel parallel LanceDB search (mode-dependent) | ~0.3s |
| S4 | RRF merge with channel_weights + chunk_hash accumulation + source dedup | ~0.01s |
| S5 | Fallback retry (if < 3 unique sources) — security-only filter | — |
| S6 | **Graph Boost** — Kuzu entity match, +0.15 to rrf_score | ~0.1s |
| S7 | expand_for_rerank (±2 neighbor context via t.to_arrow()) | **~0.2s** |
| S8 | Jina cross-encoder rerank (top 50 → top 5) | ~1s |
| S9 | score_multiplier() — KB#, subcategory, products, mentioned_products | ~0.01s |
| S10 | Confidence filter (CE < 0.1 AND mult ≤ 1.0 → discard) | ~0.01s |
| S11 | Swap expanded text into `text` field | — |
| S12 | ripgrep (parallel with S1-S3 via ThreadPoolExecutor) | ~0.5s |
| S13 | format_results() + fallback waterfall | — |

**Total pipeline latency:** ~2.5-3.5s per query (warm) — significantly faster than the old 6-8s.

---

## Stage-by-Stage Reference

### S1 — Parallel Prep (ThreadPoolExecutor, max_workers=3)

Three operations run simultaneously:

**1. DeepSeek topic classify**
- Model: `deepseek-chat` via `api.deepseek.com`
- Timeout: 10s
- Falls back to keyword-based intent detection if DeepSeek fails
- Output: list of topic strings (e.g. `["AHV", "CLUSTER_SIZING"]`)

**2. LLM routing — generate_routing()**
- Single-pass DeepSeek call returns `{"intent": "single"|"comparison", "queries": [...]}`
- `[SINGLE]`: generates 3 linguistic rewrites — tiebreakers at weight 0.3
- `[COMPARISON]`: decomposes into 2–4 sub-queries, one per product/approach — each a primary search at weight 1.0
- Regex + JSON fallback on parse failure
- One LLM call = zero extra latency vs. old generate_rewrites() approach

**3. Kuzu graph walk**
- Opens `~/.openclaw/memory/kuzu-pro/nutanix_graph_v3/` as embedded library (no daemon required)
- Extracts entities connected to query terms via `(Chunk)-[r]->(Entity)` relationships
- Entity names match LanceDB's `ecosystem_entities` / `mentioned_products` columns
- Used for Graph Boost in Stage S6
- **Verified data:** 71,765 Chunk nodes, 49,075 Entity nodes, 336,886 HAS_RELATIONSHIP edges

### S2 — Batch Embedding (jina_embed_batch)

All queries are embedded in a **single Jina API call**:

```
POST https://api.jina.ai/v1/embeddings
{"model": "jina-embeddings-v5-text-small", "input": [orig, rw1, rw2, rw3]}
```

Returns vectors in the same order as input. If rewrites fail, fewer vectors are returned — the pipeline adapts dynamically.

### S3 — Multi-Channel Parallel Search

**[SINGLE] mode** — 5 channels:

| Channel | Query | Method | Weight |
|---|---|---|---|
| 1 | Original | Vector | 1.0 |
| 2 | Original | FTS (BM25) | 1.0 |
| 3–5 | Rewrites 1–3 | Vector | 0.3 each |

**[COMPARISON] mode** — channels vary by sub-query count:

- Original query: Vector + FTS at **0.3** (de-prioritised — "A vs B" mixed results are noise)
- Each sub-query: Vector + FTS at **1.0** each (each product/approach gets a clean primary search)
- Total channels: `2 + (subqueries × 2)`

**No FTS on rewrites** — saves ~60% LanceDB I/O. Vector-only is sufficient for rewrite channels.

**Bug #2217 workaround:** Query is cleaned (`re.sub(r'[^\w\s]', '', query)`) before FTS to avoid LanceDB's empty/short-query FTS crash. If cleaned query < 2 chars, returns early with a helpful error.

### S4 — RRF Merge with Channel Weights

```python
rrf_merge(results_by_method, k=60, channel_weights=[...])  # mode-dependent
```

**Accumulation key: chunk_hash** (not `source`). The same paragraph appearing in multiple search channels gets a compounded RRF boost. The CE pool still sees one representative doc per chunk_hash.

**Post-RRF dedup by source:** Keeps the highest rrf_score per file. This ensures the CE pool has diverse file coverage — multiple pages from the same file won't dominate just because one paragraph ranked highly.

### S5 — Fallback Retry

If filtered search returns < 3 unique sources, retry with only the `access_level` security filter (dropping product/type filters).

### S6 — Graph Boost (Kuzu)

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

### S7 — Context Expansion (expand_for_rerank)

Expands ±2 neighboring chunks around each result. Uses `t.to_arrow()` with in-memory PyArrow filtering — not a `.where()` pushdown. This approach is immune to LanceDB Bug #2217 and takes ~0.2s (not the 54s deadlock that occurred when called from within LanceDB's async loop).

```python
arr = t.to_arrow()
# Filter: rel_path IN paths_set AND chunk_index BETWEEN i-2 AND i+2
# Builds per-file chunk index via column iteration
# Stitches window into r["_expanded_text"] (up to ~32K chars for reranker)
```

### S8 — Cross-Encoder Rerank (Jina reranker-v3)

Jina's hosted listwise reranker scores semantic relevance. Falls back to RRF scores if all CE scores are 0.

### S9 — Score Multiplier

**Four boost signals:**

| Signal | Condition | Multiplier |
|---|---|---|
| KB# exact match | KB number in source URL | up to 1.3× |
| KB# text match | KB number in chunk text | up to 1.15× |
| KB doc boost | `kb-` in source URL | 1.1× |
| Subcategory match | doc's `primary_product` matches topic's subcategory | 1.15× |
| **mentioned_products safeguard** | doc has zero `mentioned_products` | **0.85×** |
| Products match | doc's `mentioned_products` intersect topic's products | 1.2× |

> ⚠️ **mentioned_products safeguard (2026-05-15):** Replaced the old 0.75× `General` primary_product penalty. A legitimate broad doc (e.g., "Nutanix General Overview") will still have `mentioned_products = ["AHV", "AOS"]` from the tagger. The 0.85× penalty catches ingestion bugs where the parser completely failed to extract any product metadata.

**Cap:** 1.4× maximum to preserve CE semantic primacy.

### S10 — Confidence Filter

- Filters out results where CE score < 0.1 AND multiplier ≤ 1.0
- Swaps `_expanded_text` into main `text` field for LLM delivery

### S11 — Format + Fallback Waterfall

`format_results()` called from `main()` with both RAG results and ripgrep text. If RAG confidence is low (all CE scores < 0.10):

1. **Slack fallback** — `slk search` CLI subprocess (direct call, not MCP)
2. **SearXNG web fallback** — direct HTTP POST to `http://127.0.0.1:8888` (not MCP)

### S12 — Ripgrep (Parallel)

Ripgrep runs in parallel with the RAG search via a separate `ThreadPoolExecutor(max_workers=4)`. It uses the **Homebrew-installed rg** (`/opt/homebrew/bin/rg`):

```bash
/opt/homebrew/bin/rg -F -n -i -- "<query>" ~/.openclaw/workspace/rag/nutanix/
```

Ripgrep results (`rg_text`) are passed directly to `format_results()` and injected into the LLM output alongside RAG results — not merged into the RAG candidate pool.

---

## Key Data Structures

### `INTENT_FILTER_MAP`
Maps 4 intent buckets to `doc_type` / `content_type` filters. Applied dynamically based on keyword detection.

### `_INTENT_PATTERNS`
Keyword regex patterns for intent detection: COMPETITIVE, TROUBLESHOOTING, API_DEV, HARDWARE.

### `TOPIC_WEIGHTS`
Maps topic → float multiplier. Used in Stage S9 for post-hoc score boosting.

### `SUBJECT_PRODUCTS_MAP`
Maps topic → relevant products. Used in `score_multiplier()` for products-match boost.

### `SUBJECT_SUBCAT_MAP`
Maps topic → subcategory string. Used in `score_multiplier()` for subcategory-match boost.

### `_KB_MAP`
Maps topic → KB article number. Used in `score_multiplier()` to boost KB-matching results.

### Channel Weights
Mode-dependent — `[SINGLE]`: `[1.0, 1.0, 0.3, 0.3, 0.3]`; `[COMPARISON]`: `[0.3] + [1.0, 1.0] × N_subqueries`.

---

## Runtime Infrastructure

| Component | Host | Notes |
|---|---|---|
| LanceDB + search | MacBook + Mac mini | `nutanix_rag_v3_dedup`, synced via rsync |
| Kuzu graph DB | MacBook + Mac mini | `nutanix_graph_v3` — embedded library, opened in-process per query (no daemon) |
| DeepSeek API | Cloud | Topic classification + query routing |
| Jina Embed API | Cloud (api.jina.ai) | Batch vectorization (4 vectors/call) |
| Jina Rerank API | Cloud (api.jina.ai) | Semantic reranking |
| SearXNG | Mac mini (:8888) | Web search fallback — direct HTTP |
| Slack | MacBook | `slk search` CLI subprocess (direct call) |
| OpenClaw gateway | MacBook + Mac mini | Agent orchestration |

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

### 2026-05-19 — Intent Routing + Documentation Corrections
- **generate_routing()** — replaces generate_rewrites(): single-pass DeepSeek call returns `{intent, queries}` dict; zero extra latency
- **[SINGLE] mode** — 3 linguistic rewrites as tiebreakers (0.3 weight); 5-channel search unchanged from prior doc
- **[COMPARISON] mode** — decomposes "A vs B" queries into 2–4 sub-queries; each runs Vector + FTS at 1.0; original query de-prioritised to 0.3
- **Kuzu** — confirmed working as embedded library (no daemon). Database verified: 71,765 Chunk nodes, 49,075 Entity nodes, 336,886 HAS_RELATIONSHIP edges
- **Slack fallback** — corrected from MCP reference to direct `slk search` CLI subprocess call
- **Web fallback** — clarified as direct HTTP to SearXNG (:8888), not MCP
- **S3 channel weights** — documented mode-dependent weights; COMPARISON mode skips fixed 5-channel assumption
- **Runtime Infrastructure** — Kuzu row updated to clarify embedded library pattern (no daemon)

### 2026-05-15 — Query Recomposition Pipeline
- **generate_rewrites()** — new function: DeepSeek LLM generates 3 rewrite phrases per query; regex fallback if JSON parse fails
- **jina_embed_batch()** — new function: batches all 4 queries (1 orig + 3 rewrites) into 1 Jina API call
- **5-channel search architecture** — 1 orig Vec (1.0) + 1 orig FTS (1.0) + 3 rewrite Vec (0.3 each), run in parallel
- **rrf_merge() updated** — `channel_weights` parameter; chunk_hash as accumulation key; post-RRF source dedup
- **score_multiplier()** — replaced 0.75× General penalty with 0.85× `mentioned_products` empty safeguard
- **expand_for_rerank()** — now uses `t.to_arrow()` approach (~0.2s), immune to LanceDB async deadlock
- **Bug #2217 workaround** — short/empty queries cleaned before FTS; <2 chars returns error early

### 2026-05-13 — DeepSeek Classifier
- **Topic classifier:** Gemma → **DeepSeek** (primary); Gemma retained as local fallback
- **11-stage pipeline** documented

### 2026-05-12 — Kuzu Graph Integration
- Added Kuzu graph DB for entity-based boosting
- Deduplication: ~129K → ~85K chunks
