# NX_Shield RAG Embedding Pipeline — Documentation

> **Last updated:** 2026-05-12
> **Scripts:** `embed_pipeline_v3.py` (batch) / `embed_one.py` (single file) + `tagger_v3.py` + `kuzu_writer.py`
> **Status:** Active — 85,642 chunks in LanceDB `nutanix_rag_v3_dedup`, 72,489 Chunk nodes in Kuzu `nutanix_graph_v3`

---

## Overview

The ingestion pipeline for the Nutanix RAG knowledge base. It scans markdown/text/HTML/PDF files from the source document repository, chunks them intelligently, extracts rich metadata, embeds them via Jina AI, stores them in LanceDB (`nutanix_rag_v3_dedup`), and updates the Kuzu graph DB (`nutanix_graph_v3`).

The primary per-file script is `embed_one.py`. `embed_pipeline_v3.py` handles batch embedding of many files at once. `tagger_v3.py` provides inline metadata extraction (products, ecosystem entities, versions). `kuzu_writer.py` creates Chunk nodes in Kuzu for graph-to-vector bridging.

**Key change (2026-05-12):** Deduplication at embed time. The pipeline checks each chunk's `chunk_hash` against the LanceDB table BEFORE calling the Jina embedding API — saving API costs on duplicate chunks. Insert uses `merge_insert("chunk_hash")` instead of plain `add()`.

It supports three modes:

| Mode | Command | Use Case |
|---|---|---|
| **Single file** | `python3 embed_one.py <rel_path>` | Embed a single file (preferred for daily updates) |
| **Batch incremental** | `python3 embed_pipeline_v3.py` | Add/update many files without rebuilding everything |
| **Full rebuild** | `python3 embed_pipeline_v3.py --clean` | Complete rebuild from scratch (old table backed up first) |

---

## Pipeline Flow

```
SOURCE REPOSITORY

  embed_one.py <rel_path>  OR  embed_pipeline_v3.py

  Per file:
  ├── Checkpoint skip — skip if content_hash unchanged
  ├── File-level dedup (MD5 of normalized content)
  ├── Quality check — reject garbage content (HTML entities, low alpha ratio)
  └── LARGE_FILE pre-chunking (Slack: 60K split; GitHub: 45K split)

  +--> SMART CHUNKING
  |     split_into_chunks()
  |     - Split on ## headers first
  |     - 1024 tokens per chunk / 100 token overlap
  |     - Hard-split fallback for oversized sections

  |  apply_v3_tags() — from tagger_v3 (inline)
  |  - access_level, doc_type, primary_product (path-based)
  |  - mentioned_products, ecosystem_entities (regex from text)
  |  - versions, content_types (text + path detection)
  |  - HPE hardware detection (new 2026-05-12)
  |  - Text normalization (strips boilerplate + whitespace)

  ┌─ PRE-EMBED DEDUP ──────────────────────────────────────────┐
  │  For each chunk's chunk_hash, check if it exists in the    │
  │  LanceDB table (reads only chunk_hash column via column    │
  │  projection, avoiding loading vectors into RAM). Skip the   │
  │  Jina API call for duplicates. Saves money on re-embeds.    │
  └─────────────────────────────────────────────────────────────┘

  BATCH EMBEDDING
  |
  |  embed_texts() — Jina API primary
  |  embed_texts() — LM Studio fallback (localhost:1234)
  |  Batch size: 5 texts per API call
  |
  LANCEDB (nutanix_rag_v3_dedup)
  |
  |  merge_insert("chunk_hash") — dedup on insert
  |  when_not_matched_insert_all() — only new chunks
  |  Checkpoint saved AFTER every file (crash-resilient)
  |
  KUZU GRAPH (nutanix_graph_v3)
  |
  |  kuzu_writer.write_chunk_batch() — MERGE Chunk nodes
  |  By chunk_hash — creates graph-to-vector bridge
  |  Entity/relationship edges from vault extraction
  |
Done. 85,642 records in LanceDB + checkpoint updated.
```

---

## Supported File Types

| Category | Extensions | Notes |
|---|---|---|
| Text | `*.md`, `*.txt`, `*.html` | Standard markdown/text content |
| Code | `*.py`, `*.go`, `*.yaml`, `*.yml`, `*.tf`, `*.sh`, `*.php`, `*.js`, `*.json` | GitHub code samples, Terraform, Ansible |
| PDF | `*.pdf` | Parsed via **Docling** (table-aware) with **markitdown** fallback |

---

## Database Tables

### LanceDB: `nutanix_rag_v3_dedup` (85,642 records)

Built by deduplicating `nutanix_rag_v3_with_hash` (129,845 records) by (`chunk_hash`, `rel_path`, `chunk_index`).

