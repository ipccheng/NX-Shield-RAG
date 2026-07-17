# LanceDB Schema

This page documents the public-safe shape of the active NX-Shield/Hermes Nutanix RAG LanceDB corpus. It is intentionally schema-focused: row counts, private paths, hostnames, and credential-bearing runtime details are not part of the public contract.

## Active table concept

The current runtime uses a unified v4 table conceptually named:

```text
nutanix_rag_v4_unified
```

The table combines:

- native v4 Portal/documentation rows,
- refreshed support KB rows,
- selected source-family refreshes such as Helm/chart and advisory content,
- transformed legacy v3 evidence rows with explicit lineage metadata.

The design goal is a single active retrieval contract with rollbackable lineage, not a pile of unrelated stores hidden behind runtime fallbacks.

## Retrieval indexes

The active schema is designed for hybrid retrieval:

| Index class | Columns | Purpose |
| --- | --- | --- |
| Vector | `vector` | Semantic recall over embedded evidence chunks. |
| Full-text | `search_text` | Exact terms: KB IDs, versions, commands, errors, product names, acronyms. |
| Identity | `chunk_hash`, `content_hash`, `unique_page_key`, `guide_id`, `page_id`, `exact_identifiers`, `identifier_types` | Deduplication, lineage, rebuild checks, exact-ID lookup, and page/document targeting. |
| Policy/source | `source_family`, `source_type`, `access_scope`, `effective_access_class`, `confidentiality`, `policy_conflict_flags`, `migration_source` | Access filtering, source routing, policy-conflict review, and lineage-aware ranking. |
| Version/product | `software_type`, `software_version_normalized` | Product/version narrowing and version-sensitive canaries. |
| Lifecycle/review | `publication_status`, `ingestion_state`, `freshness_status`, `review_status`, `last_verified_at` | Source lifecycle, freshness, and review-state audits. |

## Field groups

### Schema and identity

| Field | Type | Role |
| --- | --- | --- |
| `schema_version` | string | Schema contract marker for rebuild compatibility. |
| `chunk_hash` | string | Stable chunk identity used for dedupe and graph/LanceDB parity. |
| `content_hash` | string | Text/content hash used for duplicate detection. |
| `doc_id` | string | Stable document identity; legacy rows preserve their original lineage here. |
| `guide_id` | string | Portal guide or document-family identifier when available. |
| `page_id` | string | Page-level identifier inside a guide/document. |
| `unique_page_key` | string | Stable page identity across rebuilds. |
| `section_id` | string | Section-level identity. |
| `unique_chunk_key` | string | Stable chunk identity within page/section lineage. |
| `chunk_index` | int64 | Chunk ordinal. |
| `chunk_count` | int64 | Number of chunks in the source page/document unit. |
| `exact_identifiers` | list<string> | Normalized exact identifiers such as KB, advisory, model, or document IDs; supports a label-list lookup lane. |
| `identifier_types` | list<string> | Identifier classes paired with `exact_identifiers`. |

### Source authority and citation

| Field | Type | Role |
| --- | --- | --- |
| `source_family` | string | Coarse family such as portal docs, support KB, xpress/competitive, internal enablement, chat, Helm, advisory, legacy import. |
| `source_type` | string | More specific type such as support KB, official documentation, API spec, competitive enablement, field discussion, or Helm chart. |
| `source_authority` | string | Authority class used by ranking and answer caution logic. |
| `source_authority_score` | double | Bounded numeric authority signal; it should help ranking, not override relevance. |
| `canonical_url` | string | Canonical public/support URL when available. |
| `download_json_url` | string | Portal JSON/source URL for rebuild traceability when public-safe. |
| `root_pdf_url` | string | PDF source URL when the source was a PDF. |
| `citation_label` | string | Human-readable citation label. |
| `root_document_title` | string | Source document title. |
| `page_title` | string | Page-level title. |
| `section_title` | string | Section title. |
| `breadcrumb` | list<string> | Source hierarchy for context and citation. |
| `toc_level` | int64 | Table-of-contents depth. |
| `toc_order` | int64 | Table-of-contents order. |

### Product, version, and document metadata

| Field | Type | Role |
| --- | --- | --- |
| `software_type` | string | Product/software family normalization. |
| `software_version` | string | Source version string. |
| `software_version_normalized` | string | Search/filter-friendly version normalization. |
| `product_family` | string | Product-family grouping. |
| `topic` | string | Topic classification. |
| `document_type` | string | Document type/category. |
| `release_tag` | string | Release tag when provided by the source system. |
| `file_key_path` | string | Source file/page path key. |
| `published_date` | string | Publication date if available. |
| `modified_date` | string | Modified date if available. |
| `doc_status` | string | Active/deprecated/stale status marker. |
| `is_deprecated` | bool | Deprecated-source flag. |
| `publication_status` | string | Publication-state normalization used by source-freshness policy. |
| `ingestion_state` | string | Ingestion lifecycle state for staged, promoted, or review-required rows. |
| `freshness_status` | string | Normalized freshness posture used by stale-source policy and audits. |
| `review_status` | string | Human or automated review state for the row. |
| `last_verified_at` | string | Last verification timestamp when available. |
| `verification_method` | string | How source validity or metadata was verified. |

### Access and policy

