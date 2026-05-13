# NX Shield RAG

A Retrieval-Augmented Generation (RAG) knowledge base for Nutanix technical support. Used by **Sam** and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

---

## Kuzu Graph Boost — Before vs After

Kuzu is a read-only graph layer that adds **structural entity verification** to vector search. It does not replace vector retrieval — it sits alongside it, confirming that a chunk's tagged entities are genuinely connected to the query topic through the document knowledge graph.

```
Query: "NKP edition needed for NAI"
```

**Kuzu graph topology (48,483 entities, 334,800 relationship edges):**

```
Chunk ──HAS_RELATIONSHIP──► Entity (e.g. "NAI", "NKP_EDITION")
  │                              ▲
  │                              │
  └───(via chunk_hash)      RELATED_TO
                              │
                        Entity (e.g. "Nutanix_AI")

When query contains "NAI", Kuzu finds all entities connected to "NAI"
in the graph → boosts chunks whose metadata mentions those entities.
```

| Metric | LanceDB Only (Before) | LanceDB + Kuzu Graph (After) |
|--------|----------------------|------------------------------|
| **Entity discovery** | Metadata tags only | Graph traversal finds related entities |
| **Boost mechanism** | Semantic similarity only | +0.15 RRF score for graph-verified chunks |
| **Entity coverage** | Static metadata | Graph discovers隐式 connections (e.g. "NAI"→"Nutanix_AI" via RELATED_TO) |
| **Query latency** | ~6–8s | ~6–8s (Kuzu walks run in parallel with embedding) |
| **Storage** | ~1.2 GB LanceDB | + ~100 MB Kuzu DB |
| **Graph size** | N/A | 48,483 entities / 334,800 edges |

### What Kuzu Actually Does

Kuzu does **not** retrieve additional chunks. Its role is **score boosting**:

1. **Graph walk:** Kuzu traverses `(Chunk)-[HAS_RELATIONSHIP]->(Entity)` for every query term, finding all entities connected to the query
2. **Entity matching:** The returned entity names (e.g. `NAI`, `NKP_EDITION`, `Nutanix_AI`) are fuzzy-matched against each result chunk's `ecosystem_entities` and `mentioned_products` metadata
3. **Score boost:** Chunks where tagged entities overlap with Kuzu's graph-verified entities receive +0.15 to their RRF score — structural confirmation baked into the ranking

The key advantage: **graph discovers implicit relationships that pure metadata cannot capture.** A chunk about "NAI" might not explicitly mention "Nutanix AI" — but the graph knows they're the same entity via `RELATED_TO` edges, and boosts it accordingly.

---

## RAG vs Non-RAG: Real-World Comparison

Production data from simultaneous queries during the same session. Same model, same question — only the retrieval pipeline differs.

```
"Can you compare Redhat AI with NAI? please give me a summary"
```

| Metric | Non-RAG (Direct LLM) | RAG-Grounded |
|--------|---------------------|--------------|
| **Answer quality** | Hallucinated — plausible but unsourced | Battlecard-sourced — specific KBs, versions, facts |
| **Query latency** | ~1–2s | ~6–8s |
| **Input tokens** | 14,394 | ~1,700 |
| **Output tokens** | 1,621 | ~1,600 |
| **Total tokens** | **75,631** | **~3,300** |
| **Knowledge freshness** | Frozen at model training cutoff | Retrieval from Nutanix KB and docs |
| **Domain accuracy** | Guessing | Verified |

### 23× fewer tokens — with better answers

Without retrieval, the model "hallucinates context" into existence — burning 75,631 tokens trying to sound authoritative on Nutanix-specific configs, version lifecycle dates, and compatibility matrices it only partially trained on. With RAG, the retrieved documents do that work. The model synthesises, doesn't guess.

### Accuracy vs Speed

| Trade-off | Non-RAG | RAG-Grounded |
|-----------|---------|--------------|
| Answer accuracy | Unverified (hallucination risk) | Verified against source docs |
| Token efficiency | 75,631/query | ~3,300/query (23× less) |
| Source citation | None (guessing) | Specific KB numbers, product versions |
| Reranking | None | DeepSeek topic + Jina cross-encoder |

