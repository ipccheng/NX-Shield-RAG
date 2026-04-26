# NX_Shield RAG Pipeline

A Retrieval-Augmented Generation (RAG) knowledge base for Nutanix technical support. Used by **Sam** (Ivan's primary assistant) and **NX_Shield** (engineer-facing support agent) to answer Nutanix product, KB, and troubleshooting questions.

---

## Architecture

![NX_Shield RAG Pipeline Architecture](https://github.com/ipccheng/rag-pipeline/blob/main/RAG%20Pipeline%20Diagram.png)

---

## Documents

### 👉 1. [RAG_PIPELINE_ARCHITECTURE.md](./RAG_PIPELINE_ARCHITECTURE.md)
Full pipeline documentation — covers the 7-stage query processing flow, LanceDB schema, classification system, products pushdown filter, reranking, score multipliers, confidence thresholds, MCP server integration, and runtime infrastructure.

**Best for:** Understanding how a query moves from user input to formatted response.

---

### 👉 2. [EMBED_PIPELINE.md](./EMBED_PIPELINE.md)
Ingestion pipeline documentation — covers smart chunking, metadata extraction (20 products, 8 content types), Jina AI embedding, LanceDB storage, checkpoint system, and the atomic rebuild process.

**Best for:** Understanding how source documents are processed, chunked, and loaded into the vector database.

---

## Quick Reference

| Component | Detail |
|---|---|
| Vector DB | LanceDB (`~/.openclaw/memory/lancedb-pro/`) |
| Embedding | Jina AI `jina-embeddings-v5-text-small` (1024 dims) |
| Classifier | Gemma 4 31B (via MacBook Tailscale, 3s timeout) |
| Reranker | jina-reranker-v3 (Jina AI, listwise, top 30→5) |
| Index | HNSW vector + BM25 FTS + scalar (products, subcategory, folder) |
| Chunk size | 1024 tokens / 100 token overlap |
| DB size | **170,708 chunks** / ~1.2 GB |
| Query latency | ~6–8s (warm) |
| Pipeline | 7-stage: classify → embed → LanceDB search → expand → rerank → score → format |
| Agents | Sam (main), NX_Shield (Discord bot) |

---

## Repo Contents

| File | Description |
|---|---|
| `README.md` | This file |
| `RAG_PIPELINE_ARCHITECTURE.md` | Query pipeline full documentation |
| `EMBED_PIPELINE.md` | Ingestion pipeline full documentation |
| `RAG_Pipeline_Diagram.png` | Architecture diagram (exported from draw.io) |
