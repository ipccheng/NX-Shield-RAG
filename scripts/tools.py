#!/usr/bin/env python3
"""
Unified Search Worker for Sam.
Implements the "Short-Circuit Waterfall" pattern: RAG -> Grep -> Slack.
LLM calls `master_search` once. The script returns the first successful tier of data.
"""

import json
import subprocess
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SOURCE_ROOT = Path.home() / ".openclaw/workspace/rag/nutanix"
SLACK_CACHE = Path.home() / ".local/slk/token-cache.json"
RAG_SCRIPT  = Path.home() / ".openclaw/workspace/skills/nutanix-rag-search/scripts/nutanix_rag_search.py"

# ── 1. RAG Search (Tier 1) ────────────────────────────────────────────────────
def rag_search(query: str, top_k: int = 5) -> dict:
    """Call Sam's RAG search script directly."""
    try:
        result = subprocess.run(
            ["python3", str(RAG_SCRIPT), query],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return {"error": result.stderr or "script failed", "results": [], "count": 0}
        import io, re
        output = result.stdout
        # Parse ranked results from the script's plain-text output
        # Format: [N] body_text  or  **KB-XXXX** line
        results = []
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\[(\d+)\]\s+(.{0,300})", line)
            if m:
                results.append({"rank": int(m.group(1)), "body": m.group(2).strip()})
            elif "KB-" in line and line.startswith("**"):
                results.append({"rank": len(results) + 1, "body": line[:300]})
            elif results:  # continuation of previous result
                results[-1]["body"] += " " + line[:300]
        return {"results": results[:top_k], "count": len(results)}
    except subprocess.TimeoutExpired:
        return {"error": "RAG script timed out", "results": [], "count": 0}
    except Exception as e:
        return {"error": str(e), "results": [], "count": 0}

# ── 2. Ripgrep (Tier 2) ───────────────────────────────────────────────────────
def code_grep(search_term: str, max_matches: int = 20, context_lines: int = 2) -> dict:
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
        return {"error": "grep timed out", "matches": [], "count": 0}
    except FileNotFoundError:
        return {"error": "rg not in PATH", "matches": [], "count": 0}

    matches = []
    for line in result.stdout.splitlines():
        if not line.strip(): continue
        try:
            obj = json.loads(line)
            if obj.get("type") == "match":
                data = obj["data"]
                matches.append({
                    "path": str(Path(data["path"]["text"]).relative_to(Path.home())),
                    "text": data["lines"]["text"].strip()[:200]
                })
        except Exception:
            continue
    return {"matches": matches, "count": len(matches)}

# ── 3. Slack (Tier 3) ─────────────────────────────────────────────────────────
def slack_lookup(query: str, limit: int = 5) -> dict:
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
            auth = subprocess.run(["slk", "auth"], capture_output=True, text=True, timeout=30)
            if auth.returncode != 0: return {"error": "Auth failed", "results": [], "count": 0}
        except Exception:
            return {"error": "slk command failed", "results": [], "count": 0}

    try:
        search = subprocess.run(["slk", "search", query, str(limit)], capture_output=True, text=True, timeout=60)
        if search.returncode != 0: return {"error": "Search failed", "results": [], "count": 0}

        parsed = [msg.split("] ", 1)[1][:300] for msg in search.stdout.splitlines()[1:] if "] " in msg]
        return {"results": parsed, "count": len(parsed)}
    except Exception as e:
        return {"error": str(e), "results": [], "count": 0}

# ── 👑 The Master Waterfall ───────────────────────────────────────────────────
def master_search(query: str) -> dict:
    """
    Executes the short-circuit waterfall.
    Returns the first tier that has > 0 results.
    """
    # Tier 1: Official Documentation
    rag_data = rag_search(query)
    if rag_data.get("count", 0) > 0:
        return {"tier_used": "RAG_DOCS", "query": query, "data": rag_data}

    # Tier 2: Raw Source / API Files
    grep_data = code_grep(query)
    if grep_data.get("count", 0) > 0:
        return {"tier_used": "RIPGREP_SOURCE", "query": query, "data": grep_data}

    # Tier 3: Tribal Knowledge
    slack_data = slack_lookup(query)
    if slack_data.get("count", 0) > 0:
        return {"tier_used": "SLACK_HISTORY", "query": query, "data": slack_data}

    # Complete Failure
    return {
        "tier_used": "NONE",
        "query": query,
        "data": {"error": "All 3 search tiers returned 0 results. Try a different keyword."}
    }

# ── CLI Entrypoint ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: tools.py [master|rag|grep|slack] <query>")
        sys.exit(1)

    action, query = sys.argv[1], sys.argv[2]

    if action == "master":
        result = master_search(query)
    elif action == "rag":
        result = rag_search(query)
    elif action == "grep":
        result = code_grep(query)
    elif action == "slack":
        result = slack_lookup(query)
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, ensure_ascii=False))
