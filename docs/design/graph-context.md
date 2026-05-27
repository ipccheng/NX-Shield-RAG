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

## Use cases

- Expand ambiguous acronyms or product aliases.
- Find neighboring concepts for reranking.
- Explain why two documents are related.
- Detect when retrieval is source-thin around a required entity.

## Safety rule

Graph proximity can justify retrieving more evidence. It cannot justify an answer by itself.

A good final answer should cite source documents or deterministic tool outputs, not simply say "the graph says so."
