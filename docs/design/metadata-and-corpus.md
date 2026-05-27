# Metadata and Corpus Design

Metadata is not decoration. In an enterprise RAG system, metadata is the control plane for retrieval quality and safety.

## Core fields to model

A robust technical-support corpus should include fields like:

- `source_family` — official docs, KB, design guide, validated design, community, team chat, etc.
- `confidentiality` or `access_level` — public, partner, internal, private.
- `product` / `products` — normalized product families and aliases.
- `version` / `versions` — versions mentioned or targeted by the source.
- `document_id` — stable identity for deduplication and lineage.
- `section_id` — stable section/page identity.
- `chunk_hash` / `content_hash` — dedupe and rebuild integrity.
- `source_authority` — a coarse authority class, not a substitute for relevance.
- `migration_source` — lineage when old corpora are transformed into a new schema.

## Why source family matters

Different source families carry different risk:

- Official product docs can support procedures and features.
- KBs can support known issues and workarounds.
- Validated designs can support architecture patterns.
- Community blogs can provide hints but need corroboration.
- Team chat can be useful internally but should not be exposed in public/partner modes.

The answer layer should know which family each claim came from.

## Unified corpus concept

The implementation uses a unified-corpus pattern: keep the active query path simple while preserving lineage from multiple generations of content.

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
