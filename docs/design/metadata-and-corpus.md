# Metadata and Corpus Design

Metadata is not decoration. In an enterprise RAG system, metadata is the control plane for retrieval quality and safety.

## Core fields to model

The active unified v4 corpus uses these field groups. See [LanceDB schema](lancedb-schema.md) for the full public-safe schema contract.

A robust technical-support corpus should include fields like:

- `source_family` — Portal docs, support KB, validated design, competitive collateral, team chat, Helm/chart, advisory, legacy import, etc.
- `source_type` — support KB, official documentation, API spec, competitive enablement, field discussion, and similar source-specific types.
- `source_authority` / `source_authority_score` — coarse authority class plus a bounded numeric signal.
- `access_scope` / `confidentiality` — public, partner, internal, support-portal, or similar policy classes.
- `primary_product`, `mentioned_products`, `normalized_versions`, `version_mentions_raw` — product/version metadata for scoped retrieval.
- `doc_id`, `guide_id`, `page_id`, `section_id` — stable document/page/section identity.
- `chunk_hash`, `content_hash`, `unique_page_key`, `unique_chunk_key` — dedupe, integrity, and rebuild identity.
- `text`, `search_text`, `text_markdown`, `vector` — display text, lexical text, Markdown-preserved text, and embedding vector.
- `legacy_v3_chunk_hash`, `legacy_rel_path`, `legacy_v3_source`, `migration_source` — lineage when old corpora are transformed into the current schema.

## Why source family matters

Different source families carry different risk:

- Official product docs can support procedures and features.
- KBs can support known issues and workarounds.
- Validated designs can support architecture patterns.
- Community blogs can provide hints but need corroboration.
- Team chat can be useful internally but should not be exposed in public/partner modes.

The answer layer should know which family each claim came from.

## Unified corpus concept

The implementation uses a unified-corpus pattern: keep the active query path simple while preserving lineage from multiple generations of content. The active v4 shape combines native/current evidence and transformed legacy rows in one table contract rather than forcing the runtime to choose between parallel stores.

A row should answer:

- Where did this text come from?
- What document/section does it belong to?
- Is it public, partner, internal, or private?
- Which product/version does it mention?
- Is it native to the current ingestion pipeline or migrated from an older store?

## Anti-patterns

Avoid these:

- only storing raw text and vector,
- treating all sources as equal,
- filtering access policy only after retrieval,
- hard-coding live row counts in public docs,
- overwriting old stores in-place without rollback,
- duplicating full text into a graph DB when a document identity link is enough.

## Schema evolution rule

Prefer **side-by-side rebuilds** over live mutation when changing metadata contracts.

Rebuild flow:

1. create new schema/table,
2. transform old rows with explicit lineage,
3. add indexes,
4. run retrieval and answer-path canaries,
5. switch runtime config,
6. keep old stores as rollback until soak completes.
