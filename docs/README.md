# Documentation index

[Project home and diagram](../README.md) · [Publication rules](../CONTRIBUTING.md)

A reading path for infrastructure engineers who are new to AI, with deeper references for implementers and operators. These are RAG engineering patterns, not Nutanix solution guides or proof of a deployed system. The public repository does not include the RAG application implementation.

## 1. Understand

**Start with the vocabulary and the overall flow.**

- [RAG basics and glossary](getting-started/rag-basics.md) — ingestion versus query time; embeddings, chunks, reranking, and common misconceptions.
- [The query-path diagram](../diagrams/rag-query-path.png) — the numbered path from a question to an answer or an evidence gap.
- [Example query obligations](../examples/query-obligations.md) — turn a question into the points an answer needs to establish; examples are fictional, not product answers.

## 2. Design

**Decide what each component must do and what it must not be trusted to do.**

Recommended order:

1. [Architecture overview](design/architecture.md) — component responsibilities and data/control boundaries.
2. [Retrieval pipeline](design/retrieval-pipeline.md) — hybrid search, exact identifiers, optional helpers, and evidence selection.
3. [Evidence-ledger answering](design/evidence-ledger.md) — source traceability, missing support, and answer rules.
4. [Security and access policy](design/security-and-access.md) — identity, conflicting permissions, fallback paths, and model-processing boundaries.
5. [Governance boundaries](design/ai-governance-alignment.md) — data rights, ownership, oversight, and organizational review.

Deeper references:

- [Metadata and corpus design](design/metadata-and-corpus.md) — source authority, versions, and lineage.
- [LanceDB reference schema](design/lancedb-schema.md) — illustrative fields and validation invariants, not an executable migration.
- [Graph context with Ladybug](design/graph-context.md) — optional relationship hints and separately gated rollout.
- [Enterprise RAG design controls](design/enterprise-rag-strengths.md) — why these evidence and operating controls matter.

## 3. Build

**Prepare permitted, traceable evidence before serving questions.**

- [Ingestion and corpus build](build/ingestion-and-corpus.md) — source capture, parsing, metadata, indexing, and candidate validation.
- [Implementation responsibility map](build/implementation-map.md) — components an implementation owner must supply; no private source paths or credentials.
- [Evidence-ledger template](../templates/evidence-ledger-template.yaml) — an illustrative authoring template to adapt to your application schema.

## 4. Evaluate

**Measure behavior rather than assuming that a control works.**

- [Evaluation strategy](evaluate/evaluation-strategy.md) — retrieval, evidence, final-answer, access-isolation, and failure tests.
- [Design controls and validation gates](evaluate/design-controls.md) — a compact control-to-failure-mode checklist.
- [Design lessons](evaluate/design-lessons.md) — trade-offs and evaluation lessons, not a software release history.

No executable benchmark harness or public evaluation dataset is supplied. Deployment owners must run their own authorized, revision-bound tests.

## 5. Operate

**Keep serving, changes, and recovery observable and reversible.**

- [Runtime and MCP](operate/runtime-and-mcp.md) — tool interfaces, caller identities, service boundaries, and endpoint checks.
- [Operations playbook](operate/operations-playbook.md) — diagnosis, candidate promotion, backups, and rollback.
- [Recovery prerequisites and model](operate/recovery-model.md) — what an authorized owner needs to restore and test a deployment; not a public installer.

## Diagram and contribution resources

- [Diagram assets and renderer](../diagrams/README.md) — PNG, SVG, simplified Mermaid source, and reproducible rendering instructions.
- [Publication and contribution guidance](../CONTRIBUTING.md) — keep this repository focused on RAG engineering and exclude solution details and restricted material.
