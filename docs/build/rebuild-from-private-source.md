# Rebuild Prerequisites and Recovery Model

This is a conceptual recovery checklist for an authorized implementation owner, not an installation guide. This public repository contains no runnable RAG service, dependency lockfile, source corpus, credentials, or tested restore bundle. It cannot reproduce the private implementation on its own.

NX-Shield RAG is an independent project, not a Nutanix-approved implementation. Technical recovery checks do not establish vendor support or approval for a use case.

## What a reader can reuse

The public documents describe retrieval, ingestion, metadata, evidence-ledger answering, profile-aware serving, and evaluation. Use the [implementation responsibility map](private-source-map.md) to identify the components your team must build or obtain through authorized channels.

## What an implementation owner must supply

- Authorized source code and configuration, with a recorded revision and compatible dependency versions.
- An agent or application capable of calling the retrieval interface; MCP (Model Context Protocol) is the interface pattern used here.
- Consistent backups of the vector store, graph store, and authorized source documents, with schema and embedding-model metadata.
- Credentials obtained from a secure vault, never from the public repository.
- Identity and source-access policies, provider/data-flow review, and approval for the intended users and data.
- A private recovery manifest containing actual locations, commands, expected results, and rollback steps.

Back up optional application state only when it is required for recovery or approved audit purposes. Do not restore conversation history into a public/demo service by default.

## High-level recovery sequence

1. Select a tested source revision and compatible application, database, graph-driver, and model dependencies.
2. Provision an isolated environment with external serving disabled.
3. Restore source documents and consistent data-store snapshots to explicitly configured locations.
4. Restore secrets from the vault and validate configuration syntax without printing secrets.
5. Check schema compatibility, embedding dimensions and model identity, document/chunk identities, and graph links before starting retrieval.
6. Start only the required services under a process manager, using a least-privilege identity.
7. Run direct retrieval checks, including exact identifiers, weak evidence, calculators, and forbidden-source cases.
8. Exercise the actual application path: verify tool discovery, evidence extraction, identity enforcement, and answer delivery decisions.
9. Test rollback and record results against the exact restored artifacts.
10. Enable the intended interface only after technical gates and organizational approvals pass.

## Recovery acceptance checklist

A **canary** is a small representative test used to detect a regression. Passing a canary is not a complete quality or security assessment.

- [ ] Backup logic passes syntax and fault-injection tests before scheduling.
- [ ] Archives pass integrity checks and a representative restore test; a valid archive alone does not prove application recovery.
- [ ] Vector and graph stores open with the expected schema and compatible indexes.
- [ ] The configured search tool is discoverable and callable by each intended identity.
- [ ] Service identity is consistent across environment, launch arguments, and policy configuration.
- [ ] Calculator results include inputs, units, assumptions, and calculation provenance.
- [ ] An evidence ledger reaches the answer path and weak-evidence cases disclose uncertainty.
- [ ] Negative access tests exclude unauthorized content from results, fallbacks, caches, and logs.
- [ ] The answer verifier and delivery decision are correlated to the same user turn.
- [ ] Rollback restores a compatible source/configuration/store set and passes fresh canaries.

See [operations](../operate/operations-playbook.md) for candidate promotion and backup controls, and [evaluation](../evaluate/evaluation-strategy.md) for broader release gates.
