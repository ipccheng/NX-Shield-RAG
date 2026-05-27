# Evaluation Strategy

A RAG system should be evaluated at three levels:

1. retrieval quality,
2. evidence packet quality,
3. final answer quality.

Top-k retrieval alone is not enough.

## Retrieval checks

Measure whether the right evidence appears:

- expected source family appears,
- exact identifiers match,
- product/version metadata filters work,
- source diversity is reasonable,
- weak side of comparison is detected.

## Evidence-ledger checks

Measure whether the evidence packet is honest:

- supported claims are actually supported,
- missing obligations are listed,
- verdict matches evidence strength,
- answer rules are present for risky classes,
- calculator output is included for sizing/math.

## Final answer checks

Measure the answer the user actually sees:

- uses RAG first for domain questions,
- cites or names source families appropriately,
- does not overstate weak evidence,
- does not mix public and internal evidence under restricted identities,
- gives deterministic numbers only from tools or explicitly stated assumptions.

## Regression suite design

Keep a small suite of human-meaningful canaries:

- networking production-impacting procedure,
- hardware compatibility / replacement,
- storage sizing,
- product comparison,
- exact KB/article lookup,
- graph-adjacent concept query,
- intentionally weak evidence query,
- disallowed internal-source query.

## Milestone reports

The private source repo stores historical K-series and canary reports. Public docs should summarize patterns, not expose local-only operational data.

Public principle:

> Report design lessons and evaluation categories publicly. Keep raw private paths, private query logs, and sensitive operational details out of public docs.
