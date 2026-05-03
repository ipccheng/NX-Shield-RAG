# NX_Shield RAG Pipeline

A Retrieval-Augmented Generation (RAG) knowledge base for Nutanix technical support. Used by **Sam** and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

---

## Architecture

![NX_Shield RAG Pipeline Architecture](https://github.com/ipccheng/rag-pipeline/blob/main/RAG%20Pipeline%20Diagram.png)

---

## Documents

### 👉 1. [RAG_PIPELINE_ARCHITECTURE.md](./RAG_PIPELINE_ARCHITECTURE.md)
Full pipeline documentation — covers the query processing flow, LanceDB schema, intent-based dynamic filter routing, entity extraction, cross-encoder reranking, score multipliers, confidence thresholds, MCP server integration, runtime infrastructure, and LanceDB backup.

**Best for:** Understanding how a query moves from user input to formatted response.

### 👉 2. [EMBED_PIPELINE.md](./EMBED_PIPELINE.md)
Ingestion pipeline documentation — covers smart chunking, metadata extraction (22 products, 8 content types), Jina AI embedding, LanceDB storage, checkpoint system, and the atomic rebuild process.

**Best for:** Understanding how source documents are processed, chunked, and loaded into the vector database.

### 👉 3. [METADATA_SCHEMA.md](./METADATA_SCHEMA.md)
Metadata schema design and structure — covers the 7 metadata fields (access_level, doc_type, primary_product, mentioned_products, ecosystem_entities, versions, content_types), how each field is extracted, the v2 to v3 schema evolution, and how metadata is used in pre-filtering vs reranking.

**Best for:** Understanding how documents are tagged, why the schema was redesigned, and how metadata powers search accuracy.

### 👉 4. [MCP_SETUP.md](./MCP_SETUP.md)
MCP server architecture and setup — covers the dual-instance MCP design (Sam vs NX_Shield), how tool naming works, the `--identity` flag, launchd service configuration, and troubleshooting steps.

**Best for:** Understanding how OpenClaw agents connect to the RAG search pipeline via MCP, and how to rebuild the MCP infrastructure from scratch.

### 👉 5. [HINDSIGHT_SETUP.md](./HINDSIGHT_SETUP.md)
Hindsight app setup and operations — covers Docker Compose architecture (Hindsight + Postgres), backup and restore procedures, environment configuration, and operational notes.

**Best for:** Operating and maintaining the Hindsight long-term memory system.

---

## Quick Reference

| Component | Detail |
|---|---|
| Vector DB | LanceDB (`nutanix_rag_v3` — ~1.2 GB) |
| Embedding | Jina AI `jina-embeddings-v5-text-small` (1024 dims) |
| Classifier | Gemma 4 31B (for topic-based scoring boost, 3s timeout) |
| Intent Routing | Keyword + entity-based dynamic filter construction |
| Entity Extraction | tagger_v3 — 22 Nutanix products + 24 ecosystem entities |
| Reranker | jina-reranker-v3 (Jina AI, listwise, top 30→5) |
| Index | IvfHnswPq vector + FTS + scalar (access_level, doc_type, primary_product) |
| Chunk size | 1024 tokens / 100 token overlap |
| DB size | **129,732 chunks** / ~1.2 GB |
| Query latency | ~6–8s (warm) |
| Pipeline | 7-stage: intent routing → embed → LanceDB search → expand → rerank → score → format |
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
| `HINDSIGHT_SETUP.md` | Hindsight memory system setup |
| `RAG_Pipeline_Diagram.png` | Architecture diagram |
