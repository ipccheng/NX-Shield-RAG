# NX Shield RAG

A Retrieval-Augmented Generation (RAG) knowledge base for Nutanix technical support. Used by **Sam** and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

---

## Architecture

![NX_Shield RAG Search Pipeline Architecture](./RAG%20Search%20Pipeline%20Diagram.png)

---

## Documents

### 👉 1. [RAG SEARCH PIPELINE](./RAG_SEARCH_PIPELINE.md)
Full RAG search documentation — covers the active LanceDB-centered query path, LanceDB/Kuzu search layers, deterministic routing, source-family multipliers, calculator-first sizing behavior, Evidence Ledger output, answer guardrails, MCP integration, and historical pipeline lineage.

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
| Vector DB | LanceDB search index (active unified corpus with native + imported evidence) |
| Embedding | Jina AI `jina-embeddings-v5-text-small` lineage |
| MCP Tool | `hermes_master_search` via Hermes profile endpoints |
| Graph DB | Kuzu (`nutanix_graph_v3`) advisory graph context |
| Intent Routing | Query-class routing + deterministic variants + source-family multipliers |
| Entity Extraction | tagger/graph lineage — Nutanix products + ecosystem entities |
| Reranker | jina-reranker-v3 + bounded score/source-family multipliers |
| Index | FTS on `search_text`; scalar BTree indexes on source-family, confidentiality/scope, migration-lineage, and document/page fields; vector index on `vector` |
| Answer Policy | Evidence Ledger + Answer Obligations + `answer_rule:` guardrails |
| Storage Sizing | Calculator-first path; RAG/BOM sources are supporting evidence |
| Query latency | Varies by query class, reranker, and fallbacks; use current canary/benchmark reports for live numbers |
| Pipeline | Hermes MCP → query classification → variants/source-family routing → LanceDB hybrid retrieval + Kuzu advisory context + exact matches → calculator-first if sizing → rerank/score → Evidence Ledger → grounded answer context |
| Agents | Sam, NX_Shield |

---

## Repo Contents

| File | Description |
|---|---|
| `README.md` | This file |
| `RAG_SEARCH_PIPELINE.md` | Active LanceDB-centered RAG search pipeline + historical lineage |
| `EMBED_PIPELINE.md` | Ingestion pipeline documentation |
| `METADATA_SCHEMA.md` | Metadata schema design guide |
| `MCP_SETUP.md` | MCP server architecture |
| `GRAPH_DB.md` | Kuzu graph DB schema, entity extraction, and query patterns |
| `HINDSIGHT_SETUP.md` | Hindsight memory system setup |
| `RAG_Pipeline_Diagram.png` | Architecture diagram |
