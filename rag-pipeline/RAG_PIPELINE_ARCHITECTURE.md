# NX_Shield RAG Pipeline — Architecture & Documentation

> **Last updated:** 2026-05-12
> **Status:** Active

---

## Overview

This document describes the Nutanix technical knowledge base RAG (Retrieval-Augmented Generation) pipeline. It is used by **Sam** and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

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
+-- Battlecards / competitive intelligence (xpress-md)
+-- Local PDFs (MarkItDown -> markdown)
|
v
INGESTION PIPELINE
|
+-- embed_pipeline_v3.py (chunking + embedding + inline tagging via tagger_v3)
|
v
KUZU GRAPH (nutanix_rag_v3_dedup — ~85K rows, ~800MB)
|
+-- Vector index (Hnsw, 1024-dim, edge 16)
+-- BM25 FTS index (on text)
+-- Scalar indices (access_level, doc_type, primary_product, source, rel_path)
+-- Graph topology (chunk → neighbor links via PyArrow)
|
v
QUERY INTERFACE
|
+-- Sam: direct Python exec run_search()
+-- NX_Shield: MCP protocol via mcp_server.py (port 8001 with identity=nx_shield)
|
v
run_search() [5-stage pipeline]
|
+-- Stage 1: Intent detection + filter construction (keyword + entities)
+-- Stage 2: Jina embed (api.jina.ai, 1024-dim)
+-- Stage 3: Kuzu hybrid search (vector + FTS + RRF with dynamic filters)
+-- Stage 4: expand_for_rerank (±2 neighbor context via PyArrow)
+-- Stage 5: Jina cross-encoder rerank (top 30 → top 5)
+-- Stage 6: score_multiplier() + subcategory/product boost from DeepSeek topics
+-- Stage 7: format_results() -> LLM-readable output
|
v
format_results() -> LLM-readable output
```

### Kuzu Graph Database

**Switched from LanceDB to Kuzu** for better graph traversal and relationship-aware retrieval.

- **Path:** `~/.openclaw/memory/lancedb-pro/nutanix_rag_v3_dedup.kuzu`
- **Rows:** ~85,000 (deduplicated)
- **Size:** ~800 MB
- **Embedding:** Jina AI `jina-embeddings-v5-text-small` (1024 dims)
- **Indexes:** Hnsw vector index, BM25 FTS index, BTree on scalar columns

**Schema:**

| Field | Type | Description |
|---|---|---|
| `text` | string | Chunk content, ~8000 chars per chunk |
| `vector` | float[1024] | Jina embedding |
| `source` | string | Full URL or file path |
| `rel_path` | string | Relative file path |
| `access_level` | string | `public` or `internal` |
| `doc_type` | string | e.g. `official_doc`, `kb_article`, `battlecard`, `api_spec` |
| `primary_product` | string | e.g. `AHV`, `AOS`, `Prism`, `General` |
| `mentioned_products` | string[] | e.g. `["AHV", "AOS"]` |
| `ecosystem_entities` | string[] | e.g. `["Red_Hat", "VMware"]` |
| `versions` | string[] | e.g. `["AOS_7.5"]` |
| `content_types` | string[] | e.g. `["troubleshooting", "architecture"]` |
| `chunk_index` | int | Position in source document |
| `content_hash` | string | Content dedup hash |
| `chunk_hash` | string | Chunk-level dedup hash |

### Query Paths

| Agent | Method | MCP Server | Identity |
|---|---|---|---|
| Sam | Direct Python exec | `rag-mcp-server-sam` (port 8004) | unrestricted |
| NX_Shield | MCP protocol | `rag-mcp-server` (port 8001) | `nx_shield` (public-only) |

### Pipeline Overview

| Stage | Function | Input | Output | Duration |
|---|---|---|---|---|
| 1 | Intent detection + filter build | query | intents + filter conditions | ~0.01s |
| 2 | Jina embed | query | emb (1024-dim) | ~1s |
| 3 | Kuzu hybrid search | query + emb + filters | top 30 candidates | ~0.5s |
| 4 | expand_for_rerank | candidates | `_expanded_text` (~24K chars) | **3-4s** |
| 5 | Jina CE rerank | `_expanded_text` | reranked top 5 | ~1s |
| 6 | Score multiplier + confidence filter | CE scores | boosted scores | ~0.01s |
| 7 | format_results() | boosted scores | formatted output | ~0.01s |

**Total pipeline latency:** ~6-8s per query (warm)

---

## Stage-by-Stage Reference

### Stage 1 — Intent Detection + Filter Construction

**Purpose:** Dynamically build Kuzu `.get` filter conditions from the user query, detected intent, and agent identity. No hardcoded search strings — the raw user query drives the embedding.

**Three filter layers, combined as AND:**

1. **Security boundary** — `access_level = 'public'` for NX_Shield (hard-coded, overrules everything)
2. **Dynamic entities** — `extract_ecosystem_entities()` + `extract_mentioned_products()` from tagger_v3 at query time
3. **Intent routing** — based on keyword + entity detection:

| Intent | Condition | Filter |
|---|---|---|
| `COMPETITIVE` | `vs`, `compare`, `better`, or any ecosystem entity | `doc_type IN ('battlecard', 'competitive_intel', 'official_doc')` |
| `TROUBLESHOOTING` | `error`, `fail`, `crash`, `bug`, etc. | `content_types IN ('troubleshooting', 'faq')` |
| `API_DEV` | `API`, `SDK`, `REST`, `endpoint`, `code` | `doc_type IN ('api_spec', 'official_doc', 'code_repo')` |
| `HARDWARE` | `NX-`, `G10`, `spec`, `model`, `hardware` | `doc_type IN ('reference', 'official_doc')` |

**Fallback:** If filtered results < 3, retry with only the security boundary filter.

### Stage 2 — Embedding

The raw user query is embedded via Jina AI. No topic-specific search strings are concatenated.

**`jina_embed(query)` → `[0.0123, -0.0456, ...]` (1024 floats)**
- **Endpoint:** `https://api.jina.ai/v1/embeddings`
- **Model:** `jina-embeddings-v5-text-small` (1024 dimensions)
- **Timeout:** 10s

