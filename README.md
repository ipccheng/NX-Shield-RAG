# NX Shield RAG

A Retrieval-Augmented Generation (RAG) knowledge base for Nutanix technical support. Used by **Sam** and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

---

## RAG vs Non-RAG: Real-World Comparison

Production data from simultaneous queries during the same session. Same model, same question — only the retrieval pipeline differs.

```
"Can you compare Redhat AI with NAI? please give me a summary"
```

| Metric | Non-RAG (Direct LLM) | RAG-Grounded |
|--------|---------------------|--------------|
| **Answer quality** | Hallucinated — didn't know what NAI stood for, guessed across 3 possibilities (Nutanix AI / NVIDIA AI / National AI), no sources | Identified NAI as Nutanix AI, cited 5 specific battlecards/summit docs with exact scores |
| **Query latency** | ~1–2s | ~6–8s |
| **Input tokens** | ~900 | ~984 |
| **Output tokens** | ~881 | ~934 |
| **Total tokens** | **~1,781** | **~1,918** |
| **Knowledge freshness** | Frozen at model training cutoff | Retrieval from live Nutanix battlecards, KB, and docs |
| **Domain accuracy** | Guessing | Verified — ce=0.204 on top result, specific citations |

### Better answers, comparable token cost

Without retrieval, the model "hallucinates context" into existence — burning tokens to sound authoritative on Nutanix-specific configs, version lifecycle dates, and compatibility matrices it only partially trained on. On this query, it hallucinated that "NAI" could mean Nutanix AI, NVIDIA AI, or National AI — unable to confirm which. With RAG, the retrieved documents anchor the answer: NAI is Nutanix AI, sourced from 5 specific battlecard and summit documents with verifiable scores.

Token cost is comparable (~1,918 RAG vs ~1,781 non-RAG). The extra ~137 tokens buy verifiable accuracy — a worthwhile trade in technical support.

### Accuracy vs Speed

**Accuracy is the primary constraint for this pipeline.** In technical support work, a wrong answer — even slightly wrong version numbers, slightly wrong compatibility claims — can cause downstream escalations or customer trust issues.

| Trade-off | Non-RAG | RAG-Grounded |
|-----------|---------|--------------|
| Answer accuracy | Unverified (hallucination risk) | Verified against source docs (top result ce=0.204) |
| Token efficiency | ~1,781/query | ~1,918/query (comparable) |
| Source citation | None (guessing) | 5 specific battlecard filenames, KB numbers, version strings |
| Reranking | None | Jina reranker-v3 (listwise, top 30→5) + DeepSeek topic boost + Kuzu graph boost |

For internal note-taking or brainstorming, direct LLM wins on speed. For anything requiring domain accuracy — Nutanix compatibility lists, KB references, lifecycle dates — the 6–8s latency overhead is a worthwhile trade for verified, battlecard-sourced answers.

---

## Before & After Kuzu: Adding Structural Entity Verification

Kuzu was added as a **graph DB layer** that walks the entity co-occurrence graph to verify and boost chunks whose tagged entities match structural connections found in the source corpus.

### What Changed

The query `"Can you compare Redhat AI with NAI?"` — **before Kuzu** retrieved 5 results from pure vector + FTS similarity. **After adding Kuzu**, the pipeline additionally:

1. Walks the Kuzu graph `(Chunk)-[r]->(Entity)` for entities connected to query terms (`Red_Hat`, `Nutanix_AI`)
2. Finds 12 entity nodes in the graph with co-occurrence relationships to those terms
3. Cross-matches Kuzu entity names against LanceDB `ecosystem_entities` / `mentioned_products` columns
4. Boosts chunks with graph-verified entity matches by **+0.15 RRF score** before cross-encoder reranking

### Before vs After (real production query — 2026-05-13)

**Query:** `"Can you compare Redhat AI with NAI? please give me a summary"`

| Metric | Before Kuzu (Vector + FTS only) | After Kuzu (Vector + FTS + Graph Boost) |
|--------|----------------------------------|----------------------------------------|
| **Top result** | `Red Hat AI vs Nutanix AI` battlecard (ce=0.199) | `Red Hat AI vs Nutanix AI` battlecard (ce=0.199, **graph-verified**) |
| **Entity verification** | None — pure embedding similarity | 139 entity types confirmed via Kuzu co-occurrence walk |
| **Confidence signal** | CE score only | CE score + `_graph_verified` flag + entity tags |
| **Chunks boosted (+0.15 RRF)** | 0 | 3 chunks |
| **Graph entities found** | — | **139 entity types** (vs 12 in earlier test) |
| **Latency overhead** | — | ~100ms (parallel graph walk, no added latency) |
| **Non-RAG baseline** | Hallucinated — guessed NAI = Nutanix/NVIDIA/National AI, no sources | Same hallucination (unchanged — non-RAG path unaffected by Kuzu) |

### Why It Matters

