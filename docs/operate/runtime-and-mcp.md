# Runtime and MCP Operations

NX-Shield RAG is served through MCP so different agents can call the same retrieval system through a stable tool boundary.

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

## Current public-safe runtime shape

The current deployed shape behind this design is:

- a Hermes-owned Nutanix RAG service using the unified v4 LanceDB corpus,
- one internal/default MCP service profile,
- one partner/NX-Shield-style MCP service profile with stricter access-policy checks,
- the same service-side tool concept, `hermes_master_search`, exposed through each profile,
- retrieval-time stale-KB policy rather than destructive deletion,
- deterministic routing for exact KB, limit/fact, and explicit comparison queries,
- optional graph/backfill context kept separate from the LanceDB schema contract,
- answer-verifier shadow checks before any delivery enforcement.

Public docs intentionally omit local ports, hostnames, LaunchAgent labels, and private filesystem paths. Those belong in the private source-recovery repo and operational backups.

## Runtime checks

A healthy runtime is not proven by "the process is running." Verify:

- MCP discovery lists the expected service-side tool,
- the gateway-registered MCP tool name is recognized by evidence extraction,
- a direct MCP canary returns evidence ledger output,
- profile-level agent calls use RAG before answering domain questions,
- calculator-first sizing queries call calculator path,
- access-policy canaries do not retrieve disallowed source families,
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

## Private source mapping

```text
ipccheng/NX-Shield-RAG-src
├── ops/launchagents/
├── rag/hermes-nutanix/config/mcp.yaml
├── rag/hermes-nutanix/config/gateway_config.json
├── rag/hermes-nutanix/scripts/openclaw/universal_gateway_mcp.py
└── hermes/profiles/{sam,nx-shield}/
```

## Operational rule

Restarting a gateway is not the same as restarting a RAG MCP service. When code/config changes cross service boundaries, verify the exact process that imports the changed module.

For profile-scoped gateways, verify that shared verifier modules are resolved from an explicit RAG source root or equivalent package path. Otherwise a gateway can retrieve evidence successfully but silently skip verification because the verifier import path is wrong.
