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
    ]
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
