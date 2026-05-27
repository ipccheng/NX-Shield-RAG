# NX_Shield RAG Search Pipeline

> **Last updated:** 2026-05-27
> **Status:** Active — Hermes LanceDB-centered search path
> **Primary script:** `nutanix_rag_search.py`
> **MCP tool:** `hermes_master_search`

---

## Overview

This document describes the Nutanix technical knowledge-base RAG search pipeline used by **Sam** and **NX_Shield** through Hermes MCP. The active search path is centered on **LanceDB**, combining native portal/page evidence with imported historical evidence families such as KB, Google Docs, xpress, team-chat, and legacy chunk sources.

Key additions since the v3-only pipeline:

- **LanceDB-centered corpus:** active unified search index with explicit migration lineage.
- **Hermes MCP tool naming:** `hermes_master_search` for both Sam/default and NX_Shield profile endpoints.
- **Evidence Ledger / Answer Obligations:** formatted output now exposes query class, weak-evidence notes, missing evidence, and answer obligations.
- **`answer_rule:` guardrails:** source-traceable claims, missing-evidence disclosure, and caution for competitive/licensing/pricing/roadmap claims.
- **Calculator-first sizing:** storage sizing/BOM questions emit a deterministic calculator block before using RAG as supporting context.
- **Kuzu GraphContext:** graph verification and distance-2 source suggestions remain advisory; graph relevance is not treated as answer sufficiency.

The older v3 13-stage pipeline below is retained as lineage because the active path imports historical evidence and keeps many of the same routing/reranking concepts.

---

## System Architecture

![NX_Shield RAG Search Pipeline](./RAG%20Search%20Pipeline%20Diagram.png)

### Active High-Level Flow

```text
User query
  → Hermes MCP profile endpoint (`hermes_master_search`)
  → query classifier / deterministic routing
  → query variants and source-family multipliers
  → LanceDB hybrid retrieval (vector + FTS + RRF)
  → Kuzu GraphContext advisory signal
  → exact local keyword matches as supporting context
  → calculator-first path for storage sizing/BOM
  → rerank + score + confidence filtering
  → Evidence Ledger / Answer Obligations / answer_rule guardrails
  → grounded LLM-readable answer context
```

---

## Active LanceDB Search Index

The core of the RAG search architecture is LanceDB. The current implementation uses the active unified corpus, but the architecture should be understood as **LanceDB-centered retrieval** rather than as a version-specific design.

- **Role:** core vector + FTS + scalar metadata search index
- **Embedding lineage:** Jina AI `jina-embeddings-v5-text-small`
- **Key index families:** FTS on `search_text`; scalar indexes for source family, confidentiality/scope, migration lineage, and document/page identifiers; vector index on `vector`
- **Lineage:** native evidence plus imported historical evidence families

Stable data-quality points from K17:

| Field | Verified state |
|---|---|
| `chunk_hash` | populated and unique in the active unified corpus |
| `unique_chunk_key` | populated and unique in the active unified corpus |
| `source_family` | populated for routing/filtering |
| `confidentiality` | populated for access/scope filtering |
| `migration_source` | distinguishes native vs imported lineage |
| `content_hash` | known P0 cleanup item on legacy rows |
| `section_id` | known P1 cleanup item on imported rows |

---

## Query Paths

Sam and NX_Shield use Hermes MCP profile endpoints that expose the same canonical tool name while allowing profile-specific service configuration.

| Consumer | MCP Tool | Service role | Notes |
|---|---|---|---|
| Sam/default | `hermes_master_search` | primary Hermes RAG search endpoint | active LanceDB path |
| NX_Shield | `hermes_master_search` | dedicated NX_Shield RAG search endpoint | active LanceDB path; full-docs access approved by owner |
| Storage sizing | storage calculator MCP tools | shared calculator endpoint | calculator-first for BOM/sizing questions |

All RAG MCP services call `nutanix_rag_search.py` as the search subprocess and return formatted evidence for the model to synthesize from.

---

## 13-Stage Pipeline (run_search)

