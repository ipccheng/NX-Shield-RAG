#!/usr/bin/env python3
"""
nx_gateway_mcp.py — Ultra-Thin SSE Bridge for NX_Shield
Receives HTTP/SSE from OpenClaw, calls nutanix_rag_search.py, returns TextContent.

NO FALLBACK LOGIC LIVES HERE — all waterfall logic is in nutanix_rag_search.py.

Per-agent max_calls:
  NX_Shield : 2
  Sam       : 3
  default   : 1
"""
import json
import os
import sys
import asyncio
import subprocess
import threading
from pathlib import Path
from collections import defaultdict

# ── Build session → agent map from session files ──────────────────────────
_SESSION_TO_AGENT: dict[str, str] = {}

def _load_session_map():
    global _SESSION_TO_AGENT
    agents_dir = Path.home() / ".openclaw" / "agents"
    for agent in (agents_dir).iterdir() if agents_dir.is_dir() else []:
        sess_dir = agent / "sessions"
        if sess_dir.is_dir():
            for f in sess_dir.iterdir():
                name = f.name
                if name.endswith(".jsonl") and not name.startswith("."):
                    sid = name.replace(".jsonl", "")
                    _SESSION_TO_AGENT[sid] = agent.name
                elif name.endswith(".trajectory.jsonl") and not name.startswith("."):
                    sid = name.replace(".trajectory.jsonl", "")
                    _SESSION_TO_AGENT[sid] = agent.name

_load_session_map()

# ── Load config ───────────────────────────────────────────────────────────
_GW_CONFIG_PATH = Path.home() / ".openclaw/workspace/scripts/gateway_config.json"

def _load_config():
    try:
        with open(_GW_CONFIG_PATH) as f:
            return json.load(f)
    except Exception as e:
        print(f"[gateway] WARNING: could not load {_GW_CONFIG_PATH}: {e}", file=sys.stderr)
        return {}

_cfg = _load_config()
_MAX_CALLS: dict = _cfg.get("max_calls_per_session", {
    "nutanix_shield": 2,
    "sam":            3,
    "default":        1,
})

# Per-session call counter (resets when session file mtime advances = new user message written)
import os
_call_lock = threading.Lock()
_call_counts: dict[str, int] = defaultdict(int)
_last_mtime: dict[str, float] = {}  # session_id -> last known mtime

def _get_max_calls(session_id: str) -> int:
    agent = _SESSION_TO_AGENT.get(session_id, "default")
    return _MAX_CALLS.get(agent, _MAX_CALLS.get("default", 1))

def _session_mtime(session_id: str) -> float:
    """Return mtime of the session's .jsonl file, or 0 if not found."""
    agents_dir = Path.home() / ".openclaw" / "agents"
    for agent_dir in agents_dir.iterdir() if agents_dir.is_dir() else []:
        sess_file = agent_dir / "sessions" / f"{session_id}.jsonl"
        if sess_file.is_file():
            return sess_file.stat().st_mtime
    return 0.0

def _check_and_increment(session_id: str, max_calls: int) -> bool:
    """
    Returns True if call is allowed, False if limit exceeded.
    Resets counter when the session file's mtime has advanced (new data written = new user message).
    """
    with _call_lock:
        current_mtime = _session_mtime(session_id)
        last = _last_mtime.get(session_id, 0.0)
        if session_id not in _last_mtime:
            # First time seeing this session — reset counter (new conversation)
            _call_counts[session_id] = 0
        elif current_mtime > last:
            # Session file grew since last call — user message was written → new turn
            _call_counts[session_id] = 0
        _last_mtime[session_id] = current_mtime
        _call_counts[session_id] += 1
        return _call_counts[session_id] <= max_calls

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport

# Configuration
PYTHON_BIN = "/opt/homebrew/bin/python3"
RAG_SCRIPT = Path.home() / ".openclaw/workspace/scripts/nutanix_rag_search.py"

server = Server("nx-gateway-mcp")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="master_search",
            description=(
                "The mandatory master search tool for Nutanix queries. "
                "Runs RAG + Ripgrep in parallel, then Slack, then Web — all handled by nutanix_rag_search.py. "
                "Enforced per-session call limits: NX_Shield=2, Sam=3."
            ),
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "master_search":
        raise ValueError(f"Unknown tool: {name}")

    # Enforce per-session call limit — resets when session file grows (new user message written)
    session_id = getattr(server, '_session_id', 'default')
    max_calls = _get_max_calls(session_id)
    if not _check_and_increment(session_id, max_calls):
        agent = _SESSION_TO_AGENT.get(session_id, "unknown")
        return [TextContent(
            type="text",
            text=f"[ERROR: MAX_CALLS_EXCEEDED] Agent '{agent}' is limited to {max_calls} master_search call(s) per query turn. "
                 "Compile your answer from the results already received. Do not call master_search again."
        )]

    query = arguments.get("query")
    if not query:
        raise ValueError("Missing required argument: query")

    try:
        # asyncio.to_thread prevents the subprocess from blocking the Starlette event loop
        proc = await asyncio.to_thread(
            subprocess.run,
            [PYTHON_BIN, str(RAG_SCRIPT), "--rerank-top", "5", "--identity", "nx_shield", query],
            capture_output=True, text=True, timeout=90
        )

        output = proc.stdout.strip()
        if not output:
            output = proc.stderr.strip() or "[ERROR] Backend returned no output."

        return [TextContent(type="text", text=output)]

    except Exception as e:
        print(f"Gateway execution failed: {e}", file=sys.stderr)
        return [TextContent(type="text", text=f"[ERROR] Gateway execution failed: {e}")]


# --- ASGI Setup ---
sse = SseServerTransport("/messages/")


async def endpoint_sse_raw(scope, receive, send):
    async with sse.connect_sse(scope, receive, send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def endpoint_messages_raw(scope, receive, send):
    # Extract and store session_id so handle_call_tool can enforce per-session limits
    import urllib.parse
    qs = urllib.parse.parse_qs(scope.get("query_string", b"").decode())
    server._session_id = qs.get("session_id", ["default"])[0]
    await sse.handle_post_message(scope, receive, send)


# --- ASGI Setup ---
sse = SseServerTransport("/messages/")


async def endpoint_sse_raw(scope, receive, send):
    async with sse.connect_sse(scope, receive, send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def endpoint_messages_raw(scope, receive, send):
    await sse.handle_post_message(scope, receive, send)


class _ASGIEndpointWrapper:
    def __init__(self, fn):
        self.fn = fn

    async def __call__(self, scope, receive, send):
        await self.fn(scope, receive, send)


app = Starlette(
    routes=[
        Route("/sse", endpoint=_ASGIEndpointWrapper(endpoint_sse_raw)),
        Route("/messages/", endpoint=_ASGIEndpointWrapper(endpoint_messages_raw), methods=["POST"])
    ]
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
