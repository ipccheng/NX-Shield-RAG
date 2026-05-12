# MCP_SETUP.md - Nutanix RAG MCP Server Setup

Two MCP servers run as system daemons on Mac mini, serving Nutanix RAG search to OpenClaw agents. Sam and NX_Shield each have their own MCP server instance with independent configuration.

```
OpenClaw Gateway
|
+-- Sam (agent:main)
|   +-- rag-mcp-server-sam (port 8004)
|   +-- nutanix_rag_search.py (direct, no MCP)
|
+-- NX_Shield (agent:nutanix_shield)
    +-- rag-mcp-server (port 8001)
```

## Architecture

```
MCP Server (mcp_server.py)
  - port 8004 (Sam)
  - port 8001 (NX_Shield)
  - --rerank-top 30
  |
  v
LanceDB (nutanix_rag_v3_dedup.lance)
  ~85K rows + Kuzu graph DB (~120K nodes)
```

## Key Design Points

- **Isolation** — Each agent is a distinct bot on Discord. Sam's bot (ID A) should only serve Ivan; NX_Shield's bot (ID B) serves external engineers. Separate MCP servers prevent cross-pollination of queries.

- **Independent rerank_top** — Sam uses rerank_top=50 (more thorough), NX_Shield uses rerank_top=30 (faster, lower cost for external users)

- **Identity flag** — The `--identity nx_shield` flag tells the MCP server which bot is calling, so it can label itself correctly in responses

- **Per-agent tool names** — Sam's tool is `rag-mcp-server-sam`, NX_Shield's is `rag-mcp-server`. This prevents tool name collisions.

- **Why Sam bypasses MCP** — Sam calls nutanix_rag_search.py directly because it implements a richer two-pass search pipeline (topic classification → KB routing → reranking) that the MCP interface doesn't expose.

- **Why NX_Shield uses MCP** — NX_Shield runs as a fully isolated agent with no filesystem access, so the MCP tool is the only way to reach the RAG database.

## Kuzu Graph Integration

The RAG pipeline now includes Kuzu graph DB for entity-based boosting:

- LanceDB (vector search) → Kuzu (entity context boost) → reranking

- Entity matching: LanceDB's `mentioned_products` and `ecosystem_entities` are matched against Kuzu's `Entity.name`

- `[GRAPH]` tag in results indicates graph-boosted documents

## Port Assignments (Current)

| Port | Service | Agent | Identity Flag |
|------|---------|-------|------------|
| 8001 | NX_Shield MCP | agent:nutanix_shield | `--identity nx_shield` |
| 8002 | storage-calc | agent:main | — |
| 8003 | web-search-filtered | agent:main | — |
| 8004 | Sam MCP | agent:main | (none, defaults to Sam) |
| 8005 | slack-search-mcp | agent:nutanix_shield | — |

The MCP servers bind to 127.0.0.1 only — they are not exposed externally.

## Starting/Stopping MCP Servers

### Via launchd (Recommended)

Each MCP server runs as a launchd service. Check with:

```bash
launchctl list | grep mcp-nutanix
```

**Restart Sam MCP (port 8004):**

```bash
launchctl kickstart -k gui/$(id -u)/com.samai.mcp-nutanix-rag
launchctl start com.samai.mcp-nutanix-rag
```

**Restart NX_Shield MCP (port 8001):**

```bash
launchctl kickstart -k gui/$(id -u)/com.samai.mcp-nutanix-rag-shield
launchctl start com.samai.mcp-nutanix-rag-shield
```

### Manually

```bash
# Find the process
lsof -i :<PORT>

# Kill the old process if needed
kill <PID>

# Then restart via launchd
launchctl start com.samai.mcp-nutanix-rag
```