| Stage | Function | Duration |
|---|---|---|
| S1 | Parallel: DeepSeek classify + generate_routing + Kuzu graph | ~1-2s |
| S2 | jina_embed_batch — 1 API call, 4 vectors (orig + 3 rewrites) | ~0.5s |
| S3 | Multi-channel parallel LanceDB search (mode-dependent) | ~0.1s mean observed |
| S4 | RRF merge with channel_weights + chunk_hash accumulation | ~0.01s |
| S5 | Fallback retry (if < 3 unique sources) — security-only filter | — |
| S6 | **Graph Boost** — Kuzu entity match, +0.15 to rrf_score | ~0.1s |
| S7 | expand_for_rerank (±2 neighbor context via t.to_arrow()) | **~0.2s** |
| S8 | Jina cross-encoder rerank (top 30/50 → top 5) | ~1.8s mean observed |
| S9 | score_multiplier() — KB#, subcategory, products, mentioned_products | ~0.01s |
| S10 | Confidence filter (CE < 0.1 AND mult ≤ 1.0 → discard) | ~0.01s |
| S11 | Swap expanded text into `text` field | — |
| S12 | ripgrep (parallel with S1-S3 via ThreadPoolExecutor) | ~0.5s |
| S13 | format_results() + fallback waterfall | — |

**Observed Milestone 5 latency:** 10-case sanitized eval mean external runtime `5.39s`; mean internal timed search path `4.72s`. Largest measured costs are DeepSeek/Kuzu parallel prep and Jina rerank.

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
- Dynamic node/edge counts are intentionally omitted from architecture docs; verify live graph size from Kuzu when needed.

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

**Source diversity after CE rerank:** Multiple chunks from the same source can survive into the cross-encoder pool. After CE scoring and confidence filtering, `diversify_by_source()` prefers one final result per source and backfills only if needed. This avoids suppressing strong localized chunks before semantic reranking.

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
| General/empty primary product penalty | topic expects a specific subcategory but doc primary product is empty/General | 0.75× |
| Products match | doc's `mentioned_products` intersect topic's products | 1.2× |
| Source authority | `github/*` on general non-API/non-Calm queries | 0.55× |

> ⚠️ **Source authority tuning (2026-05-24):** `github/*` remains valid for API/dev/Ansible/Terraform/Calm-style queries, but is down-weighted for general operations queries so authoritative portal/KB docs win near-ties.

**Cap:** 1.4× maximum to preserve CE semantic primacy.

### S10 — Confidence Filter

- Filters out results where CE score < 0.1 AND multiplier ≤ 1.0
- Swaps `_expanded_text` into main `text` field for LLM delivery

### S11 — Format + Fallback Waterfall

`format_results()` called from `main()` with both RAG results and ripgrep text. If RAG confidence is low (all CE scores < 0.10):

1. **Slack fallback** — `slk search` CLI subprocess (direct call, not MCP)
2. **SearXNG web fallback** — direct HTTP JSON request to `http://127.0.0.1:8888/search` (not MCP)

### S12 — Ripgrep (Parallel)

Ripgrep runs in parallel with the RAG search via a separate `ThreadPoolExecutor` in `main()`. It uses the **Homebrew-installed rg** (`/opt/homebrew/bin/rg`):

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
Mode-dependent — `[SINGLE]`: `[1.0, 1.0, 0.3, 0.3, 0.3]`; `[COMPARISON]`: `[0.3, 0.3] + [1.0, 1.0] × N_subqueries`.

### Timing Instrumentation
`run_search()` emits a sanitized timing line to stderr for baseline/eval parsing:

```text
[TIMING] {"parallel_prep": ..., "embedding": ..., "search_channels": ..., "rerank": ..., "total": ...}
```

The baseline/eval reports store timing metadata and source identifiers only; retrieved KB text snippets are not persisted.

---

## Current Bottlenecks and Follow-up Backlog

Milestone 5 showed that Stage 2 LanceDB search is no longer the main latency bottleneck. The largest measured costs are now:

1. `parallel_prep` — DeepSeek classification/routing plus Kuzu graph walk
2. `rerank` — Jina cross-encoder call
3. per-query process/runtime overhead from the MCP subprocess execution model

Recommended next optimizations:

- **Persistent service/module mode:** avoid per-query subprocess startup and reuse LanceDB/Kuzu handles plus HTTP clients.
- **Rerank optimization:** tune rerank pool size dynamically, skip rerank for high-confidence exact/KB queries where safe, or test alternative/batched reranker strategies.
- **Parallel prep optimization:** cache DeepSeek classification/routing, cache query embeddings, and make Kuzu optional/conditional by query type.
- **Eval expansion before more quality tuning:** comparison and Flow/security queries pass but can have first relevant rank 2; add more comparison/security examples before tuning weights further to avoid overfitting.

