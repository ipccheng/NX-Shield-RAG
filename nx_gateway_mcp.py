#!/usr/bin/env python3
"""
NX Gateway MCP Server
Strictly enforces the RAG -> Ripgrep -> Slack -> Web waterfall.
"""
import sys
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport

# Configuration
PYTHON_BIN = "/opt/homebrew/bin/python3"
RAG_SCRIPT = Path.home() / ".openclaw/workspace/scripts/nutanix_rag_search.py"
RAG_DOCS_DIR = Path.home() / ".openclaw/workspace/rag/nutanix"
ALLOWED_DOMAINS_FILE = Path.home() / ".openclaw/workspace/scripts/allowed_domains.json"
SEARXNG_URL = "http://127.0.0.1:8888/search"

server = Server("nx-gateway-mcp")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="master_search",
            description="The mandatory master search tool for Nutanix queries. Automatically searches Internal RAG Docs, falling back to Slack and Web Search if needed.",
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

    # ==========================================
    # TIER 1: RAG SEARCH (Mandatory First Step)
    # ==========================================
    try:
        rag_proc = subprocess.run(
            [PYTHON_BIN, str(RAG_SCRIPT), "--rerank-top", "5", "--identity", "nx_shield", query],
            capture_output=True, text=True, timeout=60
        )
        rag_out = rag_proc.stdout.strip()

        # If RAG returned valid data and didn't trigger its own "No results found" logic
        if rag_out and "No results found" not in rag_out and "error" not in rag_out.lower():
            return [TextContent(type="text", text=f"[SOURCE: Tier 1 - RAG Internal Docs]\n\n{rag_out}")]
    except Exception as e:
        print(f"RAG Tier Failed: {e}", file=sys.stderr)

    # ==========================================
    # TIER 1.5: SOURCE FILE RIPGREP (Fallback 1)
    # ==========================================
    if RAG_DOCS_DIR.exists():
        try:
            rg_proc = subprocess.run(
                ["/opt/homebrew/bin/rg", "-F", "-n", "-i", "--", query, str(RAG_DOCS_DIR)],
                capture_output=True, text=True, timeout=15
            )
            if rg_proc.returncode == 0 and rg_proc.stdout.strip():
                lines = rg_proc.stdout.strip().split("\n")[:15]
                # Truncate each line to 250 chars to keep context window manageable
                trimmed = [line[:250] + "..." if len(line) > 250 else line for line in lines]
                formatted = "\n".join(trimmed)
                return [TextContent(type="text", text=f"[SOURCE: Tier 1.5 - Local File Ripgrep]\n\n{formatted}")]
        except Exception as e:
            print(f"Ripgrep Tier Failed: {e}", file=sys.stderr)

    # ==========================================
    # TIER 2: SLACK SEARCH (Fallback 2)
    # ==========================================
    try:
        # Verify Auth first to prevent silent crashes
        auth = subprocess.run(["slk", "auth"], capture_output=True, text=True, timeout=10)
        if auth.returncode == 0:
            slack_proc = subprocess.run(
                ["slk", "search", query, "10"],
                capture_output=True, text=True, timeout=30
            )

            if slack_proc.returncode == 0:
                lines = slack_proc.stdout.splitlines()[1:]  # Skip header
                results = [line.split("] ", 1)[1][:300] for line in lines[:10] if "] " in line]

                if results:
                    formatted = "\n".join(f"[{i+1}] {r}" for i, r in enumerate(results))
                    return [TextContent(type="text", text=f"[SOURCE: Tier 2 - Slack History Fallback]\n\n{formatted}")]
    except Exception as e:
        print(f"Slack Tier Failed: {e}", file=sys.stderr)

    # ==========================================
    # TIER 3: WEB SEARCH (Last Resort)
    # ==========================================
    try:
        req = urllib.request.Request(
            f"{SEARXNG_URL}?q={urllib.parse.quote(query)}&format=json&engines=google,bing,duckduckgo&qtime=0",
            headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            web_results = data.get("results", [])

        # Load Allowed Domains Filter
        allowed_domains = []
        if ALLOWED_DOMAINS_FILE.exists():
            with open(ALLOWED_DOMAINS_FILE) as f:
                allowed_domains = json.load(f).get("domains", [])

        # Filter and format results
        filtered = []
        for r in web_results[:10]:
            url = r.get("url", "").lower()
            if not allowed_domains or any(d.lower() in url for d in allowed_domains):
                filtered.append(
                    f"Title: {r.get('title')}\nURL: {r.get('url')}\nSnippet: {r.get('content', '')}\n"
                )

        if filtered:
            formatted = "\n---\n".join(filtered)
            return [TextContent(type="text", text=f"[SOURCE: Tier 3 - Web Search Fallback]\n\n{formatted}")]
    except Exception as e:
        print(f"Web Tier Failed: {e}", file=sys.stderr)

    # ==========================================
    # ALL TIERS FAILED
    # ==========================================
    return [TextContent(
        type="text",
        text="[ERROR: ALL TIERS FAILED] No results found across RAG, Ripgrep, Slack, or Web. Please tell the user you do not have the information."
    )]


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
