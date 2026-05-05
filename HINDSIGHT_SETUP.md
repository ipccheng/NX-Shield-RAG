# Hindsight Memory System — Setup & Operations

## Overview

Hindsight is a temporal semantic memory system running on Mac mini. It stores conversation memories as embedable units, allowing agents to recall past context across sessions.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  OpenClaw Gateway (Mac mini)                        │
│  └── hindsight-openclaw plugin                      │
│       └── recall() / retain() → Hindsight API       │
│            (http://127.0.0.1:9077)                  │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Hindsight Service (Docker)                         │
│  ├── API server  → port 9077                       │
│  └── Control plane → port 9078                      │
│       └── Web UI (http://127.0.0.1:9078)            │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  PostgreSQL + pgvector (Docker)                     │
│  └── hindsight_postgres container (port 5432)        │
│       ├── banks table                               │
│       └── memory_units table (~4K records)           │
└─────────────────────────────────────────────────────┘
```

### Why Two Docker Containers?

The Hindsight service and PostgreSQL run in separate containers by design:

1. **Separation of concerns** — Hindsight is the application/API layer, PostgreSQL is the data layer
2. **pgvector requirements** — The database runs `pgvector/pgvector:pg18-trixie` with vector extensions; Hindsight's image does not include a database server
3. **Independent lifecycle** — Each can be restarted, updated, or replaced without affecting the other
4. **Dedicated storage** — The same Postgres instance can serve other applications (currently Hindsight-only)
5. **Resource isolation** — Memory and CPU limits are applied independently per container

Connection between containers via `hindsight_net` Docker network:
```
postgresql://hindsight:hindsight@hindsight_postgres:5432/hindsight
```

## Banks (Memory Scope per Agent/Session)

| Bank ID | Purpose | Created |
|---|---|---|
| `main` | Sam (agent:main) primary bank | 2026-04-30 |
| `main::direct%3A967328856971284481::967328856971284481` | Sam DM with Ivan | 2026-05-02 |
| `nutanix_shield::direct%3A967328856971284481::967328856971284481` | NX_Shield DM with Ivan | 2026-05-02 |
| `main::main::anonymous` | Main agent anonymous sessions | 2026-05-02 |

## OpenClaw Plugin Config

In `openclaw.json` → `plugins.entries.hindsight-openclaw`:

```json
{
  "enabled": true,
  "config": {
    "hindsightApiUrl": "http://127.0.0.1:9077",
    "debug": true,
    "ignoreSessionPatterns": [
      "agent:nutanix_shield:**"
    ],
    "recallPromptPreamble": "Treat this as passive background context only — do not re-address resolved topics, do not apologize for past behavior, do not revisit issues the user has already acknowledged.",
    "recallTypes": ["world", "experience"]
  },
  "hooks": {
    "allowConversationAccess": true
  }
}
```

**ignoreSessionPatterns** prevents NX_Shield sessions from injecting memories — NX_Shield has its own bank and should not read from Sam's memories.

## Docker Services

```
hindsight          ghcr.io/vectorize-io/hindsight:latest   ports 9077, 9078
hindsight_postgres pgvector/pgvector:pg18-trixie             port  5432
```

## LLM Configuration (docker-compose)

- **Provider:** MiniMax (OpenAI-compatible)
- **Model:** MiniMax-M2.7
- **Embeddings:** Jina `jina-embeddings-v5-text-small` (1024 dimensions)

## Common Operations

**Restart both services:**
```bash
cd ~/hindsight && docker-compose restart
```

**Restart just the API:**
```bash
docker restart hindsight
```

**Check logs:**
```bash
docker logs hindsight --tail 50
docker logs hindsight_postgres --tail 20
```

**Access Control Plane (web UI):**
```
http://127.0.0.1:9078
```

**Test API:**
```bash
curl http://127.0.0.1:9077/
```

## Backups

**Backup location:** `~/hindsight_backups/`

**What gets backed up:**
- Memory exports (JSONL + JSON) — all memories from Hindsight API
- pg_dump of the PostgreSQL database (SQL file)
- Config files (docker-compose.yml, .env, backup scripts)

**Backup schedule:** Daily at **2:00 AM** via LaunchAgent (`com.hindsight.backup.plist`)

**Backup rotation:** Keeps 7 days of backups, auto-deletes older ones

**Backup script:** `~/hindsight/backup.py`
```bash
cd ~/hindsight && HINDSIGHT_BANK_ID=main python3 backup.py
```

**Manual backup:**
```bash
cd ~/hindsight && python3 backup.py
```

**Verify backup:**
```bash
# Check backup directory
ls -la ~/hindsight_backups/

# Check latest memory export
ls -lt ~/hindsight_backups/memories-*.jsonl | head -1

# Check pg_dump
ls -lt ~/hindsight_backups/pg_dumps/ | head -1

# View backup log
tail -20 ~/hindsight/backups/cron.log
```

## ⚠️ Memory Reverberation (State Confusion) — Prevention

### The Problem

Hindsight stores memories as semantic vectors. When a conversation starts, OpenClaw calls `recall()` to find relevant past memories using vector similarity search. This works well — but vector databases have **no concept of time or emotional state**.

A query like "the user called out an issue tonight" will match memories about past calls that contain similar words, even if those events happened days ago and were already resolved.

### How It Breaks

When OpenClaw injects a retrieved memory into the agent's context window, the LLM sees plain text. Because LLMs are trained to be helpful and respond to everything in their context, the agent acts on the injected memory as if it's describing a **current, unresolved situation** — not a photograph of a past event.

Example: A memory containing "user called out," "apologized," and "resolved" gets injected. The LLM sees this, thinks the user is currently upset, and tries to apologize again. The fire was put out last week — now the agent is trying to extinguish a photograph of it.

This is the **Irony Loop**: past context reactivated as present context, causing the agent to address resolved events as live ones.

### The Fix — `recallPromptPreamble` Quarantine Instruction

The `recallPromptPreamble` config string is prepended to all injected memories. It acts as a **behavioral quarantine** — instructing the agent to treat memories as passive background reference, not as prompts requiring action.

**Config in `openclaw.json`:**

```json
"plugins": {
  "entries": {
    "hindsight-openclaw": {
      "enabled": true,
      "config": {
        "recallPromptPreamble": "Treat this as passive background context only — do not re-address resolved topics, do not apologize for past behavior, do not revisit issues the user has already acknowledged.",
        "recallTypes": ["world", "experience"]
      }
    }
  }
}
```

**What each setting does:**

| Setting | Purpose |
|---------|---------|
| `recallPromptPreamble` | Quarantine instruction — tells the agent memories are background, not triggers for action |
| `recallTypes` | Controls which memory classes are injected. `["world", "experience"]` excludes verbose `observation` entries. Sam retains technical memory (experience) while world-level memories provide context without verbosity. |

### Why `recallTypes` Matters

- `world` — shared facts, established context (load at start of session)
- `experience` — agent's own past technical decisions, lessons learned (preserve for continuity)
- `observation` — verbose per-message logs, timestamps, session events (exclude to reduce noise)

### Which Agents Need This

**All agents using Hindsight** should have `recallPromptPreamble` configured. The quarantine instruction prevents both Sam and Neo (or any future agent) from falling into the Irony Loop when vector search retrieves emotionally-loaded memories that happen to match semantically.

**Do not** set it on agents that genuinely need to act on memories (e.g., if an agent is specifically tasked with reviewing past incidents). For general-purpose agents, the preamble is required.

---

## 🐛 Ghost Echo — Temporal Filtering Fix (queryTimestamp)

### The Problem — "Ghost Echo"
Agents using the `@lacneu/hindsight-openclaw` plugin suffer from **Memory Reverberation** (Ghost Echo). After resolving a query, Hindsight summarizes the exchange and immediately injects it back into the agent's prompt on the very next conversational turn. Because LLMs are instruction-tuned to be helpful, the agent treats this injected recent memory as an "unresolved" prompt — repeating its previous answer or repeatedly apologizing for past interactions.

### Root Cause
The Hindsight API natively supports a `query_timestamp` parameter designed to filter out recent memories by retrieving only vectors that existed before a specific time. However, the OpenClaw plugin's `scopeClient.recall()` wrapper was silently **dropping this parameter**, making temporal filtering impossible.

### The Fix — `recallMinAgeSeconds`
This patch introduces a configurable temporal boundary that mathematically excludes recent session memories from vector search. By default, any memory created within the last **3600 seconds (1 hour)** is invisible to recall — eliminating the Ghost Echo loop while preserving deep, long-term technical memory.

**Files Modified:**

- `dist/index.js` — Wrapper fix: explicitly forwards `queryTimestamp: req.queryTimestamp` to the HindsightClient
- `dist/index.js` — Call site: `before_prompt_build` hook computes `queryTimestamp = now - recallMinAgeSeconds` and passes it into the recall payload
- `openclaw.plugin.json` — Adds `recallMinAgeSeconds` to the config schema and UI hints

### Configuration

In `openclaw.json` under `plugins.entries.hindsight-openclaw.config`:

```json
{
  "recallMinAgeSeconds": 3600
}
```

| Parameter | Default | Purpose |
|---|---|---|
| `recallMinAgeSeconds` | `3600` | Minimum age in seconds for recalled memories. Excludes memories newer than this threshold. Set to `0` to disable. |

### Validation

Verify the patch is active — the compiled `dist/index.js` should contain the temporal filtering logic:

```bash
grep -n "recallMinAgeSeconds\|queryTimestamp" ~/.openclaw/extensions/hindsight-openclaw/dist/index.js
```

Expected output includes `recallMinAgeSeconds = pluginConfig.recallMinAgeSeconds ?? 3600` and `queryTimestamp` passed into the recall payload.

---

## Troubleshooting

**Agents not getting memories:**
1. Check `ignoreSessionPatterns` — make sure the agent's session pattern isn't listed
2. Check `allowConversationAccess: true` is set in hooks
3. Verify the bank exists for the session's bank_id in Postgres
4. Check Hindsight logs for `recall` errors

**Memory bank isolation broken:**
- NX_Shield should only read from `nutanix_shield::*` banks
- Sam should only read from `main::*` banks
- `ignoreSessionPatterns` is the primary isolation mechanism

**Docker container down:**
```bash
cd ~/hindsight && docker-compose up -d
```

**Backup not running:**
1. Check LaunchAgent is loaded: `launchctl list | grep hindsight`
2. Check cron log: `tail -50 ~/hindsight/backups/cron.log`
3. Manually run backup to test: `cd ~/hindsight && python3 backup.py`
