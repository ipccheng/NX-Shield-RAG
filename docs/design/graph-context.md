# Graph Context with Ladybug

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
- verify that no write-ahead, shadow, or lock sidecars appear during read-only serving canaries.

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
