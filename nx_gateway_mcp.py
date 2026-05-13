#!/usr/bin/env python3
"""
nx_gateway_mcp.py — Ultra-Thin SSE Bridge for NX_Shield
Receives HTTP/SSE from OpenClaw, calls nutanix_rag_search.py, returns TextContent.

NO FALLBACK LOGIC LIVES HERE — all waterfall logic is in nutanix_rag_search.py.
"""
import sys
import asyncio
import subprocess
from pathlib import Path

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
                "Runs RAG + Ripgrep in parallel, then Slack, then Web — all handled by nutanix_rag_search.py."
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
