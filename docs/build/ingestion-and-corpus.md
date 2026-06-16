# Ingestion and Corpus Build

The ingestion pipeline should produce a searchable, policy-aware corpus — not just chunks.

## Target output

Each ingested unit should have:

- clean text,
- source identity,
- document and section identity,
- product/version metadata,
- source family and authority,
- access/confidentiality class,
- stable hashes,
- embedding vector,
- lexical-search text,
- optional graph/entity extraction output,
- governance metadata such as approved use scope, owner, review status, and retention/removal expectations where applicable.

## Recommended stages

```mermaid
flowchart LR
  S[Source documents] --> N[Normalize text]
  N --> M[Extract metadata]
  M --> C[Chunk / page units]
  C --> H[Hash + identity]
  H --> E[Embeddings]
  H --> X[Entity extraction]
  E --> L[LanceDB rows]
  X --> K[Kuzu graph backfill]
  L --> I[Indexes]
  K --> V[Canaries]
  I --> V
```

## Source normalization

Normalize sources before embedding:

- preserve headings and section hierarchy,
- keep URLs/document IDs,
- remove navigation boilerplate,
- record version/product context,
- avoid mixing multiple documents into one anonymous text blob.

Before ingestion, also record whether the source is approved for the intended RAG use. Treat licensing, data classification, personal/customer/partner data, source-code or telemetry content, and third-party analyst material as approval gates, not as after-the-fact cleanup.

## Chunking strategy

Use chunking that respects source structure. For technical docs, headings and sections often matter more than arbitrary token windows.

Good chunks should be:

- small enough for precise retrieval,
- large enough to contain procedure context,
- linked to parent document/section,
- stable across rebuilds where possible.

## Indexes

A mature RAG store usually needs:

- vector index for semantic recall,
- FTS index for exact terms,
- scalar indexes for source family/access/product/version,
- stable identity fields for deduplication.

The current unified v4 LanceDB contract uses one embedding vector column, one lexical `search_text` column, and scalar indexes over identity, source, access, version, and lineage fields. The public-safe schema is documented in [LanceDB schema](../design/lancedb-schema.md).

Benchmark before adding indexes. Index churn without measured need can complicate rebuilds.

## Private source mapping

Private source files that correspond to ingestion:

```text
ipccheng/NX-Shield-RAG-src
├── rag/hermes-nutanix/ingestion/
├── rag/hermes-nutanix/ingestion/openclaw_pipeline/
├── rag/hermes-nutanix/scripts/openclaw/tagger_v3.py
├── rag/hermes-nutanix/scripts/openclaw/kuzu_writer.py
└── rag/hermes-nutanix/scripts/openclaw/kuzu_backfill.py
```

These paths are implementation references, not public dependencies.
