# Retrieval Pipeline

The retrieval pipeline is designed to answer hard technical questions where the right answer may require multiple evidence families.

## Query flow

The current v4 path keeps the latency-sensitive retrieval logic deterministic where possible. Query-time LLM planning is not required for obvious exact-KB, limit/fact, or explicit comparison queries. Those classes use bounded route construction and metadata-aware ranking instead.

```mermaid
sequenceDiagram
  participant User
  participant Agent
  participant MCP as RAG MCP Tool
  participant Planner as Deterministic router
  participant LanceDB
  participant Exact as Exact/Ripgrep path
  participant Kuzu
  participant Calc as Calculator
  participant Ledger

  User->>Agent: Ask question
  Agent->>MCP: hermes_master_search(query)
  MCP->>Planner: classify intent + build bounded routes
  Planner->>LanceDB: vector + FTS + scalar-filtered channels
  Planner->>Exact: exact identifiers / lexical safety net
  Planner->>Kuzu: graph context when useful
  Planner->>Calc: deterministic sizing/math if needed
  LanceDB-->>MCP: candidate evidence
  Exact-->>MCP: exact lexical evidence
  Kuzu-->>MCP: structural hints
  Calc-->>MCP: computed result + assumptions
  MCP->>Ledger: RRF, dedup, bounded boosts, weak-evidence notes
  Ledger-->>Agent: evidence packet + answer rules
  Agent-->>User: grounded answer or uncertainty
```

## Retrieval channels

The pipeline is intentionally more operational than a generic agentic-RAG loop. It does not only decide where to search; it also applies source authority, access policy, weak-evidence disclosure, deterministic tool precedence, and graph hygiene assumptions before answer generation.

### 1. Vector search

Best for semantic recall: paraphrases, conceptual questions, and product descriptions.

Failure mode: can retrieve plausible-but-wrong chunks when terminology overlaps.

### 2. Full-text search

Best for exact product names, error strings, CLI commands, part numbers, KB IDs, versions, and acronyms.

Failure mode: misses paraphrases and semantic matches.

### 3. Scalar metadata filters

Best for enforcing policy and narrowing scope:

- source family,
- access/confidentiality class,
- product family,
- version,
- migration/source lineage,
- document or section identity.

Failure mode: bad metadata can hide useful evidence, so schema audits matter.

### 4. Exact/deterministic lookup

Best for serial-like identifiers, KB numbers, known config keys, and hard-coded product aliases.

Failure mode: brittle when the identifier is absent or normalized differently.

### 5. Graph context

Best for expanding or explaining entity relationships.

Failure mode: graph proximity is not answer sufficiency.

### 6. Calculator/tool path

Best for sizing, usable capacity, RF/FT calculations, and repeatable math.

Failure mode: wrong assumptions. The answer must state assumptions and use RAG for context.

## Fusion strategy

A useful pipeline should not just concatenate results. NX-Shield uses these ideas:

- **RRF-style fusion** so independently strong channels rise.
- **Deduplication** by chunk/document identity so one source does not crowd the result set.
- **Source diversity** so official docs, KBs, design guides, and related references can coexist.
- **Bounded boosts** so metadata/source authority helps ranking without overpowering actual relevance.
- **Exact-identity promotion** for KB-only lookups, because an exact KB query is an identity search before it is a semantic search.
- **Comparison-collateral routing** for explicit comparison questions, so competitive/battlecard evidence can appear alongside official product evidence instead of being buried by Portal-only boosts.
- **Weak-evidence detection** so one-sided or low-authority evidence triggers caution.

## Output contract

The retrieval layer should return a packet like this:

```text
query_class: networking_production_impacting
verdict: review
answer_obligations:
  - compatibility evidence
  - post-change configuration steps
  - operational risk/caveats
evidence_ledger:
  supported:
    - Hardware guide mentions supported NIC family.
    - Network guide describes host/CVM uplink reconfiguration.
  weak_or_missing:
    - Exact customer part replacement path not found.
answer_rule:
  - Cite evidence for each procedural step.
  - Do not imply compatibility if source only supports adjacent model.
  - If exact evidence is missing, say so.
```

The language model should answer from this packet, not from vague memory.
