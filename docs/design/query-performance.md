# Evidence-safe query performance

[Documentation index](../README.md) · [Project home](../../README.md) · [Retrieval pipeline](retrieval-pipeline.md)

Performance work should remove repeated computation, not permission checks or evidence context. These are implementation contracts and evaluation lessons—not public deployment guarantees or measured benchmark results. The application is not distributed here.

## Preserve the policy order

Hybrid retrieval combines semantic, lexical, exact-identity, and metadata routes. Use the same canonical evidence identity across fusion, duplicate reconciliation, graph origins, and final serialization.

1. Collect the policy-bearing copies for each canonical identity across the relevant snapshot, including copies outside a preferred source family.
2. Reconcile duplicates globally with the most restrictive applicable policy. Do not select an apparently public or authoritative copy first and hide a restrictive duplicate.
3. Apply caller and model-processing policy to the reconciled candidates.
4. Rank, select, and format only admitted evidence. Recheck newly appended or fallback evidence at its boundary.

Title-metadata preselection is safe only **after global restrictive duplicate reconciliation**, and only on fields proven unchanged by that reconciliation. If a field can change during a merge, filtering on its earlier value can change permissions or hide evidence. A projection must retain every field needed for the authorization decision, including source family and authority.

Preserve malformed-policy behavior as well as successful results. A keyless row-copy path and a keyed duplicate-merge path can have different validation/error boundaries. An optimization must not silently skip malformed keyed merges, convert errors into empty results, or invent a canonical key for a keyless row. A copied keyless row is not thereby authorized: apply the same downstream policy validation as the baseline. Test both paths and duplicate permutations independently.

## Cache embeddings, not authorization

An embedding cache can avoid repeated model calls for the **exact same input**. It must not cache retrieved passages, access-control decisions, evidence packets, or final answers under the guise of an embedding optimization.

- Key by exact input, the effective provider endpoint, a nonsecret credential/tenant identity binding, model/version, dimensions, and preprocessing contract. Do not silently lowercase, trim, or normalize Unicode to improve hit rate.
- Bound entries, retained bytes, lifetime, and concurrent work; measure eviction and memory retention, not just hit rate.
- Validate the response before insertion: expected response shape and cardinality; unique, complete, in-range response indexes matched to request order; expected vector dimensions; and finite numeric values. Reject missing, duplicate, or misleading indexes and nonnumeric or nonfinite elements.
- Never cache errors, partial batches, or malformed vectors. Do not let a cache hit turn a failed authorization check into success.
- Keep input text and vectors inside an approved processing and retention boundary. Embeddings are not anonymized data. Isolate cache namespaces when required by tenant or data policy.
- Invalidate on incompatible model/configuration changes; keep hit/miss telemetry free of query text and sensitive cache keys.

Every request still resolves identity, reads current policy, retrieves from its bound snapshot, and builds its own evidence packet. Cache-on and cache-off tests must agree on evidence and refusal behavior.

## Narrow fast paths need equivalence proofs

An ASCII regular-expression fast path is acceptable only for patterns **and inputs** for which equivalence to the original matcher is established. ASCII input alone is not sufficient: flags, character classes, boundaries, case folding, and escaping can alter behavior. Keep the original Unicode matcher as the fallback for every unproven case. Test non-ASCII letters, Unicode case-folding edge cases, punctuation, empty strings, escaped literals, and invalid patterns. Compare errors as well as matches.

Do not use a faster matcher to repair or normalize exact identifiers. Preserve the user's literal token and validate it before lookup.

## Bind a documentation delta to a full query snapshot

A pinned documentation delta is a controlled set of new or revised documents; it is not permission to mix arbitrary new rows into an old serving view.

- Bind the delta to a specific full base snapshot, schema, embedding model, policy version, and source lineage.
- Give one query a consistent full snapshot: base plus admitted delta, with canonical reconciliation over the complete policy domain. Query-scoped does not mean a small candidate list is a full snapshot.
- Verify the binding before use and protect it throughout reading, through an immutable view or equivalent consistency mechanism. If the base mutates or a binding cannot be established, fail closed; do not fall through to an unpinned current store.
- Keep caches derived from that snapshot separate from embedding-only reuse. Do not retain a full corpus indefinitely in a request cache to save a scan.
- Test base mutation, stale delta, incompatible schema/model/policy, overlapping canonical identities, partial reads, and concurrent replacement. A successful build is not serving promotion.

See [ingestion](../build/ingestion-and-corpus.md) for candidate construction and [operations](../operate/operations-playbook.md) for promotion and rollback.

## Measure stages separately

Record monotonic durations for request admission, snapshot binding, policy reconciliation, embedding (hit or miss), vector/lexical/exact retrieval, metadata selection, graph hints, fusion/reranking, and evidence formatting. Measure transport, queueing, retries, drafting, and verification separately from retrieval. Parallel stages can overlap: their durations need not sum to wall-clock latency.

Compare frozen baseline and candidate inputs, identities, models, policies, and snapshot versions. Separate cold and warm runs and dependency failures from no-results cases. Report memory peak and retained memory alongside latency distributions and per-class failures. Never trade a policy failure for a better aggregate latency number.

## Qualification checklist

| Change | Required negative and equivalence cases |
| --- | --- |
| Duplicate reconciliation | Public/restricted copies in either order; hidden source-family copy; missing policy fields; keyed merge and keyless copy |
| Metadata preselection | Reconciled-field changes; title match outside allowed scope; projection missing an authorization field |
| Embedding cache | Exact-input distinction; invalid response indexes; wrong dimensions; nonfinite vectors; eviction; policy change on a warm cache |
| ASCII matcher | Original Unicode fallback; flags and boundary behavior; matching and exception parity |
| Snapshot delta | Base mutation; wrong schema/model/policy; stale or partial snapshot; contradictory duplicate in delta |
| Graph optimization | Missing identity; stale/disallowed origin; incomplete evidence label; graph-disabled parity |

These are runtime test objectives. The repository's [documentation checks](../evaluate/documentation-validation.md) validate the handbook, not these application behaviors.
