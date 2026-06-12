# RAG Improvements Release Note

This note summarizes the current public design improvements in NX-Shield RAG. It is intentionally implementation-neutral: it avoids live hostnames, private paths, row counts, credentials, internal tickets, and operational secrets.

## Executive summary

NX-Shield RAG has moved from a basic document-search pattern toward a production-controlled evidence system:

```text
vector search demo
→ hybrid evidence retrieval
→ identity-aware, verifier-controlled, graph-assisted RAG platform
```

The design goal is not just to retrieve relevant snippets. The goal is to produce answers that are source-grounded, access-policy aware, measurable, and safe to operate across multiple agent profiles.

## What improved

### 1. Retrieval is more robust and deterministic

The query path is designed around multiple complementary retrieval channels instead of a single vector lookup:

- hybrid vector + full-text retrieval,
- exact and deterministic lookup lanes,
- metadata and access-policy filters,
- source-authority ranking,
- bounded graph signal,
- calculator-first paths for sizing and arithmetic questions.

This improves exact-ID, compatibility, security advisory, KB, Field Advisory, and supportability queries where vector-only retrieval can miss important source identity signals.

### 2. Gateway query hygiene is stronger

The current design separates the current user question from wrapped conversation context before retrieval. This reduces failures where previous-answer text or gateway wrapper text pollutes the actual search query.

The design also supports normalization for common typo, alias, and intent patterns, such as product acronyms, version formatting, and Prism Central compatibility language.

### 3. Comparison queries are handled more deliberately

Comparison questions use bounded deterministic planning rather than a default always-on query-time planner. The design can decompose explicit comparison prompts into side-specific retrieval obligations and make weak evidence visible when one side has thinner coverage.

This improves competitor and product comparisons by reducing one-sided answers and making coverage gaps explicit instead of allowing the answer model to fill gaps from prior knowledge.

### 4. Source authority is part of retrieval logic

The system treats source authority as a retrieval and ranking concern, not just an answer-formatting concern.

The intended ranking posture is:

- prefer official Nutanix Portal, KB, release note, Field Advisory, and product documentation evidence for operational claims,
- use developer and GitHub-style sources primarily for API, automation, IaC, and implementation questions,
- treat community, web, and lower-authority sources as fallback or supporting context unless the query class explicitly calls for them.

This reduces the risk of lower-authority snippets outranking official sources for operational answers.

### 5. Ladybug is the primary active graph DB

The active graph posture has been updated:

- **Ladybug** is shown as the primary graph DB on the active query path.
- **Kuzu** is treated as a legacy read-only/archive path during retirement.
- Graph output remains a bounded ranking and explanation signal, not a source of truth by itself.

This makes graph migration safer: the graph can help retrieval ranking and explain related concepts, but answer claims still require source-backed evidence.

### 6. Answer verification is a first-class control layer

The design includes an answer-verification posture with outcomes such as:

- `PASS`,
- `PASS_WITH_WARNINGS`,
- `REWRITE_REQUIRED`,
- `FAIL_CLOSED`.

The verifier is intended to catch unsupported claims, over-strong absolutes, missing weak-evidence disclosures, and cases where the answer deflects even though actionable evidence exists.

### 7. Provider failures fail closed

Embedding and reranking services are treated as dependencies that can fail independently from corpus quality.

The design now calls out provider response hardening:

- validate response shape,
- validate vector contents,
- retry boundedly where appropriate,
- fail closed with a clear dependency error instead of misclassifying the issue as a retrieval or data-corruption problem.

### 8. Evaluation and canaries guide promotion

Promotion decisions should be backed by report-only evaluations and canaries instead of intuition or one-off examples.

Useful tracked dimensions include:

- Hit@5 / Recall@5,
- MRR,
- citation authority,
- stale-source avoidance,
- comparison side coverage,
- fallback rate,
- latency,
- verifier pass/rewrite/fail outcomes,
- identity-boundary behavior.

Graph ranking, verifier enforcement, and broad corpus changes should move through shadow, canary, guarded-live, and rollback-aware stages.

### 9. Identity and access boundaries are explicit

The design supports multiple agent identities and access policies, including internal, customer-visible, partner-facing, and profile-specific retrieval boundaries.

Access policy is treated as retrieval logic. Public, partner, and internal corpora must not be separated only at final answer generation time.

### 10. Operational reliability is part of the architecture

The design distinguishes among several failure layers:

- RAG service health,
- MCP client/session health,
- gateway wrapper behavior,
- LanceDB retrieval behavior,
- graph backend behavior,
- provider dependency behavior,
- answer-verifier behavior.

This reduces unnecessary store mutation, re-ingestion, or service restarts when the real issue is a stale client, malformed provider response, query wrapper problem, or identity-boundary mismatch.

## Updated public diagram

The public query-path diagram has been refreshed to reflect the current posture:

- Ladybug primary graph DB,
- Kuzu legacy archive / retiring,
- LanceDB hybrid retrieval as the evidence source of truth,
- graph as bounded ranking signal,
- current-question-focused MCP bridge,
- embedding response hardening,
- answer-verifier rewrite/fail-closed loop,
- external fallback only after local evidence gaps.

See: [`diagrams/sample-query-path-vcf-aos.png`](../../diagrams/sample-query-path-vcf-aos.png)

## Practical impact

These improvements should most help with:

- multi-document synthesis,
- product and competitor comparisons,
- CVE / security advisory / Field Advisory lookup,
- exact KB and Portal article lookup,
- source freshness and source-authority handling,
- partner-facing answers that need explicit uncertainty,
- storage or sizing answers where deterministic calculators should lead,
- graph-assisted discovery without graph-driven hallucination.

The gains are expected to be less dramatic for simple factual queries that were already answered correctly by existing local evidence.

## What remains intentionally gated

The following areas should remain gated by evaluation, rollback planning, and explicit operating decisions:

- broader graph-ranking promotion,
- final Kuzu retirement and deletion,
- active graph orphan repair,
- broad corpus pruning,
- verifier enforcement expansion,
- query-plan memory or learning from historical outcomes,
- additional intent-specific lanes for hardware, licensing, CVE, architecture, and competitive analysis.

The safe direction is to continue using report-only audits, scoped canaries, and explicit promotion gates before mutating stores or changing live answer behavior.

## Bottom line

NX-Shield RAG is no longer documented as a generic "search documents and answer" system. The current public design presents it as an evidence-control architecture:

```text
local-first hybrid retrieval
+ source authority
+ identity-aware access control
+ bounded graph signal
+ calculator-first deterministic tools
+ verifier-controlled answer delivery
+ evaluation-gated operations
```

That combination is what makes the system suitable for technical support, presales, and partner-facing use cases where unsupported claims are operationally risky.
