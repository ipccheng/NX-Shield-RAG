# Implementation Responsibility Map

This page maps public design concepts to components an implementing team would need to supply. The filename is retained for existing links; private repository names, paths, and profile identifiers are intentionally not published.

This repository is an independent design notebook, not a runnable software distribution or a Nutanix-approved implementation. Reading it does not require access to private source.

| Design concept | Implementation responsibility | Public reference |
| --- | --- | --- |
| Search entry point and query routing | Classify the question and construct bounded search routes | [Retrieval pipeline](../design/retrieval-pipeline.md) |
| Retrieval backend | Query vector and full-text indexes; reconcile identity and policy | [Schema](../design/lancedb-schema.md) |
| MCP adapter | Expose retrieval as a tool; authenticate callers and bind access policy | [Runtime and MCP](../operate/runtime-and-mcp.md) |
| Calculator | Validate inputs, compute results, return units and assumptions | [Evidence ledger](../design/evidence-ledger.md) |
| Ingestion and entity extraction | Normalize authorized sources and retain provenance | [Ingestion](ingestion-and-corpus.md) |
| Graph adapter | Return bounded relationship hints linked to authorized evidence | [Graph context](../design/graph-context.md) |
| Answer verifier | Compare draft claims with current-turn evidence; gate delivery | [Evaluation](../evaluate/evaluation-strategy.md) |
| Service configuration and recovery | Declare identities, dependencies, backups, and rollback | [Rebuild prerequisites](rebuild-from-private-source.md) |

## Maintainer responsibility

Maintain exact source locations, package versions, launch configuration, and recovery manifests in access-controlled implementation records. Those records must identify what was actually tested; this conceptual map is not proof that any component is deployed or verified.
