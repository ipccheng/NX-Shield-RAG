# NX_Shield RAG Embedding Pipeline — Documentation

> **Last updated:** 2026-04-23
> **Author:** Sam (OpenClaw agent for Ivan)
> **Script:** `embed_pipeline_v2.py`
> **Status:** Active — used for initial ingestion and incremental updates

---

## Overview

`embed_pipeline_v2.py` is the **ingestion pipeline** for the Nutanix RAG knowledge base. It scans markdown/text/HTML/PDF files from the local `rag/nutanix/` repository, chunks them intelligently, extracts rich metadata, embeds them via Jina AI, and stores the results in LanceDB.

It supports two modes:

| Mode | Command | Use Case |
|---|---|---|
| **Incremental** | `python embed_pipeline_v2.py` | Add/update individual files without rebuilding everything |
| **Full rebuild** | `python embed_pipeline_v2.py --clean` | Complete rebuild from scratch (old table backed up first) |

---

## Pipeline Flow

```
RAG_ROOT (~/.openclaw/workspace/rag/nutanix/)

  get_all_files()
  ├── Text files: *.md, *.txt, *.html
  ├── Code files: *.py, *.go, *.yaml, *.yml, *.tf, *.sh, *.php, *.js, *.json
  └── PDF files: *.pdf (parsed via Docling or markitdown)

  Per file:
  ├── Checkpoint skip — skip if already processed
  ├── SKIP_FILES — user-requested skips
  └── LARGE_FILES — pre-chunked to stay under token limit

  +--> LARGE FILE PRE-CHUNK
  |     split_large_file() — Slack: message-split; GitHub: hard-split

  +--> SMART CHUNKING
  |     split_into_chunks()
  |     - Split on ## headers first
  |     - 1024 tokens per chunk / 100 token overlap
  |     - Hard-split fallback for oversized sections

  |  extract_metadata()
  |  - Products (regex on 22 product patterns)
  |  - Versions (AOS, AHV, Prism, NKP, NDB, Files, Objects)
  |  - Content types (api-reference, admin-guide, troubleshooting, etc.)
  |  - Folder (top-level directory)
  |
  BATCH EMBEDDING
  |
  |  embed_texts() — Jina API primary (90s timeout + 1 retry)
  |  embed_texts() — LM Studio fallback (localhost:1234)
  |  Batch size: 5 texts per API call
  |
  LANCEDB
  |
  |  add_chunks_to_table() — add to nutanix_rag_v2
  |  Checkpoint saved AFTER every file (crash-resilient)
  |
Done. Records in LanceDB + checkpoint updated.
```

---

## Supported File Types

| Category | Extensions | Notes |
|---|---|---|
| Text | `*.md`, `*.txt`, `*.html` | Standard markdown/text content |
| Code | `*.py`, `*.go`, `*.yaml`, `*.yml`, `*.tf`, `*.sh`, `*.php`, `*.js`, `*.json` | GitHub code samples, Terraform, Ansible |
| PDF | `*.pdf` | Parsed via **Docling** (table-aware) with **markitdown** fallback |

---

## Key Functions

### File Discovery

**`get_all_files(root)`** / **`get_all_markdown_files(root)`**
- Recursively scans `RAG_ROOT` for supported file types
- Supported: `*.md`, `*.txt`, `*.html`, `*.py`, `*.go`, `*.yaml`, `*.yml`, `*.tf`, `*.sh`, `*.php`, `*.js`, `*.json`, `*.pdf`
- Skips: `pipeline/` folder, files < 100 bytes
- Extracts `Source:` URL from file header if present
- PDF parsing: Docling (table-aware) → markitdown fallback
- Returns: `List[Dict]` with `path`, `rel_path`, `source`, `content`, `size`, `is_pdf`

### PDF Parsing (NEW 2026-04-23)

**`parse_pdf(pdf_path)`**
- **Docling (primary):** Table-aware PDF parsing with proper markdown table structure. ML models loaded once and reused for all PDFs in a run.
- **markitdown (fallback):** Plain text extraction for PDFs when Docling is unavailable or fails.
- `USE_DOCLING = True` — set to `False` to force markitdown-only.

**Lazy-loading design:** `DocumentConverter` loads heavy ML models (layout, OCR, table detection) once at most. A shared `_DOCLING_CONVERTER` instance is created lazily on first PDF processed and reused for all subsequent PDFs.

### Metadata Extraction

**`extract_metadata(text, rel_path, source)`**
Extracts structured metadata from chunk text and file path.

**Products detected (22 patterns):**

| Product | Regex Pattern |
|---|---|
| AOS | `\bAOS\b` |
| AHV | `\bAHV\b` |
| Prism | `\bPrism Central?\b\|\bPrism\b` |
| Flow | `\bFlow\b` |
| Karbon | `\bKarbon\b` |
| NKP | `\b(NKP\|Nutanix Kubernetes Platform)\b` |
| NDB | `\b(NDB\|Nutanix Database Service)\b` |
| Files | `\bNutanix Files\b` |
| Objects | `\bNutanix Objects\b` |
| LCM | `\bLCM\b` |
| Foundation | `\bFoundation\b` |
| v4 API | `\bv4 API\b\|v4-api` |
| NCI | `\bNCI\b` |
| NC2 | `\bNC2\b\|Cloud Clusters on Azure` |
| Vanguard | `\bVanguard\b` |
| Calm | `\bCalm\b` |
| Volumes | `\bVolumes\b` |
| Move | `\bMove\b` |
| Era | `\bEra\b` |
| NCC | `\bNCC\b\|\bNutanix\s+Cluster\s+Check` |
| X-Ray | `\bX-Ray\b` |