### Stage 3 — Hybrid Search (Kuzu)

Single vector + FTS query against the filtered Kuzu graph.

```python
# Filters built dynamically in Stage 1:
filter_str = "access_level = 'public' AND array_has_any(ecosystem_entities, ['Red_Hat'])"

# Single search with graph traversal:
vector_q = graph.search(emb_query).where(filter_str).limit(fetch_n)
fts_q = graph.search(raw_query, query_type="fts").where(filter_str).limit(fetch_n)

# RRF merge combines both:
results = rrf_merge([vector_q, fts_q], k=60)
```

**DeepSeek topic classification** runs in parallel but is used ONLY for `score_multiplier()` boosting.

### Stage 4 — Context Expansion (`expand_for_rerank`)

Replaces each hit's chunk (~8000 chars) with ±2 neighboring chunks from the same document.
**Window:** ±2 chunks per side. Uses PyArrow column iteration.

### Stage 5 — Cross-Encoder Rerank (`jina_rerank`)

Jina's hosted listwise reranker scores semantic relevance. Falls back to RRF scores if all CE scores are 0.

### Stage 6 — Score Multiplier (`score_multiplier`)

Topics from DeepSeek classification are used for post-hoc score boosting.

| Signal | Condition | Multiplier |
|---|---|---|
| KB# exact match | KB number found in source or text | up to 1.3× |
| Subcategory match | doc's `primary_product` matches topic's subcategory | up to 1.15× |
| Products match | doc's `mentioned_products` intersect topic's products | up to 1.2× |

**Cap:** 1.4× maximum to preserve CE semantic primacy.

### Stage 7 — Confidence Filter + Output

- Filters out results where CE score < 0.1 AND multiplier <= 1.0
- Swaps `_expanded_text` into main `text` field for LLM delivery
- Returns top 5 results with scores, citations, and expanded context

---

## NX_Shield Query Flow

NX_Shield follows a tiered search strategy:

1. **RAG (max 2 calls)** → `rag-mcp-server__query_nutanix_docs`
2. **Source Search / Re-query** → Re-query RAG with different keywords OR read local files
3. **Slack (max 1)** �� `slack-search-mcp__slack_search`
4. **Web (max 1)** → `web-search-filtered__web_search_filtered`

### MCP Servers for NX_Shield

| Server | Port | Tool |
|---|---|---|
| `rag-mcp-server` | 8001 | `rag-mcp-server__query_nutanix_docs` |
| `slack-search-mcp` | 8005 | `slack-search-mcp__slack_search` |
| `web-search-filtered` | 8003 | `web-search-filtered__web_search_filtered` |

---

## Runtime Infrastructure

| Component | Host | Notes |
|---|---|---|
| Kuzu + search | Primary runtime | nutanix_rag_v3_dedup |
| DeepSeek API | Cloud (api.deepseek.com) | Topic classification |
| Jina Embed API | Cloud (api.jina.ai) | Vectorization |
| Jina Rerank API | Cloud (api.jina.ai) | Semantic reranking |
| OpenClaw gateway | Host | Agent orchestration |

### MCP Server Architecture (Dual-Instance)

| Server | Port | Identity | Used By |
|---|---|---|---|
| `rag-mcp-server` | 8001 | `nx_shield` | NX_Shield (public only) |
| `rag-mcp-server-sam` | 8004 | `sam` | Sam (full access) |

---

## Changelog

### 2026-05-12
- Switched from LanceDB to **Kuzu** graph database for better graph traversal
- Added deduplicated index: **nutanix_rag_v3_dedup** (~85K rows, ~800MB)
- Replaced Gemma with **DeepSeek** for topic classification
- Added keyword fallbacks: NKP, NAI → topic mapping in QUERY_CLASSIFIERS
- Added NX_Shield MCP tools: `slack-search-mcp`, `web-search-filtered`
- Updated pipeline latency: **~6-8s per query**
- Total rows: 170,708 (full) → 85,000 (deduplicated)

### 2026-05-03
- Added `expand_for_rerank` fix (PyArrow iteration) — 54s → 3-4s
- Added pre-filtering logic updates

### 2026-04-27
- Refactored pipeline to single hybrid search (was per-topic parallel)
- Fixed `expand_for_rerank` deadlock issue
- Updated GEMMA_TIMEOUT from 10s → 3s
