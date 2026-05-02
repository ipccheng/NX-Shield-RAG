# NX_Shield RAG Pipeline

A Retrieval-Augmented Generation (RAG) knowledge base for Nutanix technical support. Used by **Sam** and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

---

## Architecture

![NX_Shield RAG Pipeline Architecture](https://github.com/ipccheng/rag-pipeline/blob/main/RAG%20Pipeline%20Diagram.png)

---

## Documents

### 👉 1. [RAG_PIPELINE_ARCHITECTURE.md](./RAG_PIPELINE_ARCHITECTURE.md)
Full pipeline documentation — covers the query processing flow, LanceDB schema, intent-based dynamic filter routing, entity extraction, cross-encoder reranking, score multipliers, confidence thresholds, MCP server integration, and runtime infrastructure.

**Best for:** Understanding how a query moves from user input to formatted response.

---

### 👉 2. [EMBED_PIPELINE.md](./EMBED_PIPELINE.md)
Ingestion pipeline documentation — covers smart chunking, metadata extraction (22 products, 8 content types), Jina AI embedding, LanceDB storage, checkpoint system, and the atomic rebuild process.

**Best for:** Understanding how source documents are processed, chunked, and loaded into the vector database.

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
| Pipeline | 5-stage: intent routing → embed → LanceDB search → expand → rerank → score → format |
| Agents | Sam, NX_Shield (Discord bot) |

---

## Repo Contents

| File | Description |
|---|---|
| `README.md` | This file |
| `RAG_PIPELINE_ARCHITECTURE.md` | Query pipeline full documentation |
| `EMBED_PIPELINE.md` | Ingestion pipeline full documentation |
| `RAG_Pipeline_Diagram.png` | Architecture diagram (exported from draw.io) |
