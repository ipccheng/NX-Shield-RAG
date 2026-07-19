# Operations Playbook

This playbook is intentionally public-safe and implementation-neutral.

## Before changing runtime behavior

1. Identify which service owns the behavior: agent gateway, RAG MCP, storage calculator, data store, or profile prompt.
2. Take a backup of the relevant config/script.
3. Make one change at a time.
4. Restart only the affected service.
5. Verify with direct service canary and profile-level canary.

## Common failure classes

### Stale process imports

Symptom: source code contains a symbol/config, but the running process errors as if it does not.

Likely cause: long-running Python process loaded old modules before a source update.

Fix: restart the specific gateway/MCP service that imports the module, then verify process start time and logs.

### Wrong endpoint locality

Symptom: local test passes, agent still sees old behavior.

Likely cause: multiple machines or profiles use `127.0.0.1` endpoints, and the test hit a different localhost than the agent.

Fix: test local direct, remote direct, and profile-discovered MCP endpoint separately.

### Retrieval good, answer bad

Symptom: correct source is in top results but final answer is wrong.

Likely cause: answer synthesis failure, not retrieval failure.

Fix: improve Evidence Ledger / answer rules and add regression canary.

### Policy gap in fallback path

Symptom: vector search is filtered correctly, but local grep/chat/web fallback leaks disallowed content.

Fix: apply access policy to every retrieval/fallback path, not only LanceDB.

### Store drift between hosts

Symptom: one profile retrieves newer documents or graph context while another does not.

Likely cause: vector store, graph store, or source artifacts were updated on one host but not synced to the other.

Fix: run a report-first parity check using stable row counts, schema hashes, chunk/document digests, graph node/edge counts, and fresh MCP canaries. Sync only after a destination backup and restart only the scoped RAG services that hold the stores open.

### Graph backend migration risk

Symptom: graph retrieval works in a foreground test but causes service instability or native-module conflicts in the long-running runtime.

Likely cause: graph drivers and other native libraries are loaded in the same process, or the candidate graph backend was promoted before deterministic ordering and rollback gates were proven.

Fix: isolate the graph backend behind a service-safe probe or adapter, keep ranking in shadow/canary first, require source review for top-1 changes, and preserve a graph-disabled rollback mode. When a replacement graph backend is active, freeze writes to the retired backend before deleting it; keep the old graph as a read-only rollback/archive until parity, dependency, and rollback checks pass.

### Embedding provider malformed response

Symptom: many unrelated retrieval cases fail at the vector-search stage with a missing-field, empty-vector, or provider-error response instead of ordinary no-results behavior.

Likely cause: the embedding endpoint returned an error object or malformed payload, or credentials/provider state changed. This is not a signal to re-ingest documents, rebuild graph edges, or prune corpus rows.

Fix: validate response shape before reading embedding fields, redact provider error details in logs, retry only within a bounded window, fail closed with an actionable error, and rerun the report-only harness after the dependency is healthy.

### Context-wrapped query pollution

Symptom: a direct clean query retrieves good evidence, but the live gateway/tool path retrieves weak or no evidence for the same user intent.

Likely cause: the gateway wrapped the live question with previous answer context, diagnostic prose, or tool instructions, and the retrieval router treated the wrapper text as equally important.

Fix: extract and route the current question first. Use previous-turn context only as a secondary signal, and add canaries for both clean and wrapped query shapes.

## Backup reliability model

Keep large or sensitive runtime data outside Git, but keep the backup logic and recovery contract under source control.

For each mandatory backup stage:

1. Write into a per-run staging or hidden partial path.
2. Record an initial manifest before long-running work and checkpoint it between stages.
3. Apply a bounded child timeout while keeping the scheduler timeout above the full stage budget.
4. Validate the artifact format and content before promotion—for example ZIP member/CRC checks, gzip integrity, a database-dump header, or a representative restore smoke test.
5. Atomically promote only a validated artifact into the trusted archive directory.
6. Move incomplete or corrupt residue into a clearly separated failed-run area; never leave it with a success-looking name beside trusted backups.
7. Keep backup directories and artifacts private because archives may contain credentials, profile state, and internal source material.

Regeneratable runtime caches should not be treated as authoritative backup content. If a cache contains a browser- or service-owned SQLite database, exclude only the narrowly identified root cache path rather than weakening coverage for user data or active stores.

Active data-store coverage should follow the current architecture. A RAG recovery set normally includes source documents, the vector store, the active graph store, and any legacy graph required for rollback. Skip or quiesce a snapshot when a likely writer is active.

Retention is a separate safety decision. Measure per-run growth and restore confidence before enabling deletion; a successful backup job is not by itself approval to prune old recovery points.

## Canary categories

- exact identifier query,
- product/version query,
- production-impacting networking query,
- sizing/math query,
- competitive comparison query,
- weak-evidence query,
- access-policy negative query.
