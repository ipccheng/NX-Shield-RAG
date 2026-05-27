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

## Runtime checks

A healthy runtime is not proven by "the process is running." Verify:

- MCP discovery lists the expected tool,
- a direct MCP canary returns evidence ledger output,
- profile-level agent calls use RAG before answering domain questions,
- calculator-first sizing queries call calculator path,
- access-policy canaries do not retrieve disallowed source families.

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
