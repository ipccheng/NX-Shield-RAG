# RAG concepts for infrastructure engineers

[Home](../../README.md) · Next: [Architecture](../design/architecture.md)

## Two different workflows

A RAG system has a **data preparation workflow** and a **question-answering workflow**. They may scale, fail, and change independently.

### Prepare the knowledge collection

1. **Authorize the source.** Confirm permission to ingest, process, retain, and expose its content to the intended users and model services.
2. **Parse the document.** Extract text and preserve headings, tables, source links, and version information. OCR (optical character recognition) may be needed for scanned pages.
3. **Split it into chunks.** A chunk is a passage small enough to retrieve and send to the model. Keep enough surrounding context to avoid changing its meaning.
4. **Attach metadata.** Record the source, version, ownership, access rules, and whether the content has been superseded.
5. **Build search indexes.** Create keyword indexes and, where appropriate, embeddings for meaning-based search.
6. **Validate before publishing.** Check extraction quality and access restrictions before making the collection available.

### Answer a question

1. Authenticate the user and determine the permitted knowledge scope.
2. Identify the question's requirements, such as product version and exact document identifiers.
3. Retrieve candidates using complementary search methods.
4. Reorder candidates and select a small evidence set.
5. Draft an answer from that evidence, using deterministic tools when appropriate.
6. Check the claims, expose evidence gaps, and return citations or a qualified response.

**Example:** “Is this upgrade supported?” needs an exact source for the relevant versions and configuration. A passage about a similar upgrade is not enough, even if it scores highly in semantic search.

## Essential vocabulary

- **LLM (large language model):** the model that interprets and generates text. Its plausible wording is not proof of correctness.
- **Inference:** running an already trained model to produce an output. A model endpoint is an API through which an application requests that output.
- **Embedding:** a numeric representation of text used to compare meaning. An embedding is not a summary, an access-control mechanism, or anonymization.
- **Vector search:** finding nearby embeddings. It helps with paraphrases but may confuse similar products, versions, or conditions.
- **Lexical / full-text search (FTS):** matching words and identifiers. Useful for exact names and KB IDs, but less tolerant of different wording.
- **Hybrid retrieval:** combining vector and lexical search. It is a retrieval strategy, not a model type.
- **Reranking:** scoring an initial candidate set more carefully against the question. A cross-encoder is one type of reranker that reads the question and passage together.
- **Reciprocal Rank Fusion (RRF):** combining ranked result lists using their positions, rather than assuming different search scores are directly comparable.
- **Corpus:** the collection of source material available to retrieval. “Indexed” means searchable; it does not mean approved for every user or current for every question.
- **Grounding:** tying a claim to evidence that actually supports it. A citation can point to a real page and still fail to support the sentence beside it.
- **Evidence ledger / obligations:** a structured record of what the answer must establish, which evidence supports it, and what is missing.
- **Graph context:** relationships between entities, such as a product and its components. A relationship helps navigation; the originating document must still support the claim.
- **MCP (Model Context Protocol):** a protocol for exposing tools and resources to AI applications. It is not a vector database or an authorization policy by itself.
- **Agentic RAG:** a workflow in which an agent chooses retrieval or tool steps. More autonomy is not automatically more accurate; constrain tool permissions, retries, and side effects.
- **Token:** a unit of text processed by a model. Input length and generated output affect resource use; tokens are not a fixed number of words.
- **Context window:** the amount of input and output a model can handle in a request. A larger window does not make irrelevant evidence useful.
- **Fine-tuning:** additional training that changes model parameters. Unlike retrieval, it is not simply looking up current documents at question time.

## Operational terms used in this notebook

- **Fail closed:** reject or withhold an operation when its authorization or required safety conditions cannot be established. It does not mean hiding errors.
- **Shadow mode:** compute a candidate result for comparison without allowing it to change the answer delivered to users.
- **Canary:** a limited test exposure or representative probe before broader enablement. Define which meaning applies in each procedure.
- **Promotion:** deliberately making a validated candidate active. Copying source files or publishing documentation is not promotion.
- **Rollback:** restore a known compatible prior state. A backup that has never been restored is not demonstrated recovery.
- **Parity:** agreement on explicitly tested properties between environments. Matching file hashes alone does not prove equivalent running behavior.
- **Revision-bound evidence:** test results tied to the exact code, data, configuration, and environment tested.

## Three common misconceptions

**“The model knows our documents after we upload them.”**
In a typical RAG workflow, documents become retrievable data. The model only sees the passages selected for its request; ingestion is not automatically model training.

**“An internal vector database makes the whole solution private.”**
Document parsing, embeddings, reranking, generation, fallbacks, logging, and monitoring can each cross a different data boundary. Review the full path.

**“A passing retrieval test proves the answer is safe.”**
Retrieval quality, claim support, permission isolation, and runtime reliability need separate tests. Include negative cases: missing evidence, conflicting documents, denied users, unavailable services, and unsupported product versions.
