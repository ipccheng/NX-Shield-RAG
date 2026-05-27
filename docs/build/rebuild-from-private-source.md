# Rebuild from Private Source

This document describes how the public docs and private source bundle fit together.

## What you need

1. This public repo: `ipccheng/NX-Shield-RAG`
2. Private source repo: `ipccheng/NX-Shield-RAG-src`
3. External backups for LanceDB/Kuzu/source documents
4. Secure credential vault for API keys, bot tokens, and OAuth credentials
5. A clean Hermes Agent installation

## What this public repo can rebuild

From this repo alone you can rebuild the **architecture and operating model**:

- retrieval design,
- ingestion contract,
- metadata model,
- evidence-ledger answer pattern,
- profile/MCP serving model,
- evaluation strategy,
- source-to-private-path map.

## What requires the private repo

The actual scripts and profile prompts are in the private source-recovery bundle:

```text
ipccheng/NX-Shield-RAG-src
├── rag/hermes-nutanix/                 # active RAG source/config skeleton
├── openclaw/workspace-scripts/         # legacy/runtime lineage
├── hermes/profiles/                    # sanitized profile prompts/config metadata
├── ops/launchagents/                   # service templates
├── reports/exchange/                   # milestone and canary records
└── tools/scan_source_safety.py         # source safety scanner
```

## What requires backup artifacts

Git should not hold large or sensitive runtime data. Restore these from backup artifacts:

- LanceDB stores,
- Kuzu databases,
- source-document corpus,
- Hindsight/Postgres dumps if used,
- session databases if needed for audit only.

## High-level rebuild sequence

1. Install Hermes Agent from upstream.
2. Clone this public design repo and the private source repo.
3. Copy private RAG source into the runtime root, normally `~/.hermes/rag/nutanix`.
4. Restore data stores from backups into the paths expected by config.
5. Recreate `.env`/secrets from secure vault only.
6. Verify Python/JSON/YAML syntax.
7. Start MCP services locally with private LaunchAgent templates or equivalent process manager.
8. Run retrieval canaries.
9. Run answer-path canaries through the actual agent profile.
10. Only then expose the profile through Discord/Telegram/etc.

## Rebuild checklist

- [ ] No secrets copied from Git.
- [ ] LanceDB opens and expected tables are visible.
- [ ] Kuzu opens read-only and graph labels/relationships are visible.
- [ ] RAG MCP exposes `hermes_master_search` or equivalent canonical tool name.
- [ ] Storage calculator tool path works for sizing queries.
- [ ] Evidence Ledger appears in RAG output.
- [ ] Weak-evidence queries return caution instead of confident guesses.
- [ ] Access policy canaries pass for the target profile.
- [ ] Final answer path uses RAG first for domain questions.

## Public/private contract

If a future implementation changes, update this public repo first at the design level, then update the private source map. The public docs should remain useful even if exact script names change.
