# MCP Server Setup — Nutanix RAG Pipeline (Updated 2026-05-13)

> **Last updated:** 2026-05-13
> **Status:** Active — Updated to reflect current `nx_gateway_mcp.py` architecture

---

## Overview

Two MCP servers run as system daemons on Mac mini, serving Nutanix RAG search to OpenClaw agents. Each agent (Sam and NX_Shield) has its own MCP server instance with identity-based access control, both running `nx_gateway_mcp.py` as the backend.

**The old `mcp_server.py` (port 8001) is still registered but superseded by the new `nx_gateway_mcp.py` instances.**

---

## Architecture

```
OpenClaw Gateway
│
├── Sam (agent:main)
│   └── tool: sam-gateway__master_search
│       └── HTTP SSE → nx_gateway_mcp.py (port 8011, identity=sam)
│           └── spawns: nutanix_rag_search.py --identity sam
│               ├── Jina embed + LanceDB hybrid search
│               ├── Kuzu graph walk (parallel)
│               ├── ripgrep /opt/homebrew/bin/rg (parallel)
│               └── Slack → SearXNG fallback waterfall
│
└── NX_Shield (agent:nutanix_shield)
    └── tool: gateway-mcp__master_search
        └── HTTP SSE → nx_gateway_mcp.py (port 8010, identity=nx_shield)
            └── spawns: nutanix_rag_search.py --identity nx_shield
                └── Same pipeline, hard-filtered to access_level='public'
```

---

## Design Decisions

### Why `nx_gateway_mcp.py` instead of calling the script directly?

`nx_gateway_mcp.py` is a thin SSE-to-subprocess bridge. It wraps `nutanix_rag_search.py` as a subprocess and exposes it as an MCP tool. Benefits:

1. **Protocol translation** — OpenClaw speaks MCP/SSE; `nutanix_rag_search.py` speaks plain stdout JSON
2. **Identity enforcement at the gateway layer** — each MCP server instance has its own `--identity` baked in at launchd startup
3. **Session-aware rate limiting** — `_check_and_increment()` uses session file mtime to track calls per session turn
4. **Timeout isolation** — each query runs in its own subprocess with a 90s timeout; crashes don't bring down the server

### Why separate MCP servers for Sam and NX_Shield?

1. **Identity isolation** — Sam (`identity=sam`) sees all content; NX_Shield (`identity=nx_shield`) is hard-filtered to `access_level='public'` at the LanceDB query level
2. **Independent rate limits** — `gateway_config.json` (`max_calls_per_session`) allows Sam 3 calls/query turn, NX_Shield only 2
3. **Separate process** — a crash in one doesn't affect the other

### Sam bypasses MCP and calls the script directly?

**No — this is outdated.** Sam uses `sam-gateway__master_search` via the MCP server on port 8011. This was updated after the original docs were written.

---

## Port Assignments

| Port | Server Name (openclaw.json) | Script | Identity | rerank_top | Used By |
|------|----------------------------|--------|----------|------------|---------|
| 8001 | `rag-mcp-server` | `mcp_server.py` (old, deprecated) | — | 30 | Not in active use |
| 8010 | `gateway-mcp` | `nx_gateway_mcp.py` | `nutanix_shield` | 5 | NX_Shield |
| 8011 | `sam-gateway` | `nx_gateway_mcp.py` | `sam` | 5 | Sam |

---

## MCP Tool Names

The tool name format is `{server_name}__{tool_name}` (double underscore):

| Server | Tool Name | Full Qualified Name |
|--------|-----------|-------------------|
| `sam-gateway` | `master_search` | `sam-gateway__master_search` |
| `gateway-mcp` | `master_search` | `gateway-mcp__master_search` |

Sam's `sam-gateway__master_search` tool is the one referenced in `IDENTITY.md` as the mandatory first-resort tool for Nutanix technical questions.

---

## Gateway Config (`gateway_config.json`)

Located at `~/.openclaw/workspace/scripts/gateway_config.json`. Controls per-agent rate limits:

```json
{
  "max_calls_per_session": {
    "nutanix_shield": 2,
    "default": 1,
    "main": 3
  }
}
```

- **`main`** = Sam (agent:main) — 3 calls per query turn
- **`nutanix_shield`** = NX_Shield — 2 calls per query turn
- **`default`** — fallback for unknown agents