---

## Architecture

![NX_Shield RAG Pipeline Architecture](https://github.com/ipccheng/rag-pipeline/blob/main/RAG%20v3%20Pipeline%20Diagram.png)

**Source file:** [RAG_Pipeline_Diagram.drawio](https://github.com/ipccheng/rag-pipeline/blob/main/RAG_Pipeline_Diagram.drawio) — edit in draw.io or VS Code extension

---

## Documents

### 👉 1. [RAG PIPELINE ARCHITECTURE](./RAG_PIPELINE_ARCHITECTURE.md)
Full pipeline documentation — covers the query processing flow, LanceDB schema, intent-based dynamic filter routing, entity extraction, cross-encoder reranking, score multipliers, confidence thresholds, the Gateway MCP enforced waterfall, and LanceDB backup.

**Best for:** Understanding how a query moves from user input to formatted response.

### 👉 2. [EMBED PIPELINE](./EMBED_PIPELINE.md)
Ingestion pipeline documentation — covers smart chunking, metadata extraction (22 products, 8 content types), Jina AI embedding, LanceDB storage, checkpoint system, and the atomic rebuild process.

**Best for:** Understanding how source documents are processed, chunked, and loaded into the vector database.

### 👉 3. [METADATA SCHEMA](./METADATA_SCHEMA.md)
Metadata schema design and structure — covers the 7 metadata fields (access_level, doc_type, primary_product, mentioned_products, ecosystem_entities, versions, content_types), how each field is extracted, the v2 to v3 schema evolution, and how metadata is used in pre-filtering vs reranking.

**Best for:** Understanding how documents are tagged, why the schema was redesigned, and how metadata powers search accuracy.

### 👉 4. [MCP SETUP](./MCP_SETUP.md)
MCP server architecture and setup — covers the Gateway MCP design (port 8010), tool naming conventions, the `--identity` flag, launchd service configuration, and troubleshooting steps.

**Best for:** Understanding how OpenClaw agents connect to the RAG search pipeline via MCP, and how to rebuild the MCP infrastructure from scratch.

### 👉 5. [GRAPH DB](./GRAPH_DB.md)
Kuzu embedded graph database — covers entity relationships, graph schema, building the graph from LanceDB, query patterns, and graph boost integration.

**Best for:** Understanding how the graph layer enhances vector search with relationship-aware retrieval.

### 👉 6. [HINDSIGHT SETUP](./HINDSIGHT_SETUP.md)
Hindsight app setup and operations — covers Docker Compose architecture (Hindsight + Postgres), backup and restore procedures, environment configuration, and operational notes.

**Best for:** Operating and maintaining the Hindsight long-term memory system.

---

## Quick Reference

| Component | Detail |
|---|---|
| Vector DB | LanceDB (`nutanix_rag_v3` — ~1.2 GB) |
| Graph DB | Kuzu (`nutanix_graph_v3` — 48,483 entities, 334,800 edges) |
| Embedding | Jina AI `jina-embeddings-v5-text-small` (1024 dims) |
| Classifier | DeepSeek (for topic-based scoring boost) |
| Intent Routing | Keyword + entity-based dynamic filter construction |
| Entity Extraction | tagger_v3 — 22 Nutanix products + 24 ecosystem entities |
| Reranker | jina-reranker-v3 (Jina AI, listwise, top 30→5) |
| Index | IvfHnswPq vector + FTS + scalar (access_level, doc_type, primary_product) |
| Chunk size | 1024 tokens / 100 token overlap |
| DB size | **129,732 chunks** / ~1.2 GB |
| Query latency | ~6–8s (warm) |
| Pipeline | 7-stage: intent routing → embed → search → expand → rerank → score → format |
| Gateway | `gateway-mcp__master_search` (port 8010) — enforces RAG → Slack → Web waterfall |
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
| `GRAPH_DB.md` | Kuzu graph database guide |
| `HINDSIGHT_SETUP.md` | Hindsight memory system setup |
| `RAG_Pipeline_Diagram.png` | Architecture diagram |