**Content types detected:**
| Type | Regex Trigger |
|---|---|
| api-reference | API, SDK, REST, endpoint, GET, POST, PUT, DELETE |
| admin-guide | install, config, deploy, setup, manage, admin |
| troubleshooting | error, issue, fix, debug, troubleshoot, KB |
| release-notes | release, GA, EOSL, EOL, version, announced |
| compatibility | compat, support matrix, Hardware, supportability |
| faq | FAQ, question |
| architecture | architect, design, diagram, topology |
| presentation | slide, deck, webinar, presentation |

### Chunking

**`split_into_chunks(text, rel_path, source, chunk_tokens=1024, overlap_tokens=100)`**

Smart chunking strategy:
1. **Split on `##` headers** — preserves section boundaries
2. **Overlap** — 100 tokens carried over between chunks for context continuity
3. **Hard-split fallback** — if a section itself exceeds `chunk_tokens`, `_hard_split()` breaks it by character count with overlap
4. **Min chunk size** — chunks < 100 chars discarded

**`split_large_file(text, rel_path)`**

Special pre-chunking for known large files that would otherwise exceed token limits:

| File Pattern | Max Chars | Strategy |
|---|---|---|
| `slack/prism_Prism.txt` | 60,000 | Split by Slack message timestamp |
| `slack/foundation_Foundation.txt` | 60,000 | Split by Slack message timestamp |
| `github/nutanix/_nutanix_nutanix.ansible.md` | 45,000 | Hard-split fallback |

Slack message pattern: split on `\n(?=\[\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}:\d{2} (?:AM|PM)\])`

### Embedding

**`embed_texts(texts, api_key)` → `List[List[float]]`**

| Provider | Endpoint | Model | Dimensions | Timeout |
|---|---|---|---|---|
| Jina AI (primary) | `https://api.jina.ai/v1/embeddings` | `jina-embeddings-v5-text-small` | 1024 | 90s + 1 retry |
| LM Studio (fallback) | `http://localhost:1234/v1/embeddings` | same | 1024 | 60s |

Batch size: **5 texts per API call** — small enough to stay safe under Jina's limits.

### LanceDB Operations

**`init_lancedb_v2(clean=False)`**
- Opens or creates `nutanix_rag_v2` table at `~/.openclaw/memory/lancedb-pro/`
- Schema: `vector`, `text`, `source`, `category`, `subcategory`, `file_path`, `rel_path`, `products`, `versions`, `content_types`, `folder`, `chunk_index`, `total_chunks`
- **Never deletes the existing table** — even with `clean=True`
- Use `safe_rebuild_table()` for destructive rebuilds

**`safe_rebuild_table(files, batch_size=5, test_mode=False)`**

Atomic full rebuild:
1. Creates temporary table `nutanix_rag_v2_rebuild_{timestamp}`
2. Embeds all files into it (ignores checkpoint)
3. On success: backs up old table → replaces with new table
4. On failure: old table remains untouched
5. Builds HNSW vector index + FTS index + scalar indices after swap

**Index build (post-swap) in `safe_rebuild_table()`:**
1. **HNSW vector index** — `IVF_HNSW_SQ`, `m=16`, `ef_construction=200`, `L2` metric
2. **Tantivy FTS index** — on `text` column, with `wait_for_index` to prevent race conditions during atomic table swaps
3. **Scalar indices** — on `products`, `subcategory`, `folder`, `category`

**`add_chunks_to_table(table, chunks, embeddings, batch_info)`**
- Converts embeddings to list format, truncates `text` to 8000 chars
- Stores `products`, `versions`, `content_types` as JSON strings
- Sets `chunk_index` and `total_chunks` for ordering

### Checkpoint System

**`processed_files.json`** — crash-resilient incremental processing

- Saved to `pipeline/processed_files.json`
- Updated **after every single file** — never lost on crash
- Checkpoint stores set of already-processed `rel_path` strings
- On restart: skips files in checkpoint (incremental mode)

**Why checkpoint over LanceDB count:**
> LanceDB full-table reads can fail due to corrupted data files. The checkpoint file is the crash-resilient source of truth — it survives pipeline restarts even when LanceDB can't be read.

---

## Files to Skip

**`SKIP_FILES`** — these files are excluded from embedding:

| File | Reason |
|---|---|
| `slack/tc_nkp_kubernetes.txt` | User requested skip (now embedded as 35 records via alternative) |
| `slack/tc_calm_error.txt` | User requested skip (now embedded as 27 records via alternative) |
| `non_advisory_backup.json` | Pre-existing LanceDB export, not a real source doc — inflates record count by 96K |

