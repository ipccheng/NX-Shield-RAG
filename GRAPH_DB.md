# Nutanix Graph DB — Kuzu Embedded Graph Database

> **Last updated:** 2026-05-12
> **Status:** Active

---

## Overview

The Graph DB is an embedded Kuzu database that stores entity relationships extracted from Nutanix technical documentation. It sits alongside the LanceDB vector store as a **read-only graph layer** used to boost search results by linking related entities.

**Purpose:** When a user asks about a product or ecosystem entity, the graph discovers all chunks connected to that entity and boosts their search rankings. This creates a hybrid RAG pipeline: **vector similarity + graph traversal**.

---

## System Architecture

### Two-DB Layout

```
┌─────────────────────────────────────────┐
│  LanceDB (nutanix_rag_v3_dedup)         │
│  ┌────────────────────────────────┐     │
│  │ Chunks with vectors + metadata │     │
│  │ chunk_hash = PRIMARY KEY       │     │
│  │ rel_path, text, access_level,  │     │
│  │ doc_type, primary_product, ... │     │
│  └──────────────┬─────────────────┘     │
│                 │ chunk_hash             │
│                 ▼                        │
│  ┌────────────────────────────────┐     │
│  │ Kuzu Graph (nutanix_graph_v3)   │     │
│  │ Chunk → HAS_RELATIONSHIP → Entity │   │
│  │ Entity → RELATED_TO → Entity     │    │
│  └────────────────────────────────┘     │
└─────────────────────────────────────────┘
```

### File Locations

| Component | Path |
|---|---|
| **LanceDB** | `~/.openclaw/memory/lancedb-pro/nutanix_rag_v3_dedup.lance` |
| **Kuzu DB** | `~/.openclaw/memory/kuzu-pro/nutanix_graph_v3` |
| **Vault JSONL** | `~/.openclaw/memory/kuzu-pro/minimax_extraction_vault.jsonl` |


---

## Schema

### Node Tables

```sql
CREATE NODE TABLE Entity(
    name          STRING PRIMARY KEY,    -- e.g. "PRISM_CENTRAL", "VMware", "AOS_6.5"
    display_name  STRING,                -- Human-readable name
    entity_type   STRING                 -- "Product", "Software", "Entity", etc.
);

CREATE NODE TABLE Chunk(
    chunk_hash    STRING PRIMARY KEY     -- MD5 of normalized text (links to LanceDB)
);
```

### Relationship Tables

```sql
CREATE REL TABLE HAS_RELATIONSHIP(
    FROM Chunk TO Entity,                -- Which chunks reference which entities
    rel_type            STRING,          -- e.g. "SUPPORTS", "REQUIRES", "DEPRECATES"
    source_chunk_hash   STRING           -- Chunk that established this relationship
);

CREATE REL TABLE RELATED_TO(
    FROM Entity TO Entity,               -- Entity-to-entity relationships
    rel_type            STRING,          -- e.g. "SUPPORTS", "INCOMPATIBLE_WITH"
    source_chunk_hash   STRING           -- Source chunk for traceability
);
```

### Node Counts (as of 2026-05-12)

| Node Type | Count |
|---|---|
| Entity | 48,483 |
| Chunk | 72,488 |
| HAS_RELATIONSHIP edges | 334,800 |
| RELATED_TO edges | 334,800 |

---

## Data Sources

### 1. MiniMax Extraction Vault (`minimax_extraction_vault.jsonl`)

This is the **source of truth** for the graph. It contains MiniMax API extraction results for each chunk:

```json
{
    "chunk_hash": "f984c3581b8a26c95217c1a774675072",
    "rel_path": "...",
    "entities": [
        {"id": "PRISM_CENTRAL", "type": "Product", "name": "PRISM_CENTRAL"},
        {"id": "AOS", "type": "Software", "name": "AOS"}
    ],
    "relationships": [
        {"source": "V4_API", "target": "PRISM_CENTRAL", "type": "SUPPORTS"},
        {"source": "V3_API", "target": "PRISM_CENTRAL", "type": "SUPPORTS"}
    ]
}
```

**Known bug:** Some records have nested lists: `"relationships": [[{...},...],...]` — requires flattening before processing.

### 2. LanceDB (for chunk_hash validation)

When building the graph, only chunks that exist in `nutanix_rag_v3_dedup` are included. The vault may reference chunk_hashes that were removed during deduplication — these are filtered out.

### 3. Entities Referenced in Relationships Only

Some entities appear in relationship rows but NOT in the vault's `entities` list for a given chunk. These "missing" entities are automatically discovered during graph build by scanning ALL relationship rows for entity names not yet in the Entity node table.

---

## Build Process

### Prerequisites

- Python 3.14+
- `kuzu==0.11.3` (`pip install kuzu`)
- LanceDB connected to `nutanix_rag_v3_dedup`
- Vault JSONL file at `minimax_extraction_vault.jsonl`

### What the Build Does

1. **Loads valid chunk_hashes** from LanceDB `nutanix_rag_v3_dedup`
2. **Parses the vault JSONL** — flattens nested lists, collects entities and relationships
3. **Creates Kuzu schema** — Entity, Chunk nodes + HAS_RELATIONSHIP, RELATED_TO edges
4. **Bulk loads entities** via CSV `COPY FROM` (fast, 48k entities in seconds)
5. **Bulk loads chunks** via CSV `COPY FROM` (72k chunks in seconds)
6. **Batch inserts relationships** — 334k edges in batches of 300 via `MATCH-CREATE`. Each edge inserts two relationships (Chunk→Entity via HAS_RELATIONSHIP, Entity→Entity via RELATED_TO). Takes ~10 minutes.
7. **Backfills missing entities** — any entity referenced in relationships but excluded from the vault's entity list gets added.

