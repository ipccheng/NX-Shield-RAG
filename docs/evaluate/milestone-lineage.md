# Milestone Lineage

NX-Shield RAG evolved through several design lessons. This page keeps the public lessons without exposing private operational detail.

## Key lessons

### Retrieval architecture improved, but answer quality needed its own layer

Early work focused on search channels, routing, and reranking. Later work showed that good retrieval can still produce wrong answers unless the final synthesis is constrained by an Evidence Ledger.

### Graph boost is useful but insufficient

Kuzu graph context improved structural recall and explanation. It did not replace source evidence. The graph is now treated as advisory context.

### Unified corpus beats parallel legacy stores

A single active search path with explicit lineage metadata is easier to operate than multiple hidden fallbacks. Old stores should remain rollback archives until soak completes.

### Calculator-first changed sizing reliability

Storage sizing and similar math questions should use deterministic calculators first. RAG provides definitions, assumptions, and caveats.

### Profile endpoints require direct verification

A profile can discover a tool while its backing service still points to an old script/config. Direct MCP canaries per endpoint are mandatory.

### Public docs should avoid dynamic operational facts

Live row counts, private hostnames, internal paths, and temporary benchmark numbers go stale quickly and can leak context. Public docs should focus on stable design.
