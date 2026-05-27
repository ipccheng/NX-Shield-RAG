# Private Source Map

This page maps public design concepts to private implementation locations in `ipccheng/NX-Shield-RAG-src`.

No private repo content is required to read this page.

| Public concept | Private source path |
|---|---|
| Main RAG query/search path | `rag/hermes-nutanix/scripts/openclaw/nutanix_rag_search.py` |
| v4/unified backend lineage | `rag/hermes-nutanix/scripts/openclaw/nutanix_rag_v4_backend.py` |
| MCP gateway wrapper | `rag/hermes-nutanix/scripts/openclaw/universal_gateway_mcp.py` |
| Storage calculator | `rag/hermes-nutanix/servers/storage_calc*.py` and `rag/hermes-nutanix/scripts/openclaw/storage_calc.py` |
| Ingestion scripts | `rag/hermes-nutanix/ingestion/` |
| Legacy ingestion lineage | `rag/hermes-nutanix/ingestion/openclaw_pipeline/` |
| Entity/tag extraction | `rag/hermes-nutanix/scripts/openclaw/tagger_v3.py` |
| Kuzu graph writer/backfill | `rag/hermes-nutanix/scripts/openclaw/kuzu_writer.py`, `kuzu_backfill.py` |
| Runtime config templates | `rag/hermes-nutanix/config/` |
| Agent profile prompts | `hermes/profiles/sam/`, `hermes/profiles/nx-shield/` |
| LaunchAgent service templates | `ops/launchagents/` |
| Rebuild/eval reports | `reports/exchange/` |

## Rule for future maintainers

Keep public docs stable and implementation-neutral. Use this map to locate the private script that implements a public concept, but do not paste private credentials, local-only host details, or private evidence into public docs.
