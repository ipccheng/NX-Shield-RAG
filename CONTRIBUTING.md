# Publication and contribution guidance

[Project home](README.md) · [Documentation index](docs/README.md)

This repository shares independent engineering patterns. It is not an official Nutanix publication, approved application, support contract, or compliance certification.

## Write for technical readers who are new to AI

- Explain what a component does and why it is needed before naming its implementation.
- Expand an acronym at first use or link to the [glossary](docs/getting-started/rag-basics.md).
- Separate conceptual design, historical implementation notes, recommendations, and freshly verified results.
- Prefer small examples and clear responsibility boundaries over unexplained lists of techniques.
- Keep the beginner path short; put detailed schemas and operating procedures in the specialist pages.

## Public-content boundaries

Keep this repository focused on our RAG system: its architecture, retrieval methods, evidence controls, evaluation, and operating patterns. Nutanix solution technical information belongs in the RAG knowledge collection, not here. Do not add product feature guides, solution deployment details, or solution-specific integration designs, even when the underlying sources are public.

Publish original explanations and references relevant to RAG engineering. Do not copy private source code, customer details, credentials, internal enablement material, restricted Portal/KB bodies, licensed research, private reports, live host identifiers, or deployment-specific paths into this repository.

Document access, processing permission, and republication permission are different. When rights are unclear, leave the material out pending a rights review. Public availability alone is not a license to republish a whole work.

Do not imply:

- Nutanix sponsorship, validation, certification, endorsement, or formal compliance approval.
- Product support, licensing, entitlement, compatibility, or performance that the cited evidence does not establish.
- That a preview feature is production-ready, or a proposed integration is already deployed.
- That automated safety controls guarantee correct answers, eliminate all prompt injection, or replace legal/security review.

Use product names only to identify the relevant technologies. Nutanix and other product names are trademarks of their respective owners. Do not add corporate logos or copied vendor diagrams without appropriate permission.

## Review checklist

Before publication:

- Review every changed document and any linked diagrams; image text and metadata can leak information too.
- Check relative links, code fences, diagram syntax, terminology, and consistency with the repository's stated scope.
- Exclude Nutanix solution details; keep examples focused on how retrieval and evidence checks work, not on product answers or deployment instructions. Cite externally sourced RAG-engineering claims where appropriate.
- Scan for credentials, personal data, private paths/hosts/identifiers, restricted source content, and approval-implying wording.
- Remove unsupported live metrics rather than presenting an old sample as a current benchmark.
- Check the diff for accidental inclusion of runtime data, audit output, or private source files.
- Record checks honestly. A secret scan or editorial review is not a formal compliance determination.

If a publication issue is found, stop further publication of the affected material and follow the applicable remediation process. Do not post the sensitive payload in a public issue. History rewriting or credential revocation requires a separately scoped response, not a silent documentation edit.
