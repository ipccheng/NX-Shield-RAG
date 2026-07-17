# Milestone Lineage

NX-Shield RAG evolved through several design lessons. This page keeps the public lessons without exposing private operational detail.

## Key lessons

### Retrieval architecture improved, but answer quality needed its own layer

Early work focused on search channels, routing, and reranking. Later work showed that good retrieval can still produce wrong answers unless the final synthesis is constrained by an Evidence Ledger and checked by answer-verifier gates.

### Graph boost is useful but insufficient

Ladybug graph context improves structural recall and explanation. It does not replace source evidence. The graph is treated as advisory context.

The safe rollout pattern is graph-shadow first: compare baseline evidence with graph-assisted candidates in reports before changing served ranking or answer generation.

### Unified corpus beats parallel legacy stores

A single active search path with explicit lineage metadata is easier to operate than multiple hidden fallbacks. Old stores should remain rollback archives until soak completes.

### Calculator-first changed sizing reliability

Storage sizing and similar math questions should use deterministic calculators first. RAG provides definitions, assumptions, and caveats.

A later evaluation milestone made this testable by injecting calculator output as report-only evidence for verifier scoring. This proves that math answers are tool-supported without mutating the corpus or graph.

### Answer verification became a separate gate

A dedicated verifier layer checks whether the drafted answer is supported by retrieved evidence and tool outputs. Its implementation-level verdicts are:

- `PASS` — supported enough to answer normally,
- `PASS_WITH_WARNINGS` — answerable, but with caveats or weak areas,
- `REWRITE_REQUIRED` — useful retrieval exists, but the answer should be revised before delivery,
- `FAIL_CLOSED` — policy, access, or evidence failure should block a normal answer.

This separates "retrieval found something" from "the user-facing answer is safe to send."

The delivery hook also needs its own runtime proof. A good answer and a passing retrieval trace are not enough to prove enforcement. The gateway should emit an auditable verifier report and delivery decision for the same user turn before the system is considered live-enforcement ready.

Two implementation lessons matter for MCP-based agent gateways:

- verify both the service-side tool name and the gateway-registered MCP tool name, because clients may prefix tool names when registering MCP servers;
- test the actual gateway message shape, not only ideal assistant/tool fixtures, because tool-call metadata may be serialized or exposed through different fields at runtime.

### Report-only eval harness became the change gate

New retrieval, graph, calculator, and verifier behavior should pass a report-only eval harness before serving behavior changes.

The harness pattern is:

- frozen case corpus for regression checks,
- local-corpus retrieval with external fallbacks disabled when isolating RAG quality,
- sanitized evidence metadata by default,
- expected source-family and exact-ID gates,
- answer-verifier verdict expectations,
- optional calculator evidence for sizing/math,
- graph-shadow columns for future graph candidate fusion.

This gives a safe promote path: report-only → shadow/warn → enforce, with human review between phases.

### Competitive answers require source-balance checks

For comparison questions, especially competitive AI or platform comparisons, one-sided evidence should not be treated as a complete answer. The eval harness should require evidence for both sides where possible and disclose weak or missing competitor evidence.

### Profile endpoints require direct verification

A profile can discover a tool while its backing service still points to an old script/config. Direct MCP canaries per endpoint are mandatory.

Profile-scoped gateways also need explicit environment/path checks for verifier imports. If a gateway resolves its home directory to a profile-specific root, shared RAG verifier modules should be located through a configured RAG root rather than by assuming the profile directory contains the RAG source tree.

### Architecture questions require composed-design evidence

For architecture/supportability questions, do not compose a supported design from separately true facts. For example, support for a scale-out management plane, a witness pattern, and multi-site operations are separate facts; the final architecture is supportable only if direct evidence supports that composed design. Retrieval should use multiple evidence lanes and the verifier should reject unsupported composition.

### Public docs should avoid dynamic operational facts

Live row counts, private hostnames, internal paths, temporary benchmark numbers, and raw eval outputs go stale quickly and can leak context. Public docs should focus on stable design.
