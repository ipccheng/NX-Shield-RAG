# Enterprise RAG Design Controls

[Documentation index](../README.md) · [Project home](../../README.md)

> **Scope:** Independent project design guidance, not a Nutanix-approved implementation. This page does not establish deployed behavior, measured effectiveness, or vendor support. The public repository does not include a runnable service.

## Reading this page

**Agentic RAG** lets an application plan retrieval and call tools rather than perform only one search. **RAG (retrieval-augmented generation)** supplies source material to a language model. **MCP (Model Context Protocol)** connects agents to tools. A **control plane** is the policy and operating logic around those calls; it is not proof of security or answer correctness. **KB** means knowledge-base article; **CVE** is a public vulnerability identifier.

NX-Shield RAG includes the familiar agentic-RAG ideas — planning, source routing, graph context, fallback search, and evidence review — but this page focuses on the proposed policy and operating controls around retrieval. These are design choices to evaluate, not demonstrated advantages over other systems.

## What makes the design distinctive

### 1. Evidence-bound answers, not just better retrieval

The system treats retrieval output as an evidence packet with obligations, confidence, and missing-claim notes. The final answer is expected to satisfy the packet, not freely synthesize from plausible context.

This is intended to reduce the common failure mode where a model retrieves adjacent snippets and then writes a confident but unsupported answer.

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

This reduces reliance on the model inferring capacity math from similar-looking examples.

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

These checks are intended to detect drift between graph and vector stores as new authorized sources arrive; repair still requires scoped validation.

### 11. Endpoint locality must be verified

In MCP-based systems, it is possible to patch the right code but call the wrong service. NX-Shield RAG treats endpoint locality as part of correctness: the active agent tool, MCP endpoint, tunnel, LaunchAgent, and backend script must be verified before claiming that a runtime change is live.

### 12. Rebuildability and public/private separation are design goals

The public repo documents architecture, templates, and operational patterns. Private source control holds implementation scripts and sanitized configuration. Data stores and their backups stay outside Git; credentials come from an approved secret store and must not be committed to either repository.

This separation keeps the design reusable while avoiding accidental disclosure of private data or volatile runtime state.

## What this notebook emphasizes

An agent can decompose a query, call tools, and retrieve iteratively. This notebook focuses on the evidence and operating controls to evaluate before technical-support or presales use; it does not claim that other RAG designs lack these controls:

- authority-aware ranking,
- identity-aware retrieval,
- evidence ledgers,
- calculator-first answer paths,
- graph-as-signal discipline,
- weak-evidence disclosure,
- report-only rollout gates,
- and corpus hygiene/backfill operations.

In short:

> Finding more context is only one task. Also ask, “Which evidence and policy checks support delivering this answer?”

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
