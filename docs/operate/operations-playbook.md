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

Fix: isolate the graph backend behind a service-safe probe or adapter, keep ranking in shadow/canary first, require source review for top-1 changes, and preserve a graph-disabled rollback mode.

## Canary categories

- exact identifier query,
- product/version query,
- production-impacting networking query,
- sizing/math query,
- competitive comparison query,
- weak-evidence query,
- access-policy negative query.
