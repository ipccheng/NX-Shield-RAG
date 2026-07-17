# Enterprise RAG Strengths

NX-Shield RAG includes the familiar agentic-RAG ideas — planning, source routing, graph context, fallback search, and evidence review — but its main value is the production control plane around retrieval. This page highlights the design strengths that are easy to miss if the system is compared only with generic agentic-RAG tutorials.

## What makes the design distinctive

### 1. Evidence-bound answers, not just better retrieval

The system treats retrieval output as an evidence packet with obligations, confidence, and missing-claim notes. The final answer is expected to satisfy the packet, not freely synthesize from plausible context.

This reduces the common enterprise failure mode where a model retrieves adjacent snippets and then writes a confident but unsupported answer.

### 2. Source authority is part of ranking

Not every source deserves equal influence. The design separates source families such as official documentation, KBs, security advisories, validated designs, competitive collateral, field notes, and public web results.

Ranking can then prefer the right authority for the question class:

- exact KB or advisory queries prefer exact official identifiers,
- operational procedures prefer official docs and KBs,
- competitive questions need balanced evidence for each side,
- field notes remain useful but lower authority than curated documentation.

### 3. Access policy is retrieval logic

Public, partner, and internal evidence cannot be filtered only after answer generation. The retrieval layer carries access and identity metadata so candidate generation, scalar filters, fallback behavior, and answer obligations can respect the agent profile before evidence reaches the writer.

This is essential for a shared MCP service used by multiple agents or personas.

### 4. Deterministic tools outrank prose for numeric questions

For sizing, usable-capacity, and repeatable arithmetic, calculators run before answer synthesis. RAG provides terminology, assumptions, caveats, and source context, but the numeric result should come from deterministic logic.

This prevents the model from inferring capacity math from similar-looking examples.

### 5. Hybrid search is intentionally redundant

The pipeline combines vector search, full-text search, exact lookup, scalar filters, and graph context because each channel fails differently.

Examples:

- vector search catches paraphrases,
- full-text search catches KB IDs, CVEs, part numbers, error strings, and command names,
- exact lookup protects identity-style queries from semantic drift,
- scalar filters enforce product, source, and access boundaries,
- graph context adds relationship awareness without becoming the source of truth.

The redundancy is deliberate: it makes misses easier to detect and recover from.

### 6. Graph context is advisory and auditable

Ladybug graph context is used as structural signal. It can explain why chunks are related, suggest nearby source families, and support graph-expanded retrieval, but it does not make a claim true by itself.

The key discipline is:

> graph proximity can improve recall; answer sufficiency still requires source-backed evidence.

This avoids a common Graph RAG trap: treating an entity edge as proof that a retrieved chunk answers the question.

### 7. Weak evidence is a first-class result

For high-risk classes such as competitive comparisons, security issues, or version-specific claims, the system should mark weak or missing evidence explicitly. A useful answer may be:

- strong for the Nutanix side,
- partial for a competitor side,
- missing for a version-specific claim,
- or blocked until a stronger source is available.

The goal is not to answer every question confidently; it is to avoid hiding uncertainty.

### 8. Query-class obligations drive answer shape

Different questions require different proof standards.

Examples:

- A CVE/security-advisory answer needs advisory ID, CVE, affected product, fix/workaround status, and freshness.
- A hardware answer needs exact model/part/source evidence.
- A sizing answer needs calculator assumptions and supporting source context.
- A comparison answer needs evidence for every compared side.
- A procedure answer needs step evidence and risk/caveat coverage.

This makes answer quality inspectable before prose is generated.

### 9. Rollout discipline is built into the design

Graph improvements and ranking changes should be evaluated before cutover. The design favors:

- report-only diagnostics,
- shadow comparisons,
- canary query suites,
- expected-answer scoring,
- latency tracking,
- and explicit enablement gates.

This matters because a retrieval change can make one query better while quietly regressing another.

### 10. Corpus hygiene is an operating concern

The system treats ingestion and graph sync as ongoing operations, not one-time setup. Useful checks include:

- LanceDB-to-graph parity,
- stale or superseded source classification,
- orphan graph chunks,
- duplicate chunk identities,
- source-family coverage gaps,
- and additive backfill checkpoints.

These controls keep graph and vector stores from drifting apart as new Portal docs, KBs, advisories, and internal sources arrive.

### 11. Endpoint locality is verified

In MCP-based systems, it is possible to patch the right code but call the wrong service. NX-Shield RAG treats endpoint locality as part of correctness: the active agent tool, MCP endpoint, tunnel, LaunchAgent, and backend script must be verified before claiming that a runtime change is live.

### 12. Rebuildability and public/private separation are design goals

The public repo documents architecture, templates, and operational patterns. The private repo and local runtime hold source scripts, data stores, credentials, and environment-specific paths.

This separation keeps the design reusable while avoiding accidental disclosure of private data or volatile runtime state.

## Comparison with generic agentic RAG

Generic agentic-RAG descriptions usually emphasize how an agent can decompose a query, call tools, retrieve iteratively, and use graph or memory. NX-Shield RAG adds the enterprise controls needed to make that safe in technical support and presales contexts:

- authority-aware ranking,
- identity-aware retrieval,
- evidence ledgers,
- calculator-first answer paths,
- graph-as-signal discipline,
- weak-evidence disclosure,
- report-only rollout gates,
- and corpus hygiene/backfill operations.

In short:

> Generic agentic RAG asks, “Can the agent find more context?” NX-Shield RAG asks, “Can the agent prove the answer is safe to say?”

## Design checklist

Use this checklist when adapting the pattern:

- [ ] Does every answerable claim map to retrieved evidence or a deterministic tool result?
- [ ] Are source families ranked by authority for the query class?
- [ ] Are public, partner, and internal access boundaries enforced before answer generation?
- [ ] Do exact IDs, CVEs, KBs, commands, and part numbers have lexical/exact retrieval paths?
- [ ] Are graph matches treated as supporting signal rather than proof?
- [ ] Does the system disclose weak or missing evidence instead of filling gaps?
- [ ] Are sizing/math answers computed by tools before the language model writes?
- [ ] Are retrieval changes evaluated with canaries before rollout?
- [ ] Can graph/vector store drift be audited and repaired additively?
- [ ] Can operators verify which MCP endpoint and backend implementation are actually active?
