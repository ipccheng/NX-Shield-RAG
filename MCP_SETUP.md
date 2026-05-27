# MCP Server Setup — Nutanix RAG Search

> **Last updated:** 2026-05-27
> **Status:** Active — Hermes MCP profile endpoints with LanceDB-centered RAG search

---

## Overview

Hermes profiles expose the Nutanix RAG search pipeline through MCP. Sam/default and NX_Shield use separate RAG service endpoints so each profile can be verified and restarted independently, while both expose the canonical MCP tool name:

```text
hermes_master_search
```

Storage sizing is handled by a separate calculator MCP service. For capacity/BOM questions, the answer path is calculator-first; RAG provides supporting source/BOM context.

---

## Architecture

```text
Hermes profile: Sam/default
└── MCP server: nutanix-rag-search
    └── tool: hermes_master_search
        └── RAG service endpoint → universal_gateway_mcp.py
            └── spawns: nutanix_rag_search.py
                ├── LanceDB hybrid retrieval
                ├── Kuzu GraphContext advisory signal
                ├── exact local keyword matches
                ├── Evidence Ledger / answer_rule output
                └── optional fallback search when confidence is low

Hermes profile: NX_Shield
└── MCP server: nutanix-rag-search
    └── tool: hermes_master_search
        └── dedicated NX_Shield RAG service endpoint
            └── same active answer path

Shared storage calculator MCP
└── tools: storage_calc_forward, storage_calc_reverse, model/config helpers
```

---

## Design Decisions

### Why separate RAG service endpoints?

1. **Profile isolation** — Sam/default and NX_Shield can be tested and restarted independently.
2. **Operational rollback** — each LaunchAgent/service can keep its own backup and environment flags.
3. **Endpoint-locality clarity** — profile MCP discovery can pass while a dedicated service still points to stale backend settings; each endpoint must be directly canaried.
4. **Answer-path parity** — both endpoints should emit Evidence Ledger, `answer_rule:` guardrails, and calculator-first sizing behavior.

### Why `hermes_master_search`?

Hermes native MCP prefixes the server name around the tool name. The underlying tool is intentionally named `hermes_master_search` so all profiles expose a clear, consistent Nutanix RAG search tool.

### NX_Shield access stance

NX_Shield currently uses owner-approved full-docs RAG access for NDA-covered users. Do not infer a public-only external policy from old `access_level='public'` documentation. If the audience/policy changes later, rerun canaries that prove internal/confidential source families are excluded for that profile.

---

## Conceptual Port Assignments

| Service role | Tool | Endpoint role | Notes |
|---|---|---|---|
| Sam/default RAG | `hermes_master_search` | primary RAG search service | active LanceDB path |
| NX_Shield RAG | `hermes_master_search` | dedicated NX_Shield RAG service | active LanceDB path and separately canaried |
| Storage calculator | `storage_calc_*` tools | shared calculator service | calculator-first sizing/BOM math |

Avoid publishing private host/IP/token details in this public documentation. Use local profile config and LaunchAgent records as the operational source of truth.

---

## MCP Tool Names

Hermes profile config should discover:

| MCP server | Tool Name | Purpose |
|---|---|---|
| `nutanix-rag-search` | `hermes_master_search` | RAG + ripgrep + optional fallback search |
| `nutanix-storage-calc` | `storage_calc_forward` / `storage_calc_reverse` / helpers | deterministic Nutanix storage sizing |

Verification pattern:

```bash
hermes --profile sam mcp test nutanix-rag-search
hermes --profile sam mcp test nutanix-storage-calc
hermes --profile nx-shield mcp test nutanix-rag-search
hermes --profile nx-shield mcp test nutanix-storage-calc
```

Direct endpoint canaries should also check for Evidence Ledger, `answer_rule:` markers, calculator-first storage sizing, and absence of stale fallback markers.

---

## Gateway Config (`gateway_config.json`)

Located at `~/.openclaw/workspace/scripts/gateway_config.json`. Controls per-agent rate limits:

```json
{
  "max_calls_per_session": {
    "nutanix_shield": 5,
    "sam": 5,
    "neo": 5,
    "main": 5,
    "default": 5
  }
}
```

All agents are configured for 5 calls per query turn.

---

## Launchd Services

Check running MCP servers:
```bash
lsof -i :8010 -i :8011 | grep LISTEN
```

| Service Name | Script | Port | Identity | Config File |
|---|---|---|---|---|
| `com.samai.mcp-gateway-nx-shield` | `universal_gateway_mcp.py` | 8010 | `nutanix_shield` | `com.samai.mcp-gateway-nx-shield.plist` |
| `com.samai.mcp-gateway-sam` | `universal_gateway_mcp.py` | 8011 | `sam` | `com.samai.mcp-gateway-sam.plist` |

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

---

## MCP Tool Config (`openclaw.json`)

Registered in `~/.openclaw/openclaw.json` under `mcp.servers`:

```json
{
  "mcp": {
    "servers": {
      "web-search-filtered": {
        "url": "http://127.0.0.1:8003/sse",
        "transport": "sse"
      },
      "storage-calc-mcp-server": {
        "url": "http://127.0.0.1:8002/sse",
        "transport": "sse"
      },
      "slack-search-mcp": {
        "url": "http://127.0.0.1:8005/sse",
        "description": "Slack search for NX_Shield"
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

The `_check_and_increment()` function in `universal_gateway_mcp.py` uses session file mtime to detect when a new query turn starts (compaction creates a new session file). Call counts reset automatically on session turnover.

If `MAX_CALLS_EXCEEDED` is returned, the agent must compile its answer from results already received — no further `master_search` calls are allowed in that turn.

---

## Changelog

### 2026-05-16
- **Script name corrected:** `nx_gateway_mcp.py` → `universal_gateway_mcp.py` throughout
- Updated `lsof` check command to only show active ports 8010/8011
- Updated `gateway_config.json` rates to 5 calls/turn for all agents
- Removed stale references to old `mcp_server.py` and `rag-mcp-server`

### 2026-05-13
- Full rewrite — docs were reverted to old architecture
- Replaced `mcp_server.py` architecture with current `nx_gateway_mcp.py` setup
- Updated port assignments: 8001 (old/deprecated) → 8010 (NX_Shield) + 8011 (Sam)
- Updated tool names: `rag-mcp-server__query_nutanix_docs` → `sam-gateway__master_search` / `gateway-mcp__master_search`
- Updated rerank_top: Sam 50→5, NX_Shield 30→5
- Added `gateway_config.json` per-agent rate limit documentation
- Clarified Sam uses MCP (not direct script call) — this was previously outdated

### 2026-05-12
- Updated LanceDB table name: `nutanix_rag_v3` → `nutanix_rag_v3_dedup`
- Added Kuzu graph DB integration for entity-based boosting
- Documented deduplicated LanceDB lineage without static row counts
- Added Graph Boost section explaining entity matching with Kuzu

### 2026-05-05
- Initial MCP server setup documentation (old `mcp_server.py` — now superseded)
