# AI Governance Alignment

> **Scope:** Independent project design guidance, not a Nutanix-approved implementation. This page does not establish deployed behavior, measured effectiveness, or vendor support. The public repository does not include a runnable service.

## Reading this page

**RAG (retrieval-augmented generation)** supplies retrieved source passages to a language model. An **embedding** is a numeric text representation; a **reranker** scores candidate passages for relevance. Both may send source data to a model service. **Prompt injection** is untrusted text attempting to redirect application behavior. These are project recommendations, not a reproduction of Nutanix policy or a claim of compliance with any standard.

NX-Shield RAG is documented as a design pattern, not as proof that any specific deployment is approved for production or external use. A deployment should be reviewed under the organization’s AI governance process before it is used with sensitive data, made broadly available, or exposed to partners or customers.

This page translates the design into governance-friendly operating requirements without publishing private policy text, internal system details, or confidential data handling specifics.

## Governance posture

Treat a running NX-Shield-style RAG service as an AI system with these properties:

- It may combine internal software, external model APIs, open-source components, deterministic tools, and retrieval indexes.
- It may process prompts, retrieved evidence, operational logs, and generated outputs.
- It may be agentic if it can call tools, access multiple systems, schedule work, or act with limited human intervention.
- It may become higher risk when it uses sensitive, customer, partner, employee, source-code, telemetry, or licensed third-party data.

The design therefore assumes that deployment requires accountable ownership, documented data flows, risk classification, access controls, monitoring, and explicit approval for the intended use case.

## Approval boundary

Do not describe the system as “approved,” “compliant,” or “safe for production” merely because it uses RAG or stores evidence locally.

Approval should cover the full operating path:

1. **Application/system:** the agent, gateway, RAG service, tools, and user interfaces.
2. **Model/provider path:** any external or internal LLM, embedding model, reranker, classifier, or API service that receives prompts, retrieved evidence, code, telemetry, or outputs.
3. **Data classes:** public, internal, confidential, partner/NDA, customer, personal, source-code, telemetry, and licensed third-party data.
4. **Use case:** internal productivity, presales support, technical support, partner-facing answers, customer-facing answers, or automation.
5. **Human oversight:** who reviews, approves, intervenes, and can stop or roll back the system.
6. **Monitoring and feedback:** how queries, outputs, incidents, quality issues, and user reports are logged and reviewed.

If any of these change materially, the deployment should be re-reviewed before the new use case is treated as approved.

## Design controls mapped to governance goals

### Accountability

- Assign an AI business owner or equivalent accountable owner for each deployment.
- Maintain a system inventory entry or equivalent internal record.
- Document the intended purpose, user population, supported domains, and excluded uses.
- Keep a decommissioning and rollback path for the runtime and corpus.

### Transparency

- Disclose AI-generated answers in partner- or customer-facing interfaces.
- Explain that answers are generated from retrieved evidence and may be incomplete when evidence is weak.
- Preserve citations, source families, source authority, and weak-evidence notices in answer context.
- Document data sources, corpus boundaries, known limitations, and fallback behavior.

### Human oversight

- Keep a human accountable for high-impact or external-facing answers.
- Require review before using generated output for customer commitments, legal/commercial conclusions, security remediation, or architecture decisions with material impact.
- Provide a clear escalation path when evidence is missing, stale, conflicting, or outside the approved corpus.

### Privacy and data security

- Classify each source before ingestion and enforce access policy during retrieval, not only during final answer generation.
- Limit external model/provider calls to data classes and use cases approved for that path.
- Keep sensitive or licensed data out of public repositories and public/demo identities.
- Apply least-privilege access, encryption in transit and at rest where applicable, and protected logs.
- Avoid using sensitive, customer, employee, source-code, telemetry, or licensed third-party data for training, fine-tuning, embeddings, or RAG unless rights and approvals are documented.

### Safety and reliability

- Prefer deterministic tools for arithmetic, sizing, or structured calculations.
- Use evidence-ledger obligations to separate supported claims from missing or weak evidence.
- Fail closed or return a bounded fallback when retrieved evidence does not support the requested answer.
- Test adversarial prompts, prompt injection attempts, stale-source retrieval, access-boundary leaks, and unsupported-claim generation before deployment.
- Monitor inputs and outputs for anomalies, hallucinations, policy bypasses, and quality regressions.

### Fairness

- Do not use RAG outputs to make or automate employment, credit, healthcare, legal, or similarly consequential decisions without separate review and controls.
- If a use case affects individuals or protected groups, add bias assessment, representative test cases, and human appeal/override mechanisms.

## Corpus governance checklist

Before a source is ingested, record:

- source owner and source family,
- licensing or usage rights,
- data classification and access scope,
- whether personal, customer, partner, employee, source-code, telemetry, or third-party licensed data is present,
- whether the content is approved for embeddings and RAG retrieval,
- whether the content is approved for the target identity, such as internal-only, partner-facing, or public/demo,
- retention and removal expectations,
- provenance fields that allow future audits and deletion.

## Runtime governance checklist

Before serving answers, verify:

- approved application/system entry or equivalent review record exists,
- owner and escalation path are documented,
- model/provider calls match the approved data classification and use case,
- profile identities enforce source access boundaries during retrieval,
- logs capture enough information for review without leaking secrets or unnecessary sensitive content,
- feedback and incident channels exist,
- rollback/kill-switch behavior is documented,
- evaluation canaries cover exact-ID lookup, weak evidence, prompt injection, access leakage, stale evidence, and deterministic-tool paths.

## Recommended wording

Use wording like:

> “This design proposes controls for data classification, retrieval-time access policy, evidence provenance, human oversight, monitoring, and rollback. Their implementation and effectiveness must be verified. A live deployment still requires approval for its application, providers, data classes, and use case.”

Avoid wording like:

> “RAG makes the system compliant.”

> “Local storage means external model calls are safe.”

> “Partner-facing answers are approved because internal filters exist.”

RAG is a control pattern. It does not replace formal approval, data classification, provider review, monitoring, or human accountability.
