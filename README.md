# NX Shield RAG

A Retrieval-Augmented Generation (RAG) knowledge base for Nutanix technical support. Used by **Sam** and **NX_Shield** to answer Nutanix product, KB, and troubleshooting questions.

---

## Current RAG Evidence Test

Production-style RAG query using the active LanceDB-centered search path.

**Query:** `"Please provide a comparative summary of VMware Private AI and Nutanix Enterprise AI (NAI)"` *(2026-05-28, active pipeline)*

| Metric | Current RAG result |
|--------|--------------------|
| **Query class** | `competitive_comparison` |
| **Evidence verdict** | **weak** — VMware Private AI evidence was missing or indirect in the top retrieved results |
| **Query latency** | **10.25s** end-to-end direct script run with Slack/Web fallbacks disabled |
| **Candidate set** | 169 unique retrieved candidates, reranked top 50 |
| **Top NAI source** | `google-docs/2026-04-07/NAI All in One Solution Kit For Sellers.txt` — final score 0.746, graph-verified |
| **Top VMware-side source** | `xpress-md/Broadcom_Compete_Technical_Discovery_Template.md` — final score 0.676, graph-verified; useful but not sufficient for confident VMware Private AI claims |
| **Answer policy** | Evidence Ledger requires missing competitor-side evidence to be disclosed; unsupported VMware licensing, pricing, roadmap, or bundling claims must be omitted or marked unknown |

### What the test shows

The RAG pipeline retrieved strong Nutanix Enterprise AI / NAI material and some VMware/Broadcom competitive context, but it did **not** retrieve enough direct VMware Private AI evidence to support a fully confident competitor-side comparison. The correct answer behavior is therefore to summarize NAI from retrieved sources, include only source-backed VMware context, and explicitly caveat that direct VMware Private AI evidence is weak or missing.

For anything requiring domain accuracy — Nutanix compatibility lists, KB references, lifecycle dates, competitive positioning, licensing, pricing, or roadmap claims — the Evidence Ledger is more important than raw answer fluency. A weak verdict should produce a careful answer with named sources and clear gaps, not a confident but unsupported comparison.

---

## Graph Context and Evidence Policy

Kuzu is an **advisory graph DB layer** that walks the entity co-occurrence graph to verify and boost chunks whose tagged entities match structural connections found in the source corpus.

### What Happens on the VMware Private AI vs NAI Query

For `"Please provide a comparative summary of VMware Private AI and Nutanix Enterprise AI (NAI)"`, the active pipeline:

1. Walks the Kuzu graph `(Chunk)-[r]->(Entity)` for entities connected to query terms such as VMware, Private AI, Nutanix Enterprise AI, and NAI
2. Cross-matches graph entity names against LanceDB metadata fields such as `ecosystem_entities` and `mentioned_products`
3. Boosts graph-verified matches before cross-encoder reranking
4. Emits an Evidence Ledger verdict so the answer can disclose when one side of a comparison is under-evidenced

### Current Test Figures (2026-05-28)

| Metric | Figure |
|--------|--------|
| **Retrieved candidates** | 169 unique candidates before reranking |
| **Rerank scope** | Top 50 candidates reranked |
| **Graph-verified result set** | 50 reranked results carried graph context |
| **Graph-authoritative suggestions** | 3 source suggestions attached as advisory context |
| **Latency** | 10.25s direct script run with Slack/Web fallbacks disabled |

### Why It Matters

Vector similarity finds *linguistically similar* chunks. Kuzu finds *structurally related* chunks — documents that frequently mention the same entities together in the source corpus. Combining both signals helps identify related competitive and product-context material, but graph relevance is not answer sufficiency. The Evidence Ledger still decides whether the retrieved sources are strong enough for a confident answer.

See [GRAPH_DB.md](./GRAPH_DB.md) for full schema, entity extraction, and query patterns.

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
