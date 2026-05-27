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
2. **Apply access filters at retrieval time.** Vector, FTS, exact search, local grep, graph expansion, and web/chat fallbacks must share policy.
3. **Disable unsafe fallbacks per identity.** If a profile is public/partner-facing, do not let it silently query internal chat or memory.
4. **Surface policy in the evidence ledger.** A blocked answer should say evidence is unavailable under the current policy.
5. **Keep public docs sanitized.** No tokens, private hostnames, local-only counts, or private operational details.

## Profiles and identities

The same corpus can serve different agents if each MCP service/profile has a clear identity and policy. Examples:

- internal research profile — broader corpus, still evidence-bound,
- partner-facing profile — restricted corpus and stronger citation rules,
- public demo profile — public-only corpus and no internal fallbacks.

## Repository policy

This public repo contains design docs only. Source scripts live in the private source repo. Credentials and data stores live outside Git.