## OpenClaw Configuration

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
      },
      "storage-calc-mcp-server": {
        "url": "http://127.0.0.1:8002/",
        "description": "Nutanix storage capacity calculator"
      },
      "web-search-filtered": {
        "url": "http://127.0.0.1:8003/",
        "description": "Brave Search API with domain filtering"
      }
    }
  }
}
```

Tool name format: `{server_name}__{tool_name}` — the double underscore separates the server name from the tool name. This is how OpenClaw routes a tool call to the correct MCP server.

## Troubleshooting

### Check if running

```bash
ps aux | grep mcp_server | grep -v grep
```

### Check if the port is listening

```bash
lsof -i :8004
lsof -i :8001
```

### Test the MCP endpoint directly

```bash
curl -s http://127.0.0.1:8004/mcp/
```

### Check the log file for errors at startup time

```bash
tail -f ~/.openclaw/logs/mcp-nutanix-rag-sam.log
tail -f ~/.openclaw/logs/mcp-nutanix-rag-shield.log
```

### Verify the LanceDB file is present and readable

```bash
ls -la ~/.openclaw/memory/lancedb-pro/nutanix_rag_v3_dedup.lance/
```

### Run a direct search test

```bash
python3 ~/.openclaw/workspace/scripts/nutanix_rag_search.py "test query"
```

### Check disk space — LanceDB needs room for query operations

```bash
df -h ~
```

### Verify the mcp.servers block is present in openclaw.json

```bash
grep -A5 "mcp" ~/.openclaw/config/openclaw.json
```

### Restart the gateway

```bash
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
launchctl start ai.openclaw.gateway
```

## Data Paths

| Path | Description |
|------|-------------|
| `~/.openclaw/memory/lancedb-pro/nutanix_rag_v3_dedup.lance/` | LanceDB with ~85K rows |
| `~/.openclaw/memory/kuzu-pro/nutanix_graph_v3/` | Kuzu graph DB (~120K nodes) |
| `~/.openclaw/logs/mcp-nutanix-rag-sam.log` | Sam MCP server logs |
| `~/.openclaw/logs/mcp-nutanix-rag-shield.log` | NX_Shield MCP server logs |

- Sam's MCP server connects directly to these paths
- Sam also has a direct Python search script (nutanix_rag_search.py) for richer two-pass search — this is separate from MCP

## Known Issues

### Symptom: MCP server crashes with the following error every time a tool call is made

```
File "/.../starlette/routing.py", line 62, in app
    await response(scope, receive, send)
TypeError: 'NoneType' object is not callable
```

### Root Cause

When Starlette routes a request to a function endpoint defined as `async def endpoint(request)`, it wraps it in `request_response()` which creates an inner app expecting a return value. If the endpoint function signature is `async def endpoint(request)`, it receives a high-level Request object and MUST return a Response object. Returning None causes Starlette to try calling None() as if it were a callable.

The MCP SSE endpoints use low-level ASGI streams (scope, receive, send) internally but were declared with a single request argument. Since they don't return anything (they yield streams), Starlette received None as the "response" and crashed.

### Fix

Wrap each endpoint in a class that implements the pure ASGI `__call__(scope, receive, send)` interface. Starlette's Route checks `isinstance(type(endpoint), type)` — if the endpoint is a class (not a function), it routes it directly as an ASGI app without wrapping it in `request_response()`.

```python
# ❌ WRONG — Starlette wraps this in request_response(), expects a Response return
async def endpoint_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], ...)

# ✅ CORRECT — class with __call__ gets routed as pure ASGI, no Response needed
class _ASGIEndpointWrapper:
    """Wraps a (scope, receive, send) ASGI callable for pure-ASGI routing in Starlette."""
    def __init__(self, fn):
        self.fn = fn
    async def __call__(self, scope, receive, send):
        await self.fn(scope, receive, send)

async def endpoint_sse_raw(scope, receive, send):
    async with sse.connect_sse(scope, receive, send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())

endpoint_sse = _ASGIEndpointWrapper(endpoint_sse_raw)
```

Additional note: The exception handler must use the `(request, exc)` signature — Starlette's ExceptionMiddleware calls it with two arguments, not four.

```python
# ❌ WRONG — four-argument signature
async def global_exception_handler(request, exc, scope, receive):
    ...

# ✅ CORRECT — two-argument signature
async def global_exception_handler(request, exc):
    ...
```

---

*Last updated: 2026-05-12*