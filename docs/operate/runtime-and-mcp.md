# Runtime and MCP Operations

[Documentation index](../README.md) · [Project home](../../README.md)

> **Scope:** Independent project design guidance, not a Nutanix-approved implementation. This page does not establish deployed behavior, measured effectiveness, or vendor support. The public repository does not include a runnable service.

## Reading this page

**MCP (Model Context Protocol)** exposes tools to an agent application. A **profile** selects application configuration and policy; its permissions must be bound to authenticated identity. A **gateway** connects user/agent requests to services. A **canary** is a representative regression test. **Endpoint locality** asks which machine and process a request actually reaches. A **LaunchAgent** is a macOS service-launch configuration; other platforms use their own process manager.

The reference design exposes RAG through MCP so different agents can call the same retrieval system through a stable tool boundary.

## Why MCP

MCP gives a clean boundary between:

- the agent profile and its prompt/tool policy,
- the RAG service and its retrieval implementation,
- deterministic tools such as storage calculators,
- profile-specific access policy.

## Canonical tool concept

The RAG service exposes a search tool conceptually named:

```text
hermes_master_search
```

Profiles may see a longer native tool name depending on MCP client prefixing, but the service-side concept should stay stable.

## Service separation

Recommended service split:

- default/internal RAG MCP service,
- dedicated partner/public-facing RAG MCP service if needed,
- shared storage calculator MCP service,
- agent gateways as separate profile processes.

This allows independent restart, logging, policy, and rollback.

### Identity consistency invariant

Each service must declare the same serving identity in its environment, process arguments, and policy configuration. A partner/public-facing service must never inherit an internal identity through a copied LaunchAgent or default argument. Startup validation and canaries should fail closed on an identity mismatch or missing identity.

## Reference service shape

An implementation can separate responsibilities as follows; this is not a deployment inventory:

- a RAG service using a compatible unified LanceDB corpus,
- one internal/default MCP service profile,
- one partner-facing MCP service profile with stricter access-policy checks,
- the same service-side tool concept, `hermes_master_search`, exposed through each profile,
- retrieval-time stale-KB policy rather than destructive deletion,
- deterministic routing for exact KB, limit/fact, and explicit comparison queries,
- Ladybug graph context kept separate from the LanceDB evidence schema contract,
- service-safe graph probe mode for graph backend canaries,
- graph ranking promoted only through shadow, guarded-canary, and rollback-gated live steps,
- answer-verifier shadow checks before any delivery enforcement.

Public docs intentionally omit local ports, hostnames, LaunchAgent labels, and private filesystem paths. Those belong in the private source-recovery repo and operational backups.

## SDK-only deployment boundary

An SDK-only implementation can use a host-native graph virtual environment, with explicit interpreter and dependency bindings. Validate imports through the actual service adapter; a foreground shell import does not prove the managed service uses the same environment. No container or graph-server installation is implied. Treat any retained Kuzu store as rollback/archive only, not an active helper; a rollback selection must not silently fall forward to the current backend.

## Staged endpoint qualification

Qualify native/direct calls, private-facing transport, and public-facing transport separately for every configured endpoint. Bind each result to its actual service identity, policy, snapshot, and loaded code. Include positive retrieval, unknown identity, conflicting duplicates, restricted-origin graph hints, malformed embeddings, and graph-disabled behavior. A native pass does not prove either transport path, and a private endpoint pass does not qualify a public endpoint.

Stage report-only comparison, restricted canary exposure, then explicit promotion. On shutdown, wait for the service manager to confirm the exact owned service is unloaded and its workers are gone; port closure alone is insufficient because an auto-restart can reopen stores. Do not unload unrelated services. Require fresh-process canaries after restart and test rollback through the same endpoint path.

## Store parity and sync checks

For multi-host RAG serving, "the code is deployed" is not enough. Treat vector store, graph store, source documents, service config, and profile policy as separate parity layers.

A safe store-sync workflow should:

1. compare logical row counts, schema hashes, and stable document/chunk digests before replacement,
2. back up the destination stores before copying,
3. stop only the services that hold the destination stores open,
4. copy directory-backed vector stores and file-backed graph stores with the correct filesystem semantics,
5. retain journal, lock, and recovery files unless the database-specific recovery procedure explicitly permits removal after backup and writer shutdown,
6. reopen/checkpoint the copied graph store before service restart,
7. verify fresh MCP clients for every serving profile.

Physical database file hashes can differ after a checkpoint or reopen even when the logical graph is identical. Prefer logical parity checks — node/edge counts, stable chunk identifiers, and schema/table shape — over raw file hashes alone. Require sidecar absence only when the selected backend/version documents that expectation for the tested mode. Do not delete legitimate journal or lock files to make a check pass.

## Runtime checks

A healthy runtime is not proven by "the process is running." Verify:

- MCP discovery lists the expected service-side tool,
- the gateway-registered MCP tool name is recognized by evidence extraction,
- a direct MCP canary returns evidence ledger output,
- profile-level agent calls use RAG before answering domain questions,
- calculator-first sizing queries call calculator path,
- access-policy canaries do not retrieve disallowed source families,
- the service identity matches its environment, launch arguments, and policy profile,
- answer-verifier shadow reports are generated for the same live turn,
- verifier delivery decisions are logged before sending the final response,
- graph-shadow evaluation is report-only until promoted.

## Answer-verifier rollout

Answer verification should be enabled in phases:

1. **Report-only CLI** — run verifier against saved or generated evidence packets.
2. **Shadow runtime** — run verifier during live agent turns but do not change the delivered response.
3. **Warn/rewrite** — allow `REWRITE_REQUIRED` verdicts to trigger one safe regeneration or a visible caution.
4. **Enforce** — fail closed only after the shadow and warn phases show acceptable false-positive and latency behavior.

The verifier should check:

- whether the answer is supported by retrieved evidence,
- whether restricted evidence leaked into a lower-trust profile,
- whether deterministic calculator output was used for math/sizing,
- whether weak competitive evidence is disclosed rather than hidden.

## Operational rule

Restarting a gateway is not the same as restarting a RAG MCP service. When code/config changes cross service boundaries, verify the exact process that imports the changed module.

For profile-scoped gateways, verify that shared verifier modules are resolved from an explicit RAG source root or equivalent package path. Otherwise a gateway can retrieve evidence successfully but silently skip verification because the verifier import path is wrong.