**Indices:**
| Index Type | Column | Params |
|---|---|---|
| BTree | `chunk_hash` | — |
| FTS | `text` | Tantivy |
| IVF_HNSW_SQ | `vector` | m=20, ef_construction=300, cosine |

The old full table `nutanix_rag_v3` (129,845 records) is archived as `nutanix_rag_v3_archive`.

The table schema contains:

| Field | Type | Description |
|---|---|---|
| `vector` | float[1024] | Jina embedding |
| `text` | string | Chunk content |
| `source` | string | Full URL or file path |
| `rel_path` | string | Relative file path |
| `access_level` | string | `public` or `internal` |
| `doc_type` | string | e.g. `official_doc`, `kb_article`, `battlecard` |
| `primary_product` | string | e.g. `AHV`, `AOS`, `Prism` |
| `mentioned_products` | string[] | Nutanix products mentioned in text |
| `ecosystem_entities` | string[] | Competitors / partners mentioned |
| `versions` | string[] | Version strings like `AOS_7.5` |
| `content_types` | string[] | Taxonomy: api-reference, troubleshooting, etc. |
| `chunk_index` | int | Position in source document |
| `content_hash` | string | Content dedup hash (file-level) |
| `chunk_hash` | string | Chunk-level dedup hash (MD5 of normalized chunk text) |

### Kuzu Graph: `nutanix_graph_v3` (72,489 Chunk nodes, 48,483 Entity nodes)

See `GRAPH_DB.md` for full schema and query patterns.

---

## V3 Metadata (`tagger_v3.py`)

`tagger_v3.py` is imported as a module (`from tagger_v3 import apply_v3_tags`) and applied during chunking — not as a separate post-enrichment pass. The module provides:

- **`get_access_level(rel_path)`** — Determines `public` or `internal` based on source folder
- **`get_doc_type(rel_path)`** — Maps top-level folder to document type
- **`get_primary_product(rel_path, text)`** — Maps portal subdirectory to product, with frequency-based fallback
- **`extract_mentioned_products(text)`** — Regex detection of 22 Nutanix product names
- **`extract_ecosystem_entities(text)`** — Regex detection of 24 competitor/partner entities
- **`extract_versions(text)`** — Version string extraction for AOS, AHV, Prism, NKP, NDB, Files, Objects
- **`extract_content_types(text, path)`** — Content type detection (8 types)

**Internal folders** (not visible to NX_Shield):
`slack`, `whatsapp`, `internal`, `google-docs`, `inbound`

---

## Key Functions

### File Discovery

**`get_all_files(root)` / `get_all_markdown_files(root)`**
- Recursively scans source directory for supported file types
- Skips: `pipeline/` folder, files < 100 bytes
- Extracts `Source:` URL from file header if present
- PDF parsing: Docling (table-aware) → markitdown fallback
- Returns: `List[Dict]` with `path`, `rel_path`, `source`, `content`, `size`, `is_pdf`

### PDF Parsing

**`parse_pdf(pdf_path)`**
- **Docling (primary):** Table-aware PDF parsing with proper markdown table structure. ML models loaded once and reused for all PDFs in a run.
- **markitdown (fallback):** Plain text extraction for PDFs when Docling is unavailable or fails.
- `USE_DOCLING = True` — set to `False` to force markitdown-only.

### Metadata Extraction (Initial)

**`extract_metadata(text, rel_path, source)`** — Initial metadata extraction per chunk:

**Products detected (22 patterns):**
AOS, AHV, Prism, Flow, Karbon, NKP, NDB, Files, Objects, LCM, Foundation, v4 API, NCI, NC2, Vanguard, Calm, Volumes, Move, Era, NCC, X-Ray, IAM

**Content types detected (8 patterns):**
api-reference, admin-guide, troubleshooting, release-notes, compatibility, faq, architecture, presentation

### Chunking

**`split_into_chunks(text, rel_path, source, chunk_tokens=1024, overlap_tokens=100)`**
1. Split on `##` headers — preserves section boundaries
2. 100 tokens overlap for context continuity
3. Hard-split fallback for oversized sections
4. Min chunk size: 100 chars

**`split_large_file(text, rel_path)`** — Pre-chunking for large files (Slack exports up to 60K chars, GitHub code at 45K chars)

### Embedding

**`embed_texts(texts, api_key)` → `List[List[float]]`**

| Provider | Endpoint | Model | Dimensions | Timeout |
|---|---|---|---|---|
| Jina AI (primary) | Jina API | `jina-embeddings-v5-text-small` | 1024 | 90s + 1 retry |
| LM Studio (fallback) | localhost:1234 | same | 1024 | 60s |

Batch size: **5 texts per API call**

### LanceDB Operations

