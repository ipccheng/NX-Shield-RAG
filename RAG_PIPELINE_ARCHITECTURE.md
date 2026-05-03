# NX_Shield RAG Pipeline — Architecture & Documentation

> **Last updated:** 2026-05-03
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
+-- embed_pipeline_v2.py (chunking + embedding)
+-- tagger_v3.py (metadata enrichment)
|
v
LANCEDB (nutanix_rag_v3 — 129,732 rows, ~1.2 GB)
|
+-- Vector index (IvfHnswPq, 1024-dim)
+-- BM25 FTS index (on text)
+-- Scalar indices (access_level, doc_type, primary_product, source, rel_path)
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
+-- Stage 3: LanceDB hybrid search (vector + FTS + RRF with dynamic filters)
+-- Stage 4: expand_for_rerank (±2 neighbor context via PyArrow)
+-- Stage 5: Jina cross-encoder rerank (top 30 → top 5)
+-- Stage 6: score_multiplier() + subcategory/product boost from Gemma topics
+-- Stage 7: format_results() -> LLM-readable output
|
v
format_results() -> LLM-readable output
```

### LanceDB Table (nutanix_rag_v3)

- **Path:** `nutanix_rag_v3` in LanceDB
- **Rows:** 129,732
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
| 3 | LanceDB hybrid search | query + emb + filters | top 30 candidates | ~0.5s |
| 4 | expand_for_rerank | candidates | `_expanded_text` (~24K chars) | **3-4s** |
| 5 | Jina CE rerank | `_expanded_text` | reranked top 5 | ~1s |
| 6 | Score multiplier + confidence filter | CE scores | boosted scores | ~0.01s |
| 7 | format_results() | boosted scores | formatted output | ~0.01s |

**Total pipeline latency:** ~6-8s per query (warm) — down from ~60s after expand_for_rerank fix

---

## Stage-by-Stage Reference

---

### Stage 1 — Intent Detection + Filter Construction

**Purpose:** Dynamically build LanceDB `.where()` filter conditions from the user query, detected intent, and agent identity. No hardcoded search strings — the raw user query drives the embedding.

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

**Entity extraction examples:**

```python
extract_ecosystem_entities("compare Redhat AI with NAI")
# → ["Red_Hat"]
# → adds: WHERE array_has_any(ecosystem_entities, ['Red_Hat'])

extract_mentioned_products("AHV networking VLAN config")
# → ["AHV"]
# → adds: WHERE array_has_any(mentioned_products, ['AHV'])
```

---

### Stage 2 — Embedding

The raw user query is embedded via Jina AI. No topic-specific search strings are concatenated — the embedding model understands the query's semantics natively.

**`jina_embed(query)` → `[0.0123, -0.0456, ...]` (1024 floats)**

- **Endpoint:** `https://api.jina.ai/v1/embeddings`
- **Model:** `jina-embeddings-v5-text-small` (1024 dimensions)
- **Timeout:** 10s

---

### Stage 3 — Single Hybrid Search

Unlike the previous per-topic parallel search approach, the search is now a single vector + FTS query against the filtered LanceDB pool.

```python
# Filters built dynamically in Stage 1:
filter_str = "access_level = 'public' AND array_has_any(ecosystem_entities, ['Red_Hat']) AND doc_type IN ('battlecard', 'competitive_intel', 'official_doc')"

# Single search with the raw user embedding:
vector_q = t.search(emb_query).where(filter_str).refine_factor(2).limit(fetch_n)
fts_q = t.search(raw_query, query_type="fts").where(filter_str).limit(fetch_n)

# RRF merge combines both:
results = rrf_merge([vector_r, fts_r], k=60)
```

**Key advantage:** No per-topic keyword dictionary to maintain. No search strings to guess. The embedding handles query semantics, filters handle metadata routing.

**Gemma topic classification** still runs in parallel but is used ONLY for `score_multiplier()` boosting (not search routing). This means if Gemma times out or the endpoint is unreachable, search still works perfectly — only the scoring boost is lost.

---

### Stage 4 — Context Expansion (`expand_for_rerank`)

Same as before — replaces each hit's tiny chunk (~8000 chars) with ±2 neighboring chunks from the same document. Gives the cross-encoder full localized context.

**Window:** ±2 chunks per side. Uses PyArrow column iteration — no vector search.

---

### Stage 5 — Cross-Encoder Rerank (`jina_rerank`)

Same as before — Jina's hosted listwise reranker scores semantic relevance. Falls back to RRF scores if all CE scores are 0.

---

### Stage 6 — Score Multiplier (`score_multiplier`)

Same signal structure as before, but topics from Gemma classification are used as a **secondary scoring signal**, not primary routing. If Gemma is offline, the multiplier defaults to 1.0 (no boost), but search still works.

**Three boost signals:**