| Field | Type | Role |
| --- | --- | --- |
| `access_scope` | string | Retrieval access class such as public, partner, internal, or support-portal. |
| `effective_access_class` | string | Normalized access class after policy reconciliation. |
| `confidentiality` | string | Confidentiality class used by policy canaries. |
| `partner_allowed` | bool | Whether partner-facing retrieval may use the row. |
| `nx_shield_allowed` | bool | Whether the NX-Shield profile may use the row. |
| `sam_allowed` | bool | Whether the internal/Sam profile may use the row. |
| `tenant_policy_tags` | list<string> | Reserved policy tags for tenant/profile-specific filtering. |
| `policy_conflict_flags` | list<string> | Conflicting or incomplete policy signals that require conservative handling or review. |

### Compatibility columns

| Field | Type | Role |
| --- | --- | --- |
| `tenant_policy_tags_legacy_null` | list<null> | Compatibility column retained for rows migrated before typed policy tags were introduced. |
| `quality_flags_legacy_null` | list<null> | Compatibility column retained for rows migrated before typed quality flags were introduced. |

### Text and embedding payload

| Field | Type | Role |
| --- | --- | --- |
| `text` | string | Display/evidence text returned to the answer path. |
| `search_text` | string | Lexical-search optimized text. |
| `text_markdown` | string | Markdown-preserved source text when available. |
| `vector` | fixed_size_list<float>[1024] | Embedding vector for semantic retrieval. |
| `token_count` | int64 | Approximate chunk token count. |
| `char_start` | int64 | Character start offset in source unit. |
| `char_end` | int64 | Character end offset in source unit. |

### Chunk neighborhood and semantic tags

| Field | Type | Role |
| --- | --- | --- |
| `parent_section_hash` | string | Parent section identity for context expansion. |
| `prev_chunk_hash` | string | Previous chunk pointer. |
| `next_chunk_hash` | string | Next chunk pointer. |
| `primary_product` | string | Primary product/entity for the row. |
| `mentioned_products` | list<string> | Other products mentioned. |
| `normalized_versions` | list<string> | Normalized version mentions. |
| `version_mentions_raw` | list<string> | Raw version strings seen in source text. |
| `features` | list<string> | Feature/topic mentions. |
| `kb_ids` | list<string> | KB identifiers referenced by the row. |
| `api_names` | list<string> | API names/endpoints where applicable. |
| `hardware_models` | list<string> | Hardware model mentions. |
| `content_types` | list<string> | Content classifications such as troubleshooting, architecture, API reference, competitive intelligence, or release notes. |
| `quality_flags` | list<string> | Reserved extraction/quality flags. |
| `extraction_warnings` | list<string> | Non-fatal extraction warnings. |

### Ingestion and lineage

| Field | Type | Role |
| --- | --- | --- |
| `ingested_at` | string | Ingestion timestamp. |
| `updated_at` | string | Last row update timestamp. |
| `parser_name` | string | Parser/extractor name. |
| `parser_version` | string | Parser/extractor version. |
| `entities_json` | string | Serialized entity extraction output used for graph backfill or audit. |
| `legacy_v3_chunk_hash` | string | Original v3 chunk hash for migrated rows. |
| `legacy_rel_path` | string | Original relative path for migrated rows. |
| `legacy_v3_source` | string | Original v3 source identifier. |
| `migration_source` | string | Lineage bucket such as native v4, Portal refresh, KB refresh, or transformed v3 import. |

## Current lineage buckets

The active design uses lineage buckets rather than hiding source generation inside opaque paths. Public-safe examples include:

- `v3_import` — transformed legacy rows retained with lineage.
- `v4_native` — native v4 rows.
- `native_v4_portal_json` — Portal JSON documentation ingestion.
- `phase_e_portal_json_stage` — staged Portal refresh rows promoted into the unified table after canary gates.
- `native_v4_portal_kb_refresh` — refreshed Portal support KB rows.
- `native_v4_artifacthub_helm_refresh` — Helm/chart metadata refresh rows.
- `native_v4_field_advisory_pdf` — field advisory PDF extraction rows.
- `v4_native_nutanix_bible_scoped_refresh` — targeted Nutanix Bible evidence with explicit source lineage.
- `v4_native_nutanix_bible_expanded_stage` — broader Nutanix Bible coverage promoted after retrieval, identity, and provenance gates.

These names are operational lineage labels, not public API guarantees.

## Ranking and policy notes

The schema supports several current ranking behaviors:

- Official Portal refresh rows can receive bounded metadata boosts when the query overlaps the document/page identity.
- Exact KB-only queries are treated as identity lookups; matching KB rows should outrank unrelated semantic neighbors.
- Explicit comparison queries can add a scoped competitive-collateral channel while preserving official product evidence.
- Stale support KB handling is retrieval-time policy, not destructive deletion: stale rows can be suppressed, demoted, or preserved with warning metadata for exact KB lookups.
- Explicit Nutanix Bible requests can promote Bible evidence when it satisfies the user’s source intent.
- Operational procedures still prefer current Portal/KB evidence over architectural background; Bible evidence adds depth without displacing current operational authority.
- Exact-ID lanes bypass broad source-precedence promotion, and any post-ranking promotion should remain visible in provenance metadata.
- Access policy is enforced before final evidence is handed to the profile/agent; it is not only a final-answer filter.

## Schema evolution rule

Change the schema by side-by-side rebuild and promotion, not by in-place mutation:

1. Build a staging table or new unified table.
2. Preserve lineage fields for old rows.
3. Create vector, FTS, and scalar indexes.
4. Run staged retrieval review and answer-path canaries.
5. Merge/promote additively with a rollback manifest.
6. Keep older stores until soak and explicit cleanup approval.