### Key Scripts

| Script | Purpose |
|---|---|
| `/tmp/kuzu_rebuild_v3.py` | Full rebuild from vault JSONL + LanceDB |
| `~/.openclaw/workspace/rag/nutanix/kuzu/kuzu_writer.py` | Chunk insertion for new embeds |

---

## Query Patterns

### Graph Boost (for RAG Search)

The graph boost works in `nutanix_rag_search.py` via `_graph_lookup(query)`:

```python
# Extract entities from query
products = extract_mentioned_products(query)      # "Prism Central" → ["Prism"]
entities = extract_ecosystem_entities(query)       # "VMware" → ["VMware"]

# Query Kuzu for related chunks
MATCH (c:Chunk)-[:HAS_RELATIONSHIP]->(e:Entity {name: 'PRISM'})
RETURN DISTINCT c.chunk_hash
```

Results: chunks whose chunk_hash matches are boosted by **×1.5** in the final score.

### Common Cypher Queries

```cypher
-- Count all entity nodes
MATCH (e:Entity) RETURN count(e);

-- Count all relationship edges
MATCH ()-[r:HAS_RELATIONSHIP]->() RETURN count(r);

-- Find all chunks related to a specific entity
MATCH (c:Chunk)-[:HAS_RELATIONSHIP]->(e:Entity {name: 'PRISM'})
RETURN c.chunk_hash, e.name, e.entity_type;

-- Find entity-to-entity relationships for a product
MATCH (s:Entity {name: 'V4_API'})-[r:RELATED_TO]->(t:Entity)
RETURN s.name, r.rel_type, t.name;

-- Find the most connected entities
MATCH (e:Entity)<-[:HAS_RELATIONSHIP]-()
RETURN e.name, count(*) AS connections
ORDER BY connections DESC
LIMIT 20;

-- Traverse: find chunks mentioning BOTH Prism AND LCM
MATCH (c:Chunk)-[:HAS_RELATIONSHIP]->(e1:Entity {name: 'PRISM'}),
      (c)-[:HAS_RELATIONSHIP]->(e2:Entity {name: 'LCM'})
RETURN DISTINCT c.chunk_hash;
```

### Performance

| Operation | Time |
|---|---|
| Kuzu traversal (CO_OCCURS_WITH) | ~6.6ms per query |
| LanceDB BTree point-lookup (chunk_hash) | 1-3ms per chunk |
| Full hybrid round-trip | <10ms per chunk |

---

## Embed Pipeline Integration

When new documents are embedded via `embed_one.py`, the following flow occurs:

1. **LanceDB insert** → `merge_insert("chunk_hash")` deduplicates by chunk hash
2. **Kuzu insert** → `kuzu_writer.write_chunk_batch()` creates Chunk nodes by chunk_hash (MERGE)

The entity/relationship extraction (MiniMax API) is a separate batch process that feeds into the vault JSONL. The per-file embed script does NOT run MiniMax extraction — it only creates the Chunk node for graph-to-vector bridging.

---

## Troubleshooting

### "Cannot find property rel_type for rel"

**Cause:** The relationship table was created WITHOUT inline properties.

```sql
-- WRONG — no properties on rel table
CREATE REL TABLE HAS_RELATIONSHIP(FROM Chunk TO Entity);

-- RIGHT — properties defined inline
CREATE REL TABLE HAS_RELATIONSHIP(FROM Chunk TO Entity, rel_type STRING, source_chunk_hash STRING);
```

**Fix:** Drop the database and recreate with inline properties on the `CREATE REL TABLE` statement.

### 0 Relationship Edges After Build

**Cause:** The rebuild attempted to set properties on a property-less relationship table. The `MATCH-CREATE` queries ran but silently failed because Kuzu couldn't find the `rel_type` property.

**Fix:** Ensure rel table creation includes all properties. Delete the partial DB and rebuild.

### Kuzu DB Locked

If you see `Database locked` errors, another process is writing to Kuzu. Check for active Python scripts or Jupyter kernels:

```bash
ps aux | grep kuzu
```

### Slow Relationship Insertion

Inserting 334k edges via `MATCH-CREATE` takes ~10-15 minutes. If it's too slow:

1. Increase batch size from 300 to 500
2. Check WAL growth — Kuzu checkpoints periodically, a large WAL slows writes
3. Use `set_max_threads_for_exec()` to allocate more CPU threads

---

## Sync Protocol

- **MacBook (Neo):** Primary build machine for Kuzu
- **Mac mini (Sam/NX_Shield):** Receives synced Kuzu DB via rsync
- **Never run Kuzu builds on Mac mini** — always build on MacBook, then rsync

```bash
rsync -avz -e "ssh" \
  ~/.openclaw/memory/kuzu-pro/nutanix_graph_v3 \
  macmini:~/.openclaw/memory/kuzu-pro/nutanix_graph_v3
```

The vault JSONL is NOT synced — it's only on MacBook as the build source material.