Vector similarity finds *linguistically similar* chunks. Kuzu finds *structurally related* chunks — documents that frequently mention the same entities together in the source corpus. Combining both signals means a query about "Red Hat AI" returns not just docs that *sound like* they're about Red Hat AI, but docs that are *verified by the graph* to be about Red Hat AI because other chunks in the corpus also mention those same entities.

See [GRAPH_DB.md](./GRAPH_DB.md) for full schema, entity extraction, and query patterns.

---

## Architecture

![NX_Shield RAG Pipeline Architecture](https://github.com/ipccheng/rag-pipeline/blob/main/RAG%20v3%20Pipeline%20Diagram.png)

---

## Documents

### 👉 1. [RAG PIPELINE ARCHITECTURE](./RAG_PIPELINE_ARCHITECTURE.md)
Full pipeline documentation — covers the query processing flow, LanceDB schema, intent-based dynamic filter routing, entity extraction, cross-encoder reranking, score multipliers, confidence thresholds, MCP server integration, runtime infrastructure, and LanceDB backup.

**Best for:** Understanding how a query moves from user input to formatted response.

### 👉 2. [EMBED PIPELINE](./EMBED_PIPELINE.md)
Ingestion pipeline documentation — covers smart chunking, metadata extraction (22 products, 8 content types), Jina AI embedding, LanceDB storage, checkpoint system, and the atomic rebuild process.

**Best for:** Understanding how source documents are processed, chunked, and loaded into the vector database.

### 👉 3. [METADATA SCHEMA](./METADATA_SCHEMA.md)
Metadata schema design and structure — covers the 7 metadata fields (access_level, doc_type, primary_product, mentioned_products, ecosystem_entities, versions, content_types), how each field is extracted, the v2 to v3 schema evolution, and how metadata is used in pre-filtering vs reranking.

**Best for:** Understanding how documents are tagged, why the schema was redesigned, and how metadata powers search accuracy.

### 👉 4. [MCP SETUP](./MCP_SETUP.md)
MCP server architecture and setup — covers the dual-instance MCP design (Sam vs NX_Shield), how tool naming works, the `--identity` flag, launchd service configuration, and troubleshooting steps.

**Best for:** Understanding how OpenClaw agents connect to the RAG search pipeline via MCP, and how to rebuild the MCP infrastructure from scratch.

### 👉 5. [HINDSIGHT SETUP](./HINDSIGHT_SETUP.md)
Hindsight app setup and operations — covers Docker Compose architecture (Hindsight + Postgres), backup and restore procedures, environment configuration, and operational notes.

**Best for:** Operating and maintaining the Hindsight long-term memory system.

### 👉 6. [GRAPH DB](./GRAPH_DB.md)
Kuzu graph database schema, entity extraction, relationship types, and query patterns — covers how entity co-occurrence walks are used to boost RAG retrieval with structural graph signals.

**Best for:** Understanding how Kuzu fits into the query pipeline, what entity types are stored, and how to write graph queries for debugging or extending the boost logic.

---

## Quick Reference

| Component | Detail |
|---|---|
| Vector DB | LanceDB (`nutanix_rag_v3_dedup` — ~1.2 GB, ~85.6K chunks) |
| Embedding | Jina AI `jina-embeddings-v5-text-small` (1024 dims) |
| Topic Classifier | DeepSeek (cloud, primary) / Gemma 4 31B (local fallback) |
| Graph DB | Kuzu (`nutanix_graph_v3` — ~72K Chunk nodes, ~48K Entity nodes) |
| Intent Routing | Keyword + entity-based dynamic filter construction |
| Entity Extraction | tagger_v3 — 22 Nutanix products + 24 ecosystem entities |
| Reranker | jina-reranker-v3 (Jina AI, listwise, top 30→5) |
| Index | IvfHnswPq vector + FTS + scalar (access_level, doc_type, primary_product) |
| Chunk size | 1024 tokens / 100 token overlap |
| DB size | **~85,642 chunks** / ~1.2 GB (deduplicated) |
| Query latency | ~6–8s (warm) |
| Pipeline | 11-stage: parallel (classify+embed+Kuzu+ripgrep) → intent filter → hybrid search → graph boost → expand → rerank → score → confidence filter → format + fallback |
| Agents | Sam, NX_Shield (Discord bot) |

---

## Repo Contents

| File | Description |
|---|---|
| `README.md` | This file |
| `RAG_PIPELINE_ARCHITECTURE.md` | Query pipeline + backup documentation |
| `EMBED_PIPELINE.md` | Ingestion pipeline documentation |
| `METADATA_SCHEMA.md` | Metadata schema design guide |
| `MCP_SETUP.md` | MCP server architecture |
| `GRAPH_DB.md` | Kuzu graph DB schema, entity extraction, and query patterns |
| `HINDSIGHT_SETUP.md` | Hindsight memory system setup |
| `RAG_Pipeline_Diagram.png` | Architecture diagram |
