# Evaluation Strategy

A RAG system should be evaluated at three levels:

1. retrieval quality,
2. evidence packet quality,
3. final answer quality.

Top-k retrieval alone is not enough. Evaluation should prove that the system can retrieve the right evidence, expose weak coverage, and prevent unsupported final answers.

## Retrieval checks

Measure whether the right evidence appears:

- expected source family appears,
- exact identifiers match,
- product/version metadata filters work,
- source diversity is reasonable,
- weak side of comparison is detected,
- official or high-authority evidence is not outranked by low-authority convenience matches.

For competitive or comparison questions, retrieval should be scored for both sides of the comparison. A one-sided answer with strong Nutanix evidence but weak competitor evidence should be treated as weak or review-required, not as a complete comparison.

## Evidence-ledger checks

Measure whether the evidence packet is honest:

- supported claims are actually supported,
- missing obligations are listed,
- verdict matches evidence strength,
- answer rules are present for risky classes,
- calculator output is included for sizing/math,
- restricted evidence is excluded for public or partner identities.

A good evidence packet should make the final answer posture obvious before the model writes prose.

## Final answer checks

Measure the answer the user actually sees:

- uses RAG first for domain questions,
- cites or names source families appropriately,
- does not overstate weak evidence,
- does not mix public and internal evidence under restricted identities,
- gives deterministic numbers only from tools or explicitly stated assumptions,
- rewrites or fails closed when evidence does not support the requested answer.

## Report-only harness pattern

Before enabling a new ranking, graph, verifier, or calculator behavior in serving, run it through a report-only harness.

A useful report-only harness should:

- disable web and chat fallbacks when testing local corpus quality,
- run a frozen corpus of human-meaningful cases,
- record sanitized evidence metadata rather than raw private chunks by default,
- compare retrieved evidence against expected source families and exact identifiers,
- run answer-verifier checks without changing delivery behavior,
- prove runtime verifier hooks by checking for a same-turn shadow report and delivery decision,
- support deterministic calculator/tool evidence as in-memory evidence for math or sizing cases,
- emit shadow columns for experimental graph or reranking paths before changing production ranking.

The default pass condition is not simply "got an answer." It is:

```text
retrieval evidence is present + expected source gates pass + verifier verdict is acceptable + runtime delivery decision is auditable
```

Expected verifier verdicts should usually be `PASS` or `PASS_WITH_WARNINGS`. Cases expected to require caution, such as restricted-source questions, one-sided competitive evidence, or missing exact KB evidence, should be explicitly marked as expected review/rewrite cases so unexpected regressions stand out.

## Verifier enforcement progression

A safe verifier rollout separates three states:

1. **shadow/report-only** — write a verifier report and delivery decision, but leave the answer unchanged;
2. **fallback-only enforcement** — if the answer cannot be verified, send a conservative evidence-bound fallback instead of the draft;
3. **regenerate-once enforcement** — for `REWRITE_REQUIRED`, run exactly one bounded revision using only retrieved evidence and verifier feedback, reverify the revised answer, then send the revised answer only if it passes; otherwise fail closed to the evidence fallback.

Regeneration should be explicitly config-gated, audited with both draft and revised verifier reports, and protected from retry loops or unbounded second model calls.

## Regression suite design

Keep a small suite of human-meaningful canaries:

- networking production-impacting procedure,
- hardware compatibility / replacement,
- storage sizing,
- product comparison,
- exact KB/article lookup,
- graph-adjacent concept query,
- intentionally weak evidence query,
- disallowed internal-source query,
- partner/public access-boundary query,
- graph-shadow query where graph context should help but not become truth,
- architecture-supportability query where separately true facts must not be composed into an unsupported design.

The private source repo can keep concrete corpus files, local run IDs, and raw evidence. Public docs should describe the case classes and evaluation gates.

## Architecture-supportability checks