---

## Configuration Constants

| Constant | Value | Notes |
|---|---|---|
| `RAG_ROOT` | `~/.openclaw/workspace/rag/nutanix` | Source documents |
| `EMBED_MODEL` | `jina-embeddings-v5-text-small` | Must match query pipeline |
| `EMBED_DIMENSIONS` | `1024` | Must match query pipeline |
| `CHUNK_TOKENS` | `1024` | Per chunk |
| `CHUNK_OVERLAP_TOKENS` | `100` | Overlap between chunks |
| `CHARS_PER_TOKEN` | `4` | Rough estimate for chunk sizing |
| `JINA_EMBED_URL` | `https://api.jina.ai/v1/embeddings` | Primary embed endpoint |
| `LM_STUDIO_URL` | `http://localhost:1234/v1/embeddings` | Fallback embed endpoint |
| `BATCH_SIZE` | `5` | Texts per embed API call |
| `USE_DOCLING` | `True` | Set to `False` to force markitdown for PDFs |

---

## Usage

### Incremental Update (most common)
```bash
cd ~/.openclaw/workspace/rag/nutanix/pipeline
python embed_pipeline_v2.py
```

- Scans for new/updated files
- Skips already-processed files via checkpoint
- Adds new records to existing LanceDB table

### Full Rebuild
```bash
python embed_pipeline_v2.py --clean
```

- Creates temporary table with timestamp suffix
- Embeds all files fresh (ignores checkpoint)
- Swaps in new table, backs up old one atomically
- Builds HNSW + Tantivy FTS + scalar indices

### Test Mode (3 files only)
```bash
python embed_pipeline_v2.py --test
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `JINA_API_KEY` | Yes (primary) | Jina AI API key for embeddings |
| `OPENCLAW_MCP_KEY` | No | MCP server key (not used by this script) |

---

## Index Build (Post-Ingest)

After a full rebuild, `safe_rebuild_table()` creates three types of indices:

### 1. HNSW Vector Index (Semantic Search)
- Type: `IVF_HNSW_SQ`
- Metric: `L2`
- `m=16`, `ef_construction=200`

### 2. Tantivy FTS Index (Keyword Search)
- Column: `text`
- Uses Tantivy engine (native Rust full-text search)
- `wait_for_index(["text_idx"])` — prevents race conditions during atomic table swaps

### 3. Scalar Indices (Pre-Filtered Queries)
- `products` — filter by Nutanix product
- `subcategory` — filter by primary product
- `folder` — filter by source folder
- `category` — filter by content category

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Jina API timeout | Retry once; fall back to LM Studio if retry fails |
| Jina API error (non-200) | Print error; fall back to LM Studio |
| LM Studio unavailable | Print warning; skip batch |
| No Jina API key | Exit with error message |
| LanceDB write fails | Exception propagates; checkpoint already saved for processed files |
| File read error | Skip file; continue with next |
| PDF Docling fails | Fall back to markitdown automatically |
| markitdown also fails | Skip PDF with warning |

---

## Related Scripts

| Script | Purpose |
|---|---|
| `embed_pipeline_v2.py` | Full ingestion pipeline (this doc) |
| `selective_embed.py` | Incremental — embed specific files or folders |
| `embed_portal.py` | Portal-specific scraping + embedding |
| `embed_solutions.py` | Nutanix Solutions KB embedding |
| `embed_security_advisories_v2.py` | Security bulletin PDF embedding |
| `run_selective_embed.sh` | Shell wrapper for selective embed |

---

## Change Log

| Date | Change |
|---|---|
| 2026-04-23 | Added Docling PDF parsing (table-aware) with markitdown fallback. Lazy-loaded DocumentConverter (ML models loaded once, reused for all PDFs). Added `*.pdf` to supported file types. |
| 2026-04-23 | Added code file extensions: `*.py`, `*.go`, `*.yaml`, `*.yml`, `*.tf`, `*.sh`, `*.php`, `*.js`, `*.json` |
| 2026-04-23 | Added `non_advisory_backup.json` to SKIP_FILES (not a real source doc) |
| 2026-04-23 | Updated HNSW index params: `m=16`, `ef_construction=200` (was `m=20`, `ef_construction=300`) |
| 2026-04-23 | Added `wait_for_index(["text_idx"])` after FTS index to prevent race conditions during table swaps |
| 2026-04-23 | Added scalar indices on `products`, `subcategory`, `folder`, `category` in `safe_rebuild_table()` |
| 2026-04-23 | Renamed `get_all_markdown_files()` → `get_all_files()` (now handles text + code + PDF); old name kept as alias |
| 2026-04-19 | Added Vanguard, Move, Era to PRODUCT_PATTERNS |
| 2026-04-16 | Added NCC, X-Ray, Calm, Volumes to PRODUCT_PATTERNS |
| 2026-04-16 | Added `safe_rebuild_table()` for atomic full rebuilds |
| 2026-04-16 | Added checkpoint system for crash-resilient incremental processing |
| 2026-04-15 | Split Slack exports by message timestamp (60K char limit) |
| 2026-04-15 | Split GitHub code files at 45K chars to avoid token overflow |