**`init_lancedb_v2(clean=False)`** — Opens or creates `nutanix_rag_v3` table
**`safe_rebuild_table(files, batch_size=5, test_mode=False)`** — Atomic full rebuild with backup
**`add_chunks_to_table(table, chunks, embeddings, batch_info)`** — Batch insert

**Index build (post-swap):**
1. **IVF_HNSW_SQ vector index** — `m=20`, `ef_construction=300`, cosine metric
2. **FTS index** — on `text` column
3. **BTree scalar index** — on `chunk_hash`

### Checkpoint System

**`processed_files.json`** — crash-resilient incremental processing
- Updated after every single file — never lost on crash
- Stores set of already-processed `rel_path` strings
- On restart: skips files in checkpoint (incremental mode)

---

## Files to Skip

**`SKIP_FILES`** — excluded from embedding:

| File | Reason |
|---|---|
| `slack/tc_nkp_kubernetes.txt` | Embedded as 35 records via alternative path |
| `slack/tc_calm_error.txt` | Embedded as 27 records via alternative path |
| `non_advisory_backup.json` | Pre-existing LanceDB export, not a real source doc — inflates record count |

---

## Configuration Constants

| Constant | Value | Notes |
|---|---|---|
| `EMBED_MODEL` | `jina-embeddings-v5-text-small` | Must match query pipeline |
| `EMBED_DIMENSIONS` | `1024` | Must match query pipeline |
| `CHUNK_TOKENS` | `1024` | Per chunk |
| `CHUNK_OVERLAP_TOKENS` | `100` | Overlap between chunks |
| `CHARS_PER_TOKEN` | `4` | Rough estimate for chunk sizing |
| `BATCH_SIZE` | `5` | Texts per embed API call |
| `USE_DOCLING` | `True` | PDF parsing mode |

---

## Usage

### Incremental Update

```bash
python embed_pipeline_v3.py
```

### Full Rebuild

```bash
python embed_pipeline_v3.py --clean
```

### Test Mode (3 files only)

```bash
python embed_pipeline_v3.py --test
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Jina API timeout | Retry once; fall back to LM Studio if retry fails |
| Jina API error (non-200) | Print error; fall back to LM Studio |
| LM Studio unavailable | Print warning; skip batch |
| LanceDB write fails | Exception propagates; checkpoint already saved |
| File read error | Skip file; continue with next |
| PDF Docling fails | Fall back to markitdown automatically |

---

## Related Scripts

| Script | Purpose |
|---|---|---|
| `embed_pipeline_v3.py` | Full ingestion pipeline (chunking + embedding + inline metadata via tagger_v3) |
| `tagger_v3.py` | V3 metadata extraction module (access level, entities, content types, versions) |
| `selective_embed.py` | Incremental — embed specific files or folders |
| `embed_portal.py` | Portal-specific scraping + embedding |
| `embed_solutions.py` | Nutanix Solutions KB embedding |
| `embed_security_advisories_v2.py` | Security bulletin PDF embedding |

---

## Change Log

| Date | Change |
| Date | Change |
|---|---|
| 2026-05-12 | **Major pipeline overhaul.** Switched to `nutanix_rag_v3_dedup` (85k deduped records). Added pre-embed dedup (checks chunk_hash before Jina API call). Switched to `merge_insert("chunk_hash")` from `table.add()`. Added Kuzu graph integration (Chunk nodes by chunk_hash). Updated vector index to IVF_HNSW_SQ (m=20, ef=300). `embed_one.py` is now the primary embed tool. HPE hardware tagging added to `tagger_v3.py`. |
| 2026-05-03 | Updated documentation for nutanix_rag_v3 schema, tagger_v3.py enrichment, IvfHnswPq index |
| 2026-04-23 | Added Docling PDF parsing (table-aware). Added `*.pdf` to supported file types. |
| 2026-04-23 | Added code file extensions: `*.py`, `*.go`, `*.yaml`, `*.yml`, `*.tf`, `*.sh`, `*.php`, `*.js`, `*.json` |
| 2026-04-23 | Added `non_advisory_backup.json` to SKIP_FILES |
| 2026-04-23 | Updated HNSW index params: `m=16`, `ef_construction=200` |
| 2026-04-23 | Added `wait_for_index(["text_idx"])` for race condition prevention |
| 2026-04-23 | Scalar indices on `products`, `subcategory`, `folder`, `category` |
| 2026-04-19 | Added Vanguard, Move, Era to PRODUCT_PATTERNS |
| 2026-04-16 | Added NCC, X-Ray, Calm, Volumes to PRODUCT_PATTERNS |
| 2026-04-16 | `safe_rebuild_table()` for atomic full rebuilds |
| 2026-04-15 | Slack message-split chunking (60K char limit) |
