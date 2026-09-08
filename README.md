# NX-Shield RAG

**Find relevant evidence. Check the answer. Make uncertainty visible.**

This is the public engineering handbook for our retrieval-augmented generation (RAG) system. It explains how retrieval, source permissions, evidence checks, and operations fit together—for technical readers who may be new to AI.

The RAG application implementation and recovery source are private. This repository contains **documentation, examples, and diagram-rendering tools—not an installable RAG service**. It is an independent project, not an official Nutanix product or validated design.

## From a question to a checkable answer

[![NX-Shield RAG: question and identity, retrieval, evidence ledger, draft, verification, and answer or evidence gap. A connected detail panel explains search, optional helpers, permissions, ranking, and bounded recovery.](diagrams/rag-query-path.png)](diagrams/rag-query-path.png)

[Open full-size PNG](diagrams/rag-query-path.png) · [Editable SVG](diagrams/rag-query-path.svg) · [Diagram source and rendering](diagrams/README.md)

Read the numbered path from top to bottom. The right-hand panel expands retrieval; the dashed revision loop returns a draft for another check. **This is a reference design, not a live deployment or accuracy claim.** Access restrictions and permitted model-processing boundaries apply throughout the path.

## Start here

New to RAG? Think of it as an open-book answer: the application finds useful reference passages before asking a language model to write. Retrieval changes the information supplied to the model; it is not the same as training the model on those documents.

Follow the handbook in this order, or jump to your area:

1. **Understand** — [RAG basics and glossary](docs/getting-started/rag-basics.md). Learn the terms and separate data preparation from question answering.
2. **Design** — [Architecture](docs/design/architecture.md). Follow the component responsibilities, retrieval path, evidence ledger, and security boundaries.
3. **Build** — [Ingestion and corpus](docs/build/ingestion-and-corpus.md). Prepare permitted documents, metadata, and searchable indexes.
4. **Evaluate** — [Evaluation strategy](docs/evaluate/evaluation-strategy.md). Test relevance, claim support, denied access, failure handling, and latency separately.
5. **Operate** — [Operations playbook](docs/operate/operations-playbook.md). Manage diagnosis, controlled changes, recovery, and rollback.

**[Browse the complete documentation index →](docs/README.md)**

## Why more than vector search?

Finding similar text is only one part of answering a technical question. This design also considers:

- **Hybrid retrieval:** combine meaning-based search, keywords, and exact identifiers.
- **Source and access policy:** distinguish relevant evidence from evidence the caller is allowed to use.
- **An evidence ledger:** record supporting sources, assumptions, and unanswered points before drafting.
- **Deterministic tools:** compute arithmetic with explicit inputs rather than asking a model to guess.
- **Optional graph hints:** use relationships to assist search, not to establish facts.
- **Answer checks:** compare the draft with its evidence, then deliver, qualify, revise, or withhold it.

These are controls to implement and evaluate—not guarantees of correctness. A citation must support its claim; a keyword match or passing automated check is not enough by itself.

## Repository guide

```text
README.md                 Visual overview and starting points
CONTRIBUTING.md           Public scope and contribution rules
docs/README.md            Complete handbook and reading order
docs/getting-started/     RAG concepts and glossary
docs/design/              Architecture, retrieval, evidence, metadata, security
docs/build/               Ingestion and implementation responsibilities
docs/evaluate/            Test strategy, control checklist, design lessons
docs/operate/             Runtime, operations, and recovery model
diagrams/                 PNG, editable SVG, Mermaid, and rendering source
examples/                 Fictional query and evidence-obligation examples
templates/                Illustrative evidence-ledger template
```

## Scope and publication boundaries

- **Our RAG engineering belongs here. Nutanix solution technical information belongs in the RAG knowledge collection, not in this public repository.** Do not add product feature guides, solution deployment details, or solution-specific integrations—even when their sources are public.
- Do not publish customer data, internal enablement, licensed analyst extracts, source-document collections, private operational reports, live environment details, or credentials.
- Permission to read a source does not automatically grant permission to redistribute it or send it to a model service.
- This handbook does not establish vendor support, licensing, compatibility, formal approval, compliance certification, or production readiness.

See [publication and contribution guidance](CONTRIBUTING.md) before proposing changes.
