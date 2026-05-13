# NX_Shield RAG Pipeline — Architecture & Documentation

> **Last updated:** 2026-05-13
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
+-- NX_Shield: gateway-mcp (port 8010) -> master_search tool
|   |
|   +-- nx_gateway_mcp.py (thin SSE bridge — no waterfall logic)
|   +-- nutanix_rag_search.py (universal search engine — all tiers below)
|       |
|       +-- Tier 1: RAG (LanceDB semantic search)
|       +-- Tier 1.5: Ripgrep (local source files, parallel with RAG)
|       +-- Tier 2: Slack (slk CLI fallback)
|       +-- Tier 3: Web (SearXNG fallback)
|
v
run_search() [7-stage pipeline]
|
+-- Stage 1: Intent detection + filter construction (keyword + entities)
+-- Stage 2: Jina embed (api.jina.ai, 1024-dim)
+-- Stage 3: LanceDB hybrid search (vector + FTS + RRF with dynamic filters)
+-- Stage 4: expand_for_rerank (±2 neighbor context via PyArrow)
+-- Stage 5: Jina cross-encoder rerank (top 30 → top 5)
+-- Stage 6: score_multiplier() + subcategory/product boost from DeepSeek topics
+-- Stage 7: format_results() -> LLM-readable output
```

### Architecture Change (2026-05-13)

**Two-component design:**

1. **`nutanix_rag_search.py` — Universal Search Engine**
   All waterfall logic lives here: RAG (Tier 1), Ripgrep (Tier 1.5), Slack (Tier 2), Web (Tier 3). Any bot, CLI tool, or script calls this one Python file and gets the full fallback sequence. No tool overhead.

2. **`nx_gateway_mcp.py` — Ultra-Thin SSE Bridge (NX_Shield only)**
   Receives HTTP/SSE from OpenClaw, extracts the query, calls `nutanix_rag_search.py`, returns `TextContent`. Contains zero fallback logic — purely an HTTP adapter.

**Why:** Any future agent (Sam on Mac mini, Neo on MacBook, a CLI script, a cron job) can call `nutanix_rag_search.py` directly and get the full engineered waterfall. The gateway is NX_Shield-specific plumbing.

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

| Agent | Method | Tool | Notes |
|---|---|---|---|
| Sam | Direct Python exec | `run_search()` | Full access (internal + public) |
| NX_Shield | Single tool call | `gateway-mcp__master_search` | Enforces RAG → Slack → Web waterfall |

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

**Total pipeline latency:** ~6-8s per query (warm)

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

**DeepSeek topic classification** runs in parallel but is used ONLY for `score_multiplier()` boosting (not search routing). This means if DeepSeek times out or the endpoint is unreachable, search still works perfectly — only the scoring boost is lost.

---

### Stage 4 — Context Expansion (`expand_for_rerank`)

Same as before — replaces each hit's tiny chunk (~8000 chars) with ±2 neighboring chunks from the same document. Gives the cross-encoder full localized context.

**Window:** ±2 chunks per side. Uses PyArrow column iteration — no vector search.

---

### Stage 5 — Cross-Encoder Rerank (`jina_rerank`)

Same as before — Jina's hosted listwise reranker scores semantic relevance. Falls back to RRF scores if all CE scores are 0.

---

### Stage 6 — Score Multiplier (`score_multiplier`)

Same signal structure as before, but topics from DeepSeek classification are used as a **secondary scoring signal**, not primary routing. If DeepSeek is offline, the multiplier defaults to 1.0 (no boost), but search still works.

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

## Gateway MCP — Thin Bridge + Universal Search Engine

NX_Shield queries go through a single mandatory tool: `gateway-mcp__master_search`.

### Per-Agent Call Limits (max_calls)

Each agent has a **max_calls** limit enforced server-side by the gateway — not by the LLM:

| Agent | max_calls | Notes |
|---|---|---|
| `nutanix_shield` | 2 | NX_Shield Discord bot |
| `sam` | 3 | Mac mini main session |
| `default` | 1 | Any unknown session |

**How it works:** The gateway builds a session→agent map at startup by scanning `~/.openclaw/agents/*/sessions/*.jsonl`. When a tool call arrives, the session ID is looked up to identify the agent, and the call counter for that session is incremented. If the limit is exceeded, the gateway returns `MAX_CALLS_EXCEEDED` — no further calls are accepted.

### Two Components

**`nx_gateway_mcp.py` (port 8010) — Thin SSE Bridge**
Receives HTTP/SSE from OpenClaw. Extracts the query string. Calls `nutanix_rag_search.py` as a subprocess. Takes the stdout and wraps it in an MCP `TextContent` payload. Zero fallback logic — purely an HTTP adapter. Also enforces per-agent call limits.

**`nutanix_rag_search.py` — Universal Search Engine**
All waterfall logic lives in one script, callable by any agent or CLI:

```
nutanix_rag_search.py [options] <query> [limit]

Options:
  --rerank-top N      Number of results to return (default: 50)
  --identity NAME     Agent identity: sam | nx_shield (default: nx_shield)
  --no-slack-search   Skip Slack fallback
  --no-web-search     Skip Web (SearXNG) fallback
```

**Tier execution:** Tier 1 (RAG) and Tier 1.5 (Ripgrep) fire in parallel via `ThreadPoolExecutor`. Tiers 2 and 3 are sequential fallbacks.

### Waterfall Logic (in nutanix_rag_search.py)

```
Tier 1:   RAG (LanceDB semantic search, CE score >= 0.1)
Tier 1.5: Ripgrep (local .md/.txt/.html files, parallel with Tier 1)
Tier 2:   Slack (slk CLI — only if Tier 1+1.5 return nothing or low confidence)
Tier 3:   Web (SearXNG — only if Tier 1+1.5+2 all fail)
```

### Gateway Configuration File

Per-agent call limits are defined in `gateway_config.json`, loaded at gateway startup:

```json
{
  "max_calls_per_session": {
    "nutanix_shield": 2,
    "sam": 3,
    "default": 1
  }
}
```

The config path is: `~/.openclaw/workspace/scripts/gateway_config.json`

### Multi-Host Configuration (env vars)

`nutanix_rag_search.py` reads paths/URLs from environment variables so the same script works on Mac mini (Sam/NX_Shield) and MacBook (Neo):

| Env Variable | Default | Notes |
|---|---|---|
| `KUZU_DB_PATH` | `~/.openclaw/memory/kuzu-pro/nutanix_graph_v3` | Kuzu graph DB |
| `SEARXNG_URL` | `http://127.0.0.1:8888/search` | Neo overrides with its local SearXNG |
| `RAG_DOCS_DIR` | `~/.openclaw/workspace/rag/nutanix` | Ripgrep search root |

### Gateway Tool Constraints

NX_Shield's tool allowlist was updated to remove all individual search tools:

| Removed (no longer callable by NX_Shield) | Still available |
|---|---|
| `rag-mcp-server__query_nutanix_docs` | `gateway-mcp__master_search` (only) |
| `slack-search-mcp__slack_search` | `memory_recall` / `memory_store` |
| `web-search-filtered__web_search_filtered` | `storage_calc_*` tools |
| | `read`, `sessions_list`, `sessions_history` |

This ensures the waterfall is architecturally enforced — not dependent on the LLM following prompt rules.

---

## Runtime Infrastructure

| Component | Host | Notes |
|---|---|---|
| LanceDB + search | Primary runtime | nutanix_rag_v3 table |
| DeepSeek | Remote endpoint | Topic scoring only |
| Jina Embed API | Cloud (api.jina.ai) | Vectorization |
| Jina Rerank API | Cloud (api.jina.ai) | Semantic reranking |
| OpenClaw gateway | Host | Agent orchestration |
| SearXNG | Host (Mac mini + Neo MacBook) | Web search (Tier 3 fallback); configurable via `SEARXNG_URL` env var |
| Slack (slk CLI) | Host | Tier 2 fallback |

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

The LanceDB database (`nutanix_rag_v3.lance`) is included in the daily OpenClaw backup (3 AM, `backup-full.sh`). The backup tar archives the entire `.openclaw/` directory, which contains both the LanceDB database and the source document repository.

### Backup (Automatic)

The OpenClaw tar backup runs daily at 3 AM and includes:
```
~/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/   (~1.2 GB)
```

To trigger a manual backup:
```bash
tar -czf ~/openclaw_backups/YYYYMMDD-openclaw-backup.tar.gz \
  -C /Users/ipccheng .openclaw
```

To manually back up LanceDB only (outside the cron):
```bash
tar -czf ~/rag_backups/nutanix_rag_v3-$(date +%Y%m%d).tar.gz \
  ~/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/
```

### Restore

Extract from the OpenClaw backup tar:
```bash
tar -xzf YYYYMMDD-openclaw-backup.tar.gz -C /Users/ipccheng/
```

This restores `.openclaw/` to `/Users/ipccheng/.openclaw/`, including the LanceDB directory at `/Users/ipccheng/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/`.

### Retention

The OpenClaw backup script keeps **14 days** of snapshots on T7. The LanceDB table grows slowly with new content, so this is sufficient for recovery.

---

## Changelog

### 2026-05-13
- **TWO-COMPONENT SPLIT**: `nutanix_rag_search.py` = universal engine (all tiers); `nx_gateway_mcp.py` = thin SSE bridge (zero fallback logic)
- **Universal engine**: All waterfall logic (RAG + Ripgrep + Slack + Web) now in one Python script — any agent/CLI can call it directly
- **Parallel Tier 1**: RAG (LanceDB) and Ripgrep now fire simultaneously via `ThreadPoolExecutor`; results are combined for richer context
- **Environment-configurable paths**: `KUZU_DB_PATH`, `SEARXNG_URL`, `RAG_DOCS_DIR` allow the same script to run on Mac mini (Sam/NX_Shield) or Neo MacBook
- **Gateway MCP** (`nx_gateway_mcp.py`) is now an ultra-thin SSE bridge — receives OpenClaw HTTP request, calls `nutanix_rag_search.py`, returns `TextContent`
- **LLM tool allowlist stripped**: Removed direct access to `rag-mcp-server__query_nutanix_docs`, `slack-search-mcp__slack_search`, `web-search-filtered__web_search_filtered` from NX_Shield
- **Web search**: SearXNG (port 8888) — configurable per host via `SEARXNG_URL` env var
- **Old MCP services decommissioned**: `rag-mcp-server` (port 8001), `slack-search-mcp` (port 8005) LaunchAgents removed from launchd
- **Per-agent call limits**: `gateway_config.json` enforces max_calls server-side (NX_Shield=2, Sam=3, default=1) — not LLM-dependent
- **Session map**: gateway builds session→agent map at startup from `~/.openclaw/agents/*/sessions/*.jsonl` to identify calling agent

### 2026-05-12
- Replaced **Gemma** with **DeepSeek** for topic classification
- Added **nutanix_rag_v3_dedup** index (~85K rows, ~800MB) for deduplicated search
- Added **NKP** and **NAI** keyword fallbacks in QUERY_CLASSIFIERS for better topic routing
- Added `slack-search-mcp` and `web-search-filtered` MCP servers for NX_Shield fallback queries

### 2026-05-03
- Added `expand_for_rerank` fix using PyArrow iteration — reduced latency from 54s to 3-4s
- Added pre-filtering logic updates

### 2026-04-27
- Refactored pipeline to single hybrid search (was per-topic parallel search)
- Fixed `expand_for_rerank` deadlock issue
- Updated GEMMA_TIMEOUT from 10s to 3s
