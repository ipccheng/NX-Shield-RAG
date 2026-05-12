#!/usr/bin/env python3
"""
Dedicated search tools for Sam — hardcoded, sandboxed functions.
LLM calls these directly via exec — never generates raw bash for searches.
The LLM decides WHICH tool to use; this script handles execution safely.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

# ── Config (hardcoded — LLM cannot change these) ──────────────────────────────
SOURCE_ROOT = Path.home() / ".openclaw/workspace/rag/nutanix"
SLACK_CACHE = Path.home() / ".local/slk/token-cache.json"
RAG_MCP_URL = "http://127.0.0.1:8004"  # Sam's local MCP server

# ── 1. RAG Search ─────────────────────────────────────────────────────────────
def rag_search(query: str, top_k: int = 5) -> dict:
    """
    Search Nutanix RAG via local MCP server JSON-RPC.
    Returns top_k results with source, doc_type, chunk_text, and scores.
    """
    import urllib.request

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "query_nutanix_docs",
            "arguments": {"query": query}
        },
        "id": 1
    }

    try:
        req = urllib.request.Request(
            f"{RAG_MCP_URL}/mcp",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)

        content = data.get("result", {}).get("content", [])
        results = []
        for block in content[:top_k]:
            text = block.get("text", "")
            lines = text.split("\n")
            parsed_successfully = False
            for line in lines:
                line = line.strip()
                if line.startswith(("1]", "2]", "3]", "4]", "5]", "6]", "7]", "8]", "9]")):
                    parts = line.split("}", 1)
                    if len(parts) == 2:
                        header, body = parts
                        header = header.replace("[", "").replace("]", "")
                        score_part = header.split("=")[-1] if "=" in header else ""
                        results.append({
                            "rank": len(results) + 1,
                            "score": score_part.strip(),
                            "body": body.strip()[:300]
                        })
                        parsed_successfully = True
                        break
                    else:
                        results.append({"rank": len(results) + 1, "body": line[:300]})
                        parsed_successfully = True
                elif line.startswith("**") and "KB-" in line:
                    results.append({"rank": len(results) + 1, "body": line[:300]})
                    parsed_successfully = True
            # FALLBACK: If string matching failed, give raw chunk
            if not parsed_successfully and text:
                results.append({"rank": len(results) + 1, "score": "unknown", "body": text[:300].strip()})
        return {"results": results[:top_k], "query": query, "count": len(results)}

    except Exception as e:
        return {"error": str(e), "results": [], "query": query}


# ── 2. Source File Grep ───────────────────────────────────────────────────────
def code_grep(search_term: str, max_matches: int = 50, context_lines: int = 2) -> dict:
    """
    Search source files using ripgrep — path LOCKED to SOURCE_ROOT.
    LLM passes ONLY the search term. Path and flags are hardcoded.
    """
    cmd = [
        "rg", "--json",
        "-m", str(max_matches),
        "-C", str(context_lines),
        search_term,
        str(SOURCE_ROOT),
        "--type", "md",
        "--type", "txt",
        "--type", "yaml",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {"error": "grep timed out after 30s", "matches": [], "term": search_term}
    except FileNotFoundError:
        return {"error": "ripgrep (rg) is not installed or not in PATH.", "matches": [], "term": search_term}

    matches = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if obj.get("type") == "match":
                data = obj["data"]
                # path at data.path.text, text at data.lines.text, line at data.line_number
                path_str = data["path"]["text"]
                text = data["lines"]["text"].strip()
                line_no = data.get("line_number", 0)
                matches.append({
                    "path": str(Path(path_str).relative_to(Path.home())),
                    "line": line_no,
                    "text": text[:200]
                })
        except (json.JSONDecodeError, KeyError, ValueError):
            continue

    return {"matches": matches, "count": len(matches), "term": search_term}


# ── 3. Slack Lookup ───────────────────────────────────────────────────────────
def slack_lookup(query: str, limit: int = 10) -> dict:
    """
    Search Slack via slk CLI — uses cached token+cookie (fast after warmup).
    Requires Slack desktop app open for auth extraction (first call after warmup).
    """
    # Check if cached auth exists and is recent (< 4 hrs)
    cache_valid = False
    if SLACK_CACHE.exists():
        try:
            with open(SLACK_CACHE) as f:
                cache = json.load(f)
            cache_valid = (time.time() - cache.get("ts", 0)) < 4 * 3600
        except Exception:
            pass

    if not cache_valid:
        try:
            auth_result = subprocess.run(
                ["slk", "auth"], capture_output=True, text=True, timeout=30
            )
            if auth_result.returncode != 0:
                return {"error": "Slack auth failed. Is the desktop app open?", "results": []}
        except FileNotFoundError:
            return {"error": "Slack CLI (slk) is not installed or not in PATH.", "results": []}
        except subprocess.TimeoutExpired:
            return {"error": "Slack auth command timed out.", "results": []}

    # Run search
    try:
        search_result = subprocess.run(
            ["slk", "search", query, str(limit)],
            capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        return {"error": "slk search timed out", "results": []}
    except FileNotFoundError:
        return {"error": "Slack CLI (slk) is not installed or not in PATH.", "results": []}

    if search_result.returncode != 0:
        return {"error": search_result.stderr or "Search failed", "results": []}

    # Parse output: group multi-line messages by timestamp header
    # Format: [date] #channel — user:
    #         message body (may span multiple lines until next [date] header)
    import re
    lines = search_result.stdout.splitlines()
    messages = []
    current_msg = None

    header_re = re.compile(r"^\[([^\]]+)\]\s+(#\S+|@\S+)\s+[\u2014-]\s+\S+")

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("Found"):
            continue
        header_match = header_re.match(line)
        if header_match:
            # Save previous message if any
            if current_msg:
                messages.append(current_msg)
            # Start new message
            timestamp, channel = header_match.groups()
            body_start = header_match.end()
            body = line[body_start:].strip()
            current_msg = {
                "channel": channel,
                "timestamp": timestamp,
                "text": body
            }
        elif current_msg:
            # Continuation of current message
            # Stop if we hit what looks like a new header
            if header_re.match(line.lstrip()):
                messages.append(current_msg)
                current_msg = None
            else:
                current_msg["text"] += " " + line

    if current_msg:
        messages.append(current_msg)

    parsed = []
    for msg in messages[:limit]:
        text = msg["text"][:300].strip()
        parsed.append(f"[{msg['timestamp']}] {msg['channel']}: {text}")

    return {"results": parsed, "count": len(parsed), "query": query}


# ── 4. Master Search (Short-Circuit Waterfall) ──────────────────────────────────
def master_search(query: str) -> dict:
    """
    Supervisor/Worker pattern: runs RAG → Grep → Slack in waterfall,
    returning on first non-empty result. Single tool call for the LLM.
    """
    # Step 1: Official docs (RAG)
    rag = rag_search(query)
    if rag.get("count", 0) > 0:
        return {"source": "rag", "query": query, **rag}

    # Step 2: Source files (Grep)
    grep = code_grep(query)
    if grep.get("count", 0) > 0:
        return {"source": "grep", "query": query, **grep}

    # Step 3: Slack (Tribal knowledge)
    slack = slack_lookup(query)
    if slack.get("count", 0) > 0:
        return {"source": "slack", "query": query, **slack}

    # All empty
    return {"source": "none", "query": query, "error": "No results from any source"}


# ── CLI entrypoint ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: tools.py [rag|grep|slack|master] <query>")
        sys.exit(1)

    action, query = sys.argv[1], sys.argv[2]

    if action == "rag":
        result = rag_search(query)
    elif action == "grep":
        result = code_grep(query)
    elif action == "slack":
        result = slack_lookup(query)
    elif action == "master":
        result = master_search(query)
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, ensure_ascii=False))
