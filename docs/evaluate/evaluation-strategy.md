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
- graph-shadow query where graph context should help but not become truth.

The private source repo can keep concrete corpus files, local run IDs, and raw evidence. Public docs should describe the case classes and evaluation gates.

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

Graph improvements should be promoted only if they improve recall or explanation without weakening source authority, access policy, exact-ID behavior, or latency budgets.

## Milestone reports

The private source repo stores historical K-series, canary, and eval-harness reports. Public docs should summarize patterns, not expose local-only operational data.

Public principle:

> Report design lessons and evaluation categories publicly. Keep raw private paths, private query logs, row counts, hostnames, and sensitive operational details out of public docs.
