# Graph Context with Ladybug

[Documentation index](../README.md) · [Project home](../../README.md)

> **Scope:** Independent project design guidance, not a Nutanix-approved implementation. This page does not establish deployed behavior, measured effectiveness, or vendor support. The public repository does not include a runnable service.

## Reading this page

A **graph** stores entities as nodes and relationships as edges. Here, Ladybug names the reference graph component; LanceDB names the searchable text/vector store. **Recall** measures how much relevant evidence retrieval finds. **Top-k** means the first k results. **Shadow** runs an experiment without changing delivered answers; a **canary** is a representative regression test. A **bounded boost** limits how much a signal may change ranking.

NX-Shield uses graph context as a retrieval signal, not as a truth oracle.

## What belongs in the graph

Good graph nodes:

- products,
- features,
- KB/article identities,
- errors and symptoms,
- hardware models,
- components,
- source documents/chunks.

Good relationships:

- product mentions feature,
- document discusses product,
- KB relates to error,
- component belongs to hardware family,
- chunk mentions entity.

## What does not belong in the graph

Do not use the graph as a second copy of the full corpus. Keep full text and source metadata in LanceDB or document storage. The graph should point back to source identities.

Do not use graph relationships as final-answer evidence by themselves. A relationship can suggest what to retrieve, but a user-facing claim still needs a source document or deterministic tool output.

## Use cases

- Expand ambiguous acronyms or product aliases.
- Find neighboring concepts for reranking.
- Explain why two documents are related.
- Detect when retrieval is source-thin around a required entity.
- Identify graph-neighbor candidates for shadow evaluation.

## Identity-admitted, read-only projection

Treat graph context as an optional read-only projection of evidence, not an independent authority. Admit the authenticated identity before querying or exposing labels. Each returned relationship must retain complete evidence labels: source identity and locator, applicable version, relationship scope, and the passage context needed to preserve conditions and exceptions. If a label cannot be safely grounded and bounded, omit it rather than clipping away its qualification.

Resolve origins against the current query-scoped canonical evidence view, reconcile restrictive duplicates, and apply caller and model-processing policy. A stale, missing, superseded, or out-of-scope origin cannot authorize a graph hint. Do not expose restricted titles or source existence through a graph explanation. Recheck origins before evidence serialization.

Use only a small bounded ranking boost for admitted hints; protect exact-identifier results and source authority. Entity co-occurrence and graph distance are not semantic proof or support for a composed claim. Graph failure may use an explicitly qualified graph-disabled retrieval path, but identity/policy errors must not become a permissive fallback.

## Graph-shadow rollout

Graph-assisted retrieval should be promoted in phases:

1. **Baseline** — serve the current hybrid/vector/lexical/exact retrieval path.
2. **Shadow** — compute graph-assisted candidates in reports only.
3. **Compare** — inspect top evidence keys, top-1 changes, top-5 overlap, exact-ID behavior, source-authority gates, and latency.
4. **Warn** — allow graph assistance to annotate or warn, but not override source-backed evidence.
5. **Serve** — promote graph candidate fusion only after regression gates pass.

A graph-shadow report should answer:

- Did graph context add useful candidates?
- Did it displace an exact identifier hit?
- Did it increase low-authority or stale evidence?
- Did it violate profile access boundaries?
- Did it add unacceptable latency?

## Service-safe graph backend pattern

Graph libraries and vector-store runtimes do not always coexist safely inside one long-running Python process. A production graph layer should therefore support a service-safe probe or adapter mode:

- keep the graph database as a read-only retrieval signal during rollout,
- isolate driver-specific imports if mixed native modules can conflict,
- make graph candidate ordering deterministic before comparing top-k results,
- preserve a rollback path to the previous graph backend or to graph-disabled retrieval,
- check read-only behavior against the selected backend/version contract; require sidecar absence only when that contract requires it, and never delete recovery or lock files merely to satisfy a canary.

For an SDK-only deployment, use a host-native virtual environment for the graph adapter and qualify its interpreter and native dependencies independently. Do not infer that container tooling or a graph server is required. Keep Kuzu, where retained, as a read-only rollback/archive backend only—not an active query helper or automatic fallback. Explicit rollback must pass its own schema, identity, and top-level entry-point checks.

This pattern lets a team evaluate a new graph backend without treating the migration as a data-store cutover. The backend can be active as a candidate source while ranking remains canary or guarded-live.

## Guarded live promotion

Moving graph context from shadow to serving should require more than a passing aggregate score. A safer promotion gate checks:

- every top-1 change is source-reviewed,
- no exact identifier hit is demoted,
- no source-authority downgrade occurs,
- top-5 overlap remains high for neutral reorderings,
- answer verification still rejects unsupported architecture composition,
- rollback can disable graph ranking without changing the corpus.

A useful intermediate state is **guarded live**: graph ranking can influence retrieval with bounded boosts, exact-ID protection, query-anchor requirements, and verifier fallback still active. This treats graph as an operationally useful signal while keeping the Evidence Ledger and verifier as the final safety gates.

## Safety rule

Graph proximity can justify retrieving more evidence. It cannot justify an answer by itself.

A good final answer should cite source documents or deterministic tool outputs, not simply say "the graph says so."