Architecture questions need more than ordinary semantic top-k evidence. The evaluation set should include composed-design cases where a plausible answer could incorrectly combine individually true statements into an unsupported architecture.

Useful architecture-supportability lanes include:

- **unsupported composition lane** — reject designs that stretch a management-plane quorum, appliance, or HA group across failure domains unless official evidence supports that exact composed design;
- **global-management lane** — require direct evidence for global or fleet-level management, rather than inferring it from a local management-plane HA guide;
- **failure-domain lane** — distinguish site/failure-domain survivability from node or VM-level HA inside one supported domain;
- **fallback lane** — allow backup/restore or DR runbooks as weaker recovery evidence, but do not treat them as equivalent to an active-active or stretched-quorum architecture.

For example, a customer can reasonably ask for one management experience across two sites plus a witness, but the answer must not infer that a three-VM management plane can be placed one VM per site/witness just because scale-out HA, anti-affinity, Metro/witness, and backup/restore are each documented elsewhere.

Expected behavior for this class:

```text
direct official evidence for the composed architecture -> answer may recommend it
partial adjacent evidence only -> answer must caveat or propose safer alternatives
contradicting or constraining evidence -> answer must rewrite or fail closed
```

These checks should stay in the eval/verifier framework so improvements generalize beyond one named customer design or one product acronym.

## Calculator/tool evidence checks

For storage sizing and other deterministic math, RAG should not synthesize numeric answers from prose alone.

The safer pattern is:

1. classify the query as sizing/math intent,
2. run a deterministic calculator or tool with explicit assumptions,
3. attach the tool result as evidence,
4. let RAG provide definitions, caveats, and source-backed assumptions,
5. verify that the final answer uses the tool output rather than inventing numbers.

Calculator evidence can be tested in report-only mode by appending an in-memory evidence row to the verifier input. This proves answer quality without writing to the vector store, graph store, or serving path.

## Graph-shadow checks

Graph context should be evaluated as a candidate generator or reranking signal before it changes served answers.

A graph-shadow report should compare:

- baseline top evidence keys,
- graph-assisted top evidence keys,
- whether top-1 changed,
- top-5 overlap,
- latency impact,
- whether exact-ID and source-authority gates still pass.

Graph improvements should be promoted only if they improve recall or explanation without weakening source authority, access policy, exact-ID behavior, or latency budgets. A passing aggregate graph-shadow gate is not sufficient by itself: every top-1 change should be classified as beneficial, neutral, risky, or bad, and no-entity cases should be treated as query/entity coverage review rather than automatic graph-store mutation.

## Verifier utility guardrails

Verifier enforcement should optimize for safety first, then utility. For architecture-supportability cases, the safety-critical gate is that unsupported composed designs are rejected or fail closed. A separate utility gate should measure whether safe negated or cautionary wording is incorrectly treated as an unsupported positive claim.

Useful verdict posture:

```text
unsafe positive composition -> FAIL_CLOSED or evidence fallback
safe caution / "do not present as supported" -> PASS_WITH_WARNINGS or supported rewrite
insufficient direct evidence -> conservative fallback with weak-evidence disclosure
```

This prevents a false sense of readiness: a verifier can be safe enough for guarded serving while still needing utility refinements to reduce unnecessary fallbacks.

## Guarded graph/live checks

Graph ranking can move through a guarded-live state only when source review shows neutral or beneficial top-1 changes. Neutral reorderings should stay inside authoritative source families, preserve exact-ID hits, and avoid moving from official sources to community or third-party sources.

Promotion should remain reversible through config, not data mutation. If the graph layer is disabled, the vector/lexical/exact retrieval path should still produce evidence-bound answers.

## Milestone reports

The private source repo stores historical K-series, canary, and eval-harness reports. Public docs should summarize patterns, not expose local-only operational data.

Public principle:

> Report design lessons and evaluation categories publicly. Keep raw private paths, private query logs, row counts, hostnames, and sensitive operational details out of public docs.
