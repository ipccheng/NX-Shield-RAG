# Design Controls and Validation Gates

[Documentation index](../README.md) · [Project home](../../README.md)

This page maps proposed retrieval and operating controls to their validation gates. It is **not a software release note, deployment attestation, or benchmark report**. No public RAG application implementation or reproducible performance result accompanies these claims.

NX-Shield RAG is an independent project, not a Nutanix-approved implementation. Deployment owners must separately validate technical behavior, source rights, provider data flows, organizational approval, and any product support or licensing claims.

## Terms used here

**RAG (retrieval-augmented generation)** gives a language model retrieved sources before it drafts an answer. An **embedding** represents text numerically for similarity search. **Reranking** reorders candidate passages for relevance. A **verifier** compares draft claims with available evidence; it is not a guarantee of truth. **MCP (Model Context Protocol)** connects agents and tools. **Shadow** runs a proposed change without altering delivery; a **canary** is a representative regression test. **Promotion** moves a validated candidate into serving, and **rollback** restores the prior compatible state.

## Controls and the failure modes they target

| Design area | Proposed behavior | What must be tested |
| --- | --- | --- |
| Hybrid retrieval | Combine vector search, full-text search, exact identifiers, metadata filters, and bounded graph hints | Exact identifiers and version-sensitive evidence remain visible; extra channels do not bypass authorization |
| Query hygiene | Separate the current question from previous answers and wrapper text; use search-only aliases | Clean and context-wrapped queries preserve intent; explicit identifiers are not silently corrected |
| Comparison routing | Construct a bounded set of side-specific routes rather than requiring a model planner for every query | Both sides receive evidence coverage; missing competitor evidence is disclosed |
| Source authority | Prefer current, applicable official sources for operational claims; use implementation sources for implementation questions | Bounded ranking boosts do not displace more relevant or exact evidence |
| Explicit source requests | Surface requested Nutanix Bible evidence without replacing current operational authority | Exact-ID lanes bypass broad source promotion; ordering changes retain provenance |
| Graph context | Use Ladybug as the reference relationship component, linked to evidence in the searchable corpus | Graph relationships remain hints, not independent proof; backend and ranking changes have separate gates |
| Answer verification | Use `PASS`, `PASS_WITH_WARNINGS`, `REWRITE_REQUIRED`, or `FAIL_CLOSED` to control draft delivery | Unsupported claims, overstatements, and missing caveats are caught without excessive rejection of valid answers |
| Model dependencies | Validate response structure, finite vector values, model/dimension compatibility, and bounded retries | Dependency failures are reported as dependency failures, not confused with missing corpus evidence |
| Identity boundaries | Bind each caller to explicit source permissions across retrieval, graph expansion, fallbacks, and delivery | Unknown identities fail closed; an internal entitlement never leaks into a public profile |
| Operational diagnosis | Separate service, client/session, gateway, store, graph, model, and verifier failures | A stale client or malformed model response does not trigger unnecessary re-ingestion or store mutation |
| Corpus lifecycle | Capture source identity, hierarchy, artifacts, extraction quality, and provenance before candidate promotion | New-content retrieval and old-query preservation pass; source/vector/graph state and rollback artifacts are consistent |
| Hardware sizing | Separate inventory, computed resource totals, vendor specifications, and design validation | Raw is not mistaken for usable capacity; calculated capacity is not treated as an orderable or supported configuration |

These controls are intended to address failure modes, not establish measured improvement. See the [retrieval pipeline](../design/retrieval-pipeline.md), [evidence ledger](../design/evidence-ledger.md), and [ingestion model](../build/ingestion-and-corpus.md) for details.

## Evaluation evidence required before claiming improvement

Record the baseline and candidate revisions, compatible schemas/models, frozen test set, identities, fallback settings, and measurement boundary. Compare at least:

- **Hit@5:** the fraction of queries with at least one labeled relevant result among the first five.
- **Recall@5:** the fraction of labeled relevant items found among the first five, with a documented aggregation method.
- **MRR (mean reciprocal rank):** a summary of how early the first relevant result appears.
- Source authority, freshness, exact-identifier preservation, and comparison-side coverage.
- Unauthorized-evidence findings, including duplicate-policy conflicts and fallback paths.
- Verifier accept/rewrite/block results, false positives, and missed unsupported claims.
- Local retrieval and end-to-end latency separately, including model calls and fallbacks when enabled.

Metrics are only as reliable as the labeled cases and measurement setup. A small smoke test does not establish production accuracy, a service-level objective, or safety for a new user population. Follow the [evaluation strategy](evaluation-strategy.md).

## Gated rollout, not implied deployment status

1. Run report-only diagnostics on a frozen candidate.
2. Compare shadow results with the baseline, including source review of each first-result change.
3. Permit guarded influence only with bounded ranking changes, identity checks, and delivery enforcement appropriate to the evaluated scope.
4. Promote only the exact tested source/configuration/store set, with a compatible rollback set.
5. Verify fresh direct and application-level requests after cutover; roll back if a required gate fails.

Keep graph ranking, graph repair, corpus pruning, verifier enforcement expansion, historical-query learning, and new intent-specific lanes separately gated. Success in one area does not authorize another.

For multi-host deployments, compare logical store content and policy, not raw file hashes alone. Incremental index preservation can limit unrelated ranking changes, but still needs new-content and preservation tests. See [operations](../operate/operations-playbook.md).

## Diagram and next reading

The [query-path illustration](../../diagrams/rag-query-path.png) is a conceptual aid, not proof of active components or verified behavior. Use [architecture](../design/architecture.md) for component responsibilities and [governance](../design/ai-governance-alignment.md) for approval boundaries.