---

## Runtime Infrastructure

| Component | Host | Notes |
|---|---|---|
| LanceDB + search | Hermes RAG host(s) | active unified search index with native + imported evidence |
| Kuzu graph DB | Hermes RAG host(s) | `nutanix_graph_v3` — embedded advisory graph; relationship semantics cleanup tracked in K17 |
| Jina Embed/Rerank API | Cloud (api.jina.ai) | Query embedding lineage and semantic reranking |
| Storage calculator MCP | Hermes RAG host(s) | deterministic Nutanix storage sizing for BOM/capacity questions |
| SearXNG / web fallback | Local service where configured | fallback only when confidence/evidence is insufficient |
| Slack / exact local matches | Local tools where configured | supporting context; answer must still disclose weak or missing evidence |
| Hermes gateway/profiles | Sam + NX_Shield profiles | agent orchestration and MCP discovery |

---

## LanceDB Backup

The active LanceDB store should be backed up as part of the Hermes/Nutanix RAG backup process. Keep old historical/rollback stores until explicit cleanup approval after a soak period.

**Manual backup pattern:**
```bash
# Resolve the active LanceDB path from the running RAG service configuration,
# then archive that directory with a date-stamped filename.
tar -czf ~/rag_backups/nutanix_lancedb_active-$(date +%Y%m%d).tar.gz \
  /path/to/active/lancedb/store/
```

**Restore:**
```bash
tar -xzf YYYYMMDD-nutanix_lancedb_active.tar.gz -C /restore/root/
```

---

## Changelog

### 2026-05-27 — LanceDB-centered RAG search docs + diagram rename
- **Documentation rename** — `RAG_PIPELINE_ARCHITECTURE.md` is now `RAG_SEARCH_PIPELINE.md` to describe the active search path more clearly.
- **Diagram rename** — `RAG v3 Pipeline Diagram.png` is now `RAG Search Pipeline Diagram.png`.
- **Active LanceDB path** — documented LanceDB as the central search index, with native + imported evidence lineage and stable metadata fields.
- **Answer policy** — documented Evidence Ledger, Answer Obligations, weak-evidence notes, and `answer_rule:` guardrails.
- **Calculator-first sizing** — documented deterministic storage sizing/BOM path with RAG as supporting context.
- **K17 roadmap** — documented current schema/data-quality findings and side-by-side rebuild stance.

### 2026-05-24 — Milestone 5 Performance Instrumentation + Channel Cleanup
- **Timing instrumentation** — added `[TIMING]` JSON output for guard, DB open, parallel prep, embedding, Stage 2 search, graph boost, context expansion, rerank, postprocess, and total.
- **Stage 2 parallelization** — channel searches are executed with `ThreadPoolExecutor` while preserving deterministic channel order for weighted RRF.
- **Channel topology helper** — `route_search_methods()` enforces vector+FTS for original routes and vector-only for SINGLE rewrites.
- **COMPARISON original query** — original mixed comparison query is preserved at weight `0.3`; decomposed subqueries remain weight `1.0`.
- **Eval expansion** — sanitized eval suite expanded from 5 to 10 cases; latest run: 10/10 pass, Hit@5 10/10, mean MRR 0.9, mean latency 5.39s.
- **Follow-up backlog** — documented persistent service mode, rerank optimization, parallel prep caching/conditional Kuzu, and eval expansion before additional quality tuning.

### 2026-05-19 — Intent Routing + Documentation Corrections
- **generate_routing()** — replaces generate_rewrites(): single-pass DeepSeek call returns `{intent, queries}` dict; zero extra latency
- **[SINGLE] mode** — 3 linguistic rewrites as tiebreakers (0.3 weight); 5-channel search unchanged from prior doc
- **[COMPARISON] mode** — decomposes "A vs B" queries into 2–4 sub-queries; each runs Vector + FTS at 1.0; original query de-prioritised to 0.3
- **Kuzu** — confirmed working as embedded library (no daemon). Dynamic graph counts are intentionally omitted from architecture docs.
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
- Deduplication: historical rebuild reduced duplicate chunk records; verify current count live when needed