| Signal | Condition | Multiplier |
|---|---|---|
| KB# exact match | KB number found in source or text | up to 1.3× |
| Subcategory match | doc's `primary_product` matches topic's subcategory | up to 1.15× |
| Products match | doc's `mentioned_products` intersect topic's products | up to 1.2× |

**Cap:** 1.4× maximum to preserve CE semantic primacy.

---

### Stage 7 — Confidence Filter + Output

- Filters out results where CE score < 0.1 AND multiplier <= 1.0
- Swaps `_expanded_text` into main `text` field for LLM delivery
- Returns top 5 results with scores, citations, and expanded context

---

## Runtime Infrastructure

| Component | Host | Notes |
|---|---|---|
| LanceDB + search | Primary runtime | nutanix_rag_v3 table |
| Gemma 4 31B | Remote endpoint | Topic scoring only |
| Jina Embed API | Cloud (api.jina.ai) | Vectorization |
| Jina Rerank API | Cloud (api.jina.ai) | Semantic reranking |
| OpenClaw gateway | Host | Agent orchestration |

### MCP Server Architecture (Dual-Instance)

Two separate RAG MCP server instances provide identity-based access control:

| Server | Port | Identity | Used By |
|---|---|---|---|
| `rag-mcp-server` | 8001 | `nx_shield` | NX_Shield (public only) |
| `rag-mcp-server-sam` | 8004 | `sam` (default) | Sam (full access) |

The identity is passed via `NX_AGENT_IDENTITY` env var (managed by launchd) and read at query time by `build_search_filters()`. NX_Shield can never retrieve `access_level='internal'` docs regardless of query or filter parameters.

---

## Key Data Structures

### `INTENT_FILTER_MAP`
Maps 5 intent buckets to doc_type / content_type filters. Applied dynamically based on keyword detection.

### `_INTENT_PATTERNS`
Keyword regex patterns for intent detection. 4 patterns covering COMPETITIVE, TROUBLESHOOTING, API_DEV, HARDWARE.

### `TOPIC_WEIGHTS`
Maps topic → float multiplier. Used in Stage 6 for post-hoc score boosting.

### `SUBJECT_PRODUCTS_MAP`
Maps topic → relevant products. Used in `score_multiplier` for products-match boost.

### `SUBJECT_SUBCAT_MAP`
Maps topic → subcategory string. Used in `score_multiplier` for subcategory-match boost.

### `_KB_MAP`
Maps topic → KB article number. Used in `score_multiplier` to boost KB-matching results.

---

## LanceDB Backup

The vector database is the core of the RAG system. Unlike config files, it is not included in the OpenClaw backup cron. A separate backup step is required.

### What to Back Up

```
~/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/   (~1.2 GB)
```

This directory contains the LanceDB table data, vector indices, and scalar indices for `nutanix_rag_v3`.

### Backup Methods

**Option A — Tarball (simple, portable)**
```bash
tar -czf ~/rag_backups/nutanix_rag_v3-$(date +%Y%m%d).tar.gz \
  ~/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/
```

**Option B — Rsync (faster for subsequent backups, keeps permissions)**
```bash
rsync -avz ~/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/ \
  ~/rag_backups/nutanix_rag_v3-latest/
```

### Restore

```bash
# 1. Stop any active ingest or search (prevents writes during restore)
# 2. Replace the directory
tar -xzf ~/rag_backups/nutanix_rag_v3-YYYYMMDD.tar.gz \
  -C ~/.openclaw/memory/lancedb-pro/

# Or for rsync restore:
rsync -avz ~/rag_backups/nutanix_rag_v3-latest/ \
  ~/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/

# 3. Restart the search service if needed
```

### Retention

Keep **7 days** of snapshots minimum. The DB grows slowly with new content so rolling daily backups are manageable.

### What's NOT Included in OpenClaw Backup

| Item | Included? | Notes |
|---|---|---|
| `nutanix_rag_v3.lance` | ✅ Included | Backed up via `.openclaw/memory/` in OpenClaw tar |
| `processed_files.json` | ✅ Included | Backed up via `.openclaw/workspace/rag/` |
| Source document repo | ✅ Included | `~/.openclaw/workspace/rag/nutanix/` is under `.openclaw/workspace/` |
| OpenClaw config | ✅ Included | Config files in `.openclaw/` |
| LM Studio model files | ❌ No | Model files live in the LM Studio app directory |
| Jina API key | ❌ No | Stored in OpenClaw config / environment variables |

The OpenClaw tar backup (3 AM, `backup-full.sh`) covers the entire `.openclaw/` directory, which includes both the LanceDB database and the source document repository. The only significant gaps are the LM Studio model binaries and the API key (which must be restored separately).

### Fresh Rebuild Path

If the DB is lost and no backup exists, recovery is possible via the source repo + pipeline scripts:

1. Source docs exist → run `embed_pipeline_v2.py --clean` to re-ingest
2. API keys available → Jina embedding continues as normal
3. Full rebuild time: several hours depending on source volume

This path is slower than restore-from-backup but doesn't lose data permanently.