---

## Launchd Services

Check running MCP servers:
```bash
lsof -i :8001 -i :8010 -i :8011 | grep LISTEN
```

| Service Name | Script | Port | Identity | Config File |
|---|---|---|---|---|
| `com.samai.mcp-nutanix-rag` | `mcp_server.py` (old) | 8001 | — | `com.samai.mcp-nutanix-rag.plist` |
| `com.samai.mcp-gateway-nx-shield` | `nx_gateway_mcp.py` | 8010 | `nutanix_shield` | `com.samai.mcp-gateway-nx-shield.plist` |
| `com.samai.mcp-gateway-sam` | `nx_gateway_mcp.py` | 8011 | `sam` | `com.samai.mcp-gateway-sam.plist` |

**Restart NX_Shield MCP:**
```bash
launchctl kickstart -k gui/$(id -u)/com.samai.mcp-gateway-nx-shield
launchctl start com.samai.mcp-gateway-nx-shield
```

**Restart Sam MCP:**
```bash
launchctl kickstart -k gui/$(id -u)/com.samai.mcp-gateway-sam
launchctl start com.samai.mcp-gateway-sam
```

**Restart old MCP (if ever needed):**
```bash
launchctl kickstart -k gui/$(id -u)/com.samai.mcp-nutanix-rag
launchctl start com.samai.mcp-nutanix-rag
```

---

## MCP Tool Config (`openclaw.json`)

Registered in `~/.openclaw/openclaw.json` under `mcp.servers`:

```json
{
  "mcp": {
    "servers": {
      "rag-mcp-server": {
        "url": "http://127.0.0.1:8001/sse",
        "transport": "sse"
      },
      "gateway-mcp": {
        "url": "http://127.0.0.1:8010/sse",
        "transport": "sse",
        "description": "NX Gateway - enforces RAG->Slack->Web waterfall"
      },
      "sam-gateway": {
        "url": "http://127.0.0.1:8011/sse",
        "transport": "sse",
        "description": "Sam Gateway - enforces RAG->Slack->Web waterfall, sam identity"
      }
    }
  }
}
```

---

## Log Files

```
/tmp/nx_gateway_out.log  (NX_Shield gateway stdout)
/tmp/nx_gateway_err.log  (NX_Shield gateway stderr)
/tmp/sam_gateway_out.log  (Sam gateway stdout)
/tmp/sam_gateway_err.log  (Sam gateway stderr)
~/.openclaw/logs/mcp-nutanix-rag-sam.log  (old mcp_server.py)
```

---

## Database Paths

```
~/.openclaw/memory/lancedb-pro/nutanix_rag_v3_dedup.lance/
~/.openclaw/memory/kuzu-pro/nutanix_graph_v3/
~/.openclaw/workspace/rag/nutanix/  (ripgrep source docs)
```

---

## Rate Limiting Internals

The `_check_and_increment()` function in `nx_gateway_mcp.py` uses session file mtime to detect when a new query turn starts (compaction creates a new session file). Call counts reset automatically on session turnover.

If `MAX_CALLS_EXCEEDED` is returned, the agent must compile its answer from results already received — no further `master_search` calls are allowed in that turn.

---

## Changelog

### 2026-05-13
- **Full rewrite** — docs were reverted to old architecture
- Replaced `mcp_server.py` architecture with current `nx_gateway_mcp.py` setup
- Updated port assignments: 8001 (old/deprecated) → 8010 (NX_Shield) + 8011 (Sam)
- Updated tool names: `rag-mcp-server__query_nutanix_docs` → `sam-gateway__master_search` / `gateway-mcp__master_search`
- Updated rerank_top: Sam 50→5, NX_Shield 30→5
- Added `gateway_config.json` per-agent rate limit documentation
- Clarified Sam uses MCP (not direct script call) — this was previously outdated

### 2026-05-12
- Updated LanceDB table name: `nutanix_rag_v3` → `nutanix_rag_v3_dedup`
- Added Kuzu graph DB integration for entity-based boosting
- Updated row count: ~130K → ~85K (deduplicated)
- Added Graph Boost section explaining entity matching with Kuzu

### 2026-05-05
- Initial MCP server setup documentation (old `mcp_server.py` — now superseded)
