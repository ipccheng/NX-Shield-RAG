# Security and Access Policy

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
