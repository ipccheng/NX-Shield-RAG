# Security and Access Policy

> **Scope:** Independent project design guidance, not a Nutanix-approved implementation. This page does not establish deployed behavior, measured effectiveness, or vendor support. The public repository does not include a runnable service.

## Reading this page

**RAG (retrieval-augmented generation)** passes retrieved passages to a language model. **FTS** means full-text search. An **identity** is the authenticated caller or service principal; a **profile** is configuration bound to that identity, not a user-supplied permission claim. **Fail closed** means denying access when required identity or policy information is missing. **MCP (Model Context Protocol)** is a tool interface, not an authorization system.

RAG access control must happen before and during retrieval, not only in the final answer prompt.

## Threat model

An enterprise RAG can leak information when:

- internal documents are retrieved for public users,
- fallback search paths bypass vector-store filters,
- chat/memory sources are mixed with public docs,
- the answer model paraphrases private evidence without citing it,
- logs or public repos include local paths, tokens, or private snippets.

## Design rules

1. **Classify every source.** Public/partner/internal/private should be metadata, not a folder convention only.
2. **Confirm rights and approval before ingestion.** A document being technically retrievable does not mean it is approved for embeddings, RAG, model prompts, public demos, partner use, or customer-facing answers.
3. **Apply access filters at retrieval time.** Vector, FTS, exact search, local grep, graph expansion, and web/chat fallbacks must share policy.
4. **Disable unsafe fallbacks per identity.** If a profile is public/partner-facing, do not let it silently query internal chat or memory.
5. **Surface policy in the evidence ledger.** A blocked answer should say evidence is unavailable under the current policy.
6. **Keep public docs sanitized.** No tokens, private hostnames, local-only counts, or private operational details.
7. **Keep approval status separate from technical controls.** Access filters, evidence ledgers, and local storage support governance; they do not by themselves approve the application, provider path, data class, or use case.
8. **Require identity consistency.** Environment, process arguments, and policy configuration must resolve to the same serving identity; startup and canaries fail closed on mismatch.
9. **Treat unknown identity conservatively.** Missing or unrecognized identities never inherit internal access.

## Profiles and identities

The same corpus can serve different agents if each MCP service/profile has a clear identity and policy. Examples:

- internal research profile — broader corpus, still evidence-bound,
- partner-facing profile — restricted corpus and stronger citation rules,
- public demo profile — public-only corpus and no internal fallbacks.

## Repository policy

This public repo contains design docs only. Source scripts live in the private source repo. Credentials and data stores live outside Git. Governance records, approval decisions, risk assessments, and provider-review artifacts should stay in the appropriate internal systems and should not be copied into this public repository.

## Enforcement boundaries to test

Treat retrieved documents, graph labels, tool output, and conversation history as untrusted data, never as instructions that may change permissions. A prompt-injection detector is an additional signal, not the authorization boundary.

- Authenticate the caller and bind a server-controlled identity; do not accept an asserted profile name as permission.
- Reconcile duplicate evidence with conflicting source or access metadata conservatively before source filtering, ranking, or deduplication can hide the restrictive copy.
- Apply policy to context expansion, graph neighbors, exact lookup, fallback results, and any evidence appended by a gateway. Recheck before serialization and model submission.
- Scope caches, logs, and retained conversation context to authorized identities and retention policy; embeddings and graph metadata also require data classification.
- Record unauthorized retrieval as a blocker even when the final answer omits it. Do not expose restricted titles or source existence in a denial message.
- Test unknown identities, missing policy fields, conflicting duplicates in both input orders, and rollback schemas through the actual application path.

See [evaluation](../evaluate/evaluation-strategy.md) and [governance](ai-governance-alignment.md). These are required test objectives, not claims that the public repository implements the controls.
