# MCP Server Setup — Nutanix RAG Pipeline

## Overview

Two MCP servers run as system daemons on Mac mini, serving Nutanix RAG search to OpenClaw agents. Sam and NX_Shield each have their own MCP server instance with independent configuration.

## Architecture

```
OpenClaw Gateway
|
+-- Sam (agent:main)
|       +-- rag-mcp-server-sam
|       +-- nutanix_rag_search.py (direct, no MCP)
|
+-- NX_Shield (agent:nutanix_shield)
|       +-- rag-mcp-server
|
+-------|
        v
MCP Server (mcp_server.py)
  - port 8004 (Sam)
  - port 8001 (NX_Shield)
  - --rerank-top 30
        |
        v
LanceDB (nutanix_rag_v3.lance)
  ~1.2GB, ~130K rows
``` 

## Design Decisions

### Why separate MCP servers for Sam and NX_Shield?

1. **Isolation** — Each agent is a distinct bot on Discord. Sam's bot (ID A) should only serve Ivan; NX_Shield's bot (ID B) serves external engineers. Separate MCP servers prevent cross-pollination of queries.
2. **Independent rerank_top** — Sam uses `rerank_top=50` (more thorough), NX_Shield uses `rerank_top=30` (faster, lower cost for external users)
3. **Identity flag** — The `--identity nx_shield` flag tells the MCP server which bot is calling, so it can label itself correctly in responses
4. **Per-agent tool names** — Sam's tool is `rag-mcp-server-sam`, NX_Shield's is `rag-mcp-server`. This prevents tool name collisions.

### Why MCP at all for NX_Shield, but Sam uses the script directly?

- **Sam** bypasses MCP and calls `nutanix_rag_search.py` directly because it implements a richer two-pass search pipeline (topic classification → KB routing → reranking) that the MCP interface doesn't expose.
- **NX_Shield** uses MCP because it runs as a fully isolated agent with no filesystem access, so the MCP tool is the only way to reach the RAG database.

## Port Assignments

| Port | Service | Agent | Identity Flag |
|------|---------|-------|--------------|
| 8001 | NX_Shield MCP | agent:nutanix_shield | `--identity nx_shield` |
| 8002 | storage-calc | agent:main | — |
| 8003 | web-search-filtered | agent:main | — |
| 8004 | Sam MCP | agent:main | (none, defaults to Sam) |

The MCP servers bind to `127.0.0.1` only — they are not exposed externally.

## Launchd Services

```
~/Library/LaunchAgents/com.samai.mcp-nutanix-rag.plist        → Sam MCP        (port 8004)
~/Library/LaunchAgents/com.samai.mcp-nutanix-rag-shield.plist → NX_Shield MCP (port 8001)
~/Library/LaunchAgents/com.samai.mcp-storage-calc.plist       → port 8002
~/Library/LaunchAgents/com.samai.mcp-web-search.plist          → port 8003
```

Each plist sets:
- `KeepAlive: true` — restarts if the process crashes
- `RunAtLoad: true` — starts at login
- Environment variable `NX_RAG_PORT` and optionally `NX_AGENT_IDENTITY`

## MCP Tool Config (openclaw.json)

The MCP tool definitions are registered in `openclaw.json` under `mcp.servers`:

```json
{
  "mcp": {
    "servers": {
      "rag-mcp-server-sam": {
        "url": "http://127.0.0.1:8004/mcp/",
        "description": "Nutanix RAG knowledge base for Sam"
      },
      "rag-mcp-server": {
        "url": "http://127.0.0.1:8001/mcp/",
        "description": "Nutanix RAG knowledge base for NX_Shield"
      }
    }
  }
}
```

The tool name `rag-mcp-server__query_nutanix_docs` is constructed from `{server_name}__{tool_name}` — the double underscore separates the server name from the tool name. This is how OpenClaw routes a tool call to the correct MCP server.

## Starting and Stopping MCP Servers

**Check if running:**
```bash
ps aux | grep mcp_server | grep -v grep
```

**Restart Sam MCP:**
```bash
launchctl kickstart -k gui/$(id -u)/com.samai.mcp-nutanix-rag
launchctl start com.samai.mcp-nutanix-rag
```

**Restart NX_Shield MCP:**
```bash
launchctl kickstart -k gui/$(id -u)/com.samai.mcp-nutanix-rag-shield
launchctl start com.samai.mcp-nutanix-rag-shield
```

**Check service status:**
```bash
launchctl list | grep mcp-nutanix
```

**Reload after config change:**
```bash
launchctl unload ~/Library/LaunchAgents/com.samai.mcp-nutanix-rag.plist
launchctl load ~/Library/LaunchAgents/com.samai.mcp-nutanix-rag.plist
```

## Logs

```
~/.openclaw/logs/mcp-nutanix-rag-sam.log
~/.openclaw/logs/mcp-nutanix-rag-shield.log
```

Both stdout and stderr are written to the same log file.

## RAG Database

```
~/.openclaw/memory/lancedb-pro/nutanix_rag_v3.lance/
```

- Sam's MCP server connects directly to this path
- Sam also has a direct Python search script (`nutanix_rag_search.py`) for richer two-pass search — this is separate from MCP

## Common Issues

### MCP tool returns "not found" or "connection refused"

1. Check the MCP server process is running:
   ```bash
   ps aux | grep mcp_server | grep -v grep
   ```

2. Check if the port is listening:
   ```bash
   lsof -i :8004
   lsof -i :8001
   ```

3. Test the MCP endpoint directly:
   ```bash
   curl -s http://127.0.0.1:8004/mcp/
   ```

4. Check the log file for errors at startup time

### RAG returns no results / empty response

1. Verify the LanceDB file is present and readable
2. Run a direct search test:
   ```bash
   python3 ~/.openclaw/workspace/skills/nutanix-rag-search/scripts/nutanix_rag_search.py "test query"
   ```
3. Check disk space — LanceDB needs room for query operations

### Agent not finding the MCP tool

1. Verify the `mcp.servers` block is present in `openclaw.json`
2. Restart the gateway:
   ```bash
   launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
   launchctl start ai.openclaw.gateway
   ```
3. Check the gateway log for MCP registration messages

### Port already in use

```bash
lsof -i :<PORT>
# Kill the old process if needed
kill <PID>
# Then restart via launchd
launchctl start com.samai.mcp-nutanix-rag
```
