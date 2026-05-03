# MCP Server Setup — Nutanix RAG Pipeline

## Overview

Two MCP servers run as system daemons on Mac mini, serving Nutanix RAG search to OpenClaw agents.

| Service | Identity | Port | Agent | Rerank Top |
|---------|----------|------|-------|------------|
| `mcp-nutanix-rag` | Sam | 8004 | agent:main (personal assistant) | 50 |
| `mcp-nutanix-rag-shield` | NX_Shield | 8001 | agent:nutanix_shield (external engineers) | 30 |

Sam's MCP server is called by the gateway via the `rag-mcp-server-sam` tool. NX_Shield calls its MCP server via `rag-mcp-server` tool. Both use the same Python MCP server binary.

## Launchd Services

```
~/Library/LaunchAgents/com.samai.mcp-nutanix-rag.plist        → port 8004 (Sam)
~/Library/LaunchAgents/com.samai.mcp-nutanix-rag-shield.plist → port 8001 (NX_Shield)
~/Library/LaunchAgents/com.samai.mcp-storage-calc.plist       → port 8002
~/Library/LaunchAgents/com.samai.mcp-web-search.plist          → port 8003
```

All configured with `KeepAlive` and `RunAtLoad`.

## MCP Server Binary

Both MCP servers run the same Python script:

```
mcp_server.py --rerank-top 30 --port <PORT> [--identity nx_shield]
```

- `--identity nx_shield` is set only on the NX_Shield server
- Without it, the server identifies as "Sam"

Location: `~/.openclaw/workspace/skills/nutanix-rag-search/scripts/mcp_server.py`

## RAG Database

```
~/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/
```

- Size: ~1.2GB
- Rows: ~130,000
- Search script: `~/.openclaw/workspace/skills/nutanix-rag-search/scripts/nutanix_rag_search.py`
- Sam uses the search script directly (two-pass search with topic classification), not the MCP tool

## Port Assignments

| Port | Service | Purpose |
|------|---------|---------|
| 8001 | NX_Shield MCP | RAG query for external engineers |
| 8002 | storage-calc | Nutanix storage sizing (storage-calc-mcp-server) |
| 8003 | web-search-filtered | Brave search MCP (web-search-filtered__) |
| 8004 | Sam MCP | RAG query for Ivan's personal assistant |

## Startup Logs

Logs written to:

```
~/.openclaw/logs/mcp-nutanix-rag-sam.log
~/.openclaw/logs/mcp-nutanix-rag-shield.log
```

## Agent Configuration

### Sam (agent:main)

Uses `rag-mcp-server-sam` MCP tool pointing to port 8004. Sam's workspace skill also includes `nutanix_rag_search.py` for direct two-pass RAG search (topic classification → specific search → reranking).

### NX_Shield (agent:nutanix_shield)

Uses `rag-mcp-server` MCP tool pointing to port 8001. Configured for external engineer isolation — per-user session separation, no memory injection from Hindsight (via `ignoreSessionPatterns`).