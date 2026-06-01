# Graph Context with Kuzu

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

## Safety rule

Graph proximity can justify retrieving more evidence. It cannot justify an answer by itself.

A good final answer should cite source documents or deterministic tool outputs, not simply say "the graph says so."
