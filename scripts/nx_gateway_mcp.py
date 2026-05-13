#!/usr/bin/env python3
"""
universal_gateway_mcp.py — Ultra-Thin SSE Bridge for OpenClaw Agents

Single script, multiple instances via launchd:
  NX_Shield: python3 nx_gateway_mcp.py --port 8010 --identity nutanix_shield
  Sam:       python3 nx_gateway_mcp.py --port 8011 --identity sam
"""
import json
import sys
import asyncio
import subprocess
import threading
import urllib.parse
from pathlib import Path
from collections import defaultdict
import argparse

# ── MCP imports (must be before @server decorators) ─────────────────────────
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route

# ── Runtime args (set at startup) ─────────────────────────────────────────────
_PARSER = argparse.ArgumentParser(description="Universal MCP Gateway")
_PARSER.add_argument("--port", type=int, default=8010)
_PARSER.add_argument("--identity", type=str, required=True)
_PARSER.add_argument("--rerank-top", type=int, default=5)
_ARGS = _PARSER.parse_known_args()[0]

AGENT_IDENTITY: str = _ARGS.identity
AGENT_PORT: int = _ARGS.port
RERANK_TOP: int = _ARGS.rerank_top

PYTHON_BIN = "/opt/homebrew/bin/python3"
RAG_SCRIPT = Path.home() / ".openclaw/workspace/scripts/nutanix_rag_search.py"
GW_CONFIG  = Path.home() / ".openclaw/workspace/scripts/gateway_config.json"

# ── Server instance (created before decorators) ────────────────────────────────
server = Server("universal-gateway-mcp")

# ── Config loader ──────────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        with open(GW_CONFIG) as f:
            return json.load(f)
    except Exception:
        return {}

_CFG = _load_config()

# ── Session → agent map (built at startup) ─────────────────────────────────────
_SESSION_TO_AGENT: dict = {}

def _build_session_map() -> None:
    global _SESSION_TO_AGENT
    agents_dir = Path.home() / ".openclaw" / "agents"
    for agent_dir in agents_dir.iterdir() if agents_dir.is_dir() else []:
        sess_dir = agent_dir / "sessions"
        if sess_dir.is_dir():
            for f in sess_dir.iterdir():
                if f.suffix == ".jsonl" and not f.name.startswith("."):
                    _SESSION_TO_AGENT[f.stem] = agent_dir.name

_build_session_map()

# ── Per-session call counter (mtime-based reset) ─────────────────────────────
_call_lock   = threading.Lock()
_call_counts: dict = defaultdict(int)
_last_mtime: dict = {}

def _session_mtime(session_id: str) -> float:
    agents_dir = Path.home() / ".openclaw" / "agents"
    for agent_dir in agents_dir.iterdir() if agents_dir.is_dir() else []:
        sess_file = agent_dir / "sessions" / f"{session_id}.jsonl"
        if sess_file.is_file():
            return sess_file.stat().st_mtime
    return 0.0

def _get_max_calls(session_id: str) -> int:
    agent   = _SESSION_TO_AGENT.get(session_id, "default")
    max_map = _CFG.get("max_calls_per_session", {})
    return max_map.get(agent, max_map.get("default", 1))

def _check_and_increment(session_id: str) -> bool:
    with _call_lock:
        current_mtime = _session_mtime(session_id)
        last = _last_mtime.get(session_id, 0.0)
        if session_id not in _last_mtime:
            _call_counts[session_id] = 0
        elif current_mtime > last:
            _call_counts[session_id] = 0
        _last_mtime[session_id] = current_mtime
        agent    = _SESSION_TO_AGENT.get(session_id, "default")
        max_calls = _get_max_calls(session_id)
        _call_counts[session_id] += 1
        return _call_counts[session_id] <= max_calls

# ── Tool definition ────────────────────────────────────────────────────────────
@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="master_search",
            description=(
                "The mandatory master search tool for Nutanix queries. "
                "Runs RAG + Ripgrep in parallel, then Slack, then Web — all in nutanix_rag_search.py. "
                f"Identity: {AGENT_IDENTITY}."
            ),
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        )
    ]

# ── Tool handler ───────────────────────────────────────────────────────────────
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "master_search":
        raise ValueError(f"Unknown tool: {name}")

    session_id = getattr(server, "_session_id", "default")
    if not _check_and_increment(session_id):
        agent     = _SESSION_TO_AGENT.get(session_id, "unknown")
        max_calls = _get_max_calls(session_id)
        return [TextContent(
            type="text",
            text=f"[ERROR: MAX_CALLS_EXCEEDED] Agent '{agent}' is limited to {max_calls} master_search call(s) per query turn. "
                 "Compile your answer from the results already received. Do not call master_search again."
        )]

    query = arguments.get("query")
    if not query:
        raise ValueError("Missing required argument: query")

    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [PYTHON_BIN, str(RAG_SCRIPT),
             "--rerank-top", str(RERANK_TOP),
             "--identity",   AGENT_IDENTITY,
             query],
            capture_output=True, text=True, timeout=90
        )
        output = proc.stdout.strip()
        if not output:
            output = proc.stderr.strip() or "[ERROR] Backend returned no output."
        return [TextContent(type="text", text=output)]
    except Exception as e:
        print(f"Gateway execution failed: {e}", file=sys.stderr)
        return [TextContent(type="text", text=f"[ERROR] Gateway execution failed: {e}")]

# ── ASGI Setup ────────────────────────────────────────────────────────────────
sse = SseServerTransport("/messages/")

async def endpoint_sse_raw(scope, receive, send):
    async with sse.connect_sse(scope, receive, send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())

async def endpoint_messages_raw(scope, receive, send):
    qs = urllib.parse.parse_qs(scope.get("query_string", b"").decode())
    server._session_id = qs.get("session_id", ["default"])[0]
    await sse.handle_post_message(scope, receive, send)

class _ASGIEndpointWrapper:
    def __init__(self, fn): self.fn = fn
    async def __call__(self, scope, receive, send):
        await self.fn(scope, receive, send)

app = Starlette(
    routes=[
        Route("/sse",      endpoint=_ASGIEndpointWrapper(endpoint_sse_raw)),
        Route("/messages/", endpoint=_ASGIEndpointWrapper(endpoint_messages_raw), methods=["POST"])
    ]
)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"[gateway] Starting — identity={AGENT_IDENTITY}, port={AGENT_PORT}, rerank_top={RERANK_TOP}")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
