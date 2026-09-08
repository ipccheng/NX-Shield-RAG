# Evidence-Ledger Answering

> **Scope:** Independent project design guidance, not a Nutanix-approved implementation. This page does not establish deployed behavior, measured effectiveness, or vendor support. The public repository does not include a runnable service.

## Reading this page

An **obligation** is a question the answer must address. A **verifier** checks a draft against its evidence; it can make mistakes and does not certify vendor support. **Fail closed** means withholding normal delivery when a required evidence or policy check fails. **NIC** means network interface card; **RF** means replication factor, a data-copy assumption for sizing. Use the [ledger template](../../templates/evidence-ledger-template.yaml) and [query examples](../../examples/query-obligations.md).

An evidence ledger records which claims the available sources support and which questions remain unanswered.

It turns retrieval output into an explicit answer contract.

## Problem

A model can retrieve good documents and still write a bad answer. Common failures:

- correct source retrieved, wrong conclusion synthesized,
- one source overgeneralized beyond its scope,
- missing evidence hidden behind confident wording,
- internal/low-authority evidence treated like public official guidance,
- numeric sizing answered from prose instead of deterministic calculation.

## Pattern

Before final answer generation, compile an evidence ledger with four sections:

1. **Answer obligations** — what the user actually needs answered.
2. **Supported claims** — claims directly backed by retrieved evidence or tools.
3. **Weak/missing claims** — obligations where evidence is partial or absent.
4. **Answer rules** — constraints the final writer must obey.

## Example

This is a fictional structure, not an excerpt from vendor documentation or evidence that a hardware change is supported. Replace the placeholders with verified sources before use.

```yaml
answer_obligations:
  - identify whether the replacement path is documented
  - list required configuration checks after hardware replacement
  - call out production-impacting risks

supported_claims:
  - source: <verified hardware source and section>
    claim: <network validation requirement directly supported by that source>
  - source: <verified networking source and section>
    claim: <mapping review requirement directly supported by that source>

weak_or_missing_claims:
  - exact Broadcom-to-Intel replacement certification evidence was not found
  - customer-specific firmware/driver compatibility is not proven by retrieved docs

answer_rules:
  - do not state the exact replacement is certified unless evidence says so
  - provide a pre-change and post-change checklist
  - mark production-impacting steps as requiring maintenance planning
```

## Verdicts

Use verdicts to decide answer posture. There are two useful layers:

Conceptual posture:

- **strong** — enough direct, authoritative evidence to answer normally.
- **review** — useful evidence exists, but production impact or partial evidence requires caution.
- **weak** — evidence is thin or one-sided; answer should focus on what is known and what to verify.
- **blocked** — policy/access/source constraints prevent answering.

Implementation-level verifier verdicts:

- `PASS` — supported enough to answer normally.
- `PASS_WITH_WARNINGS` — answerable, but caveats or weak areas must be visible.
- `REWRITE_REQUIRED` — retrieved evidence is not enough for the current draft; revise before delivery.
- `FAIL_CLOSED` — do not send a normal answer because evidence, access policy, or safety gates failed.

A practical mapping is:

```text
strong  -> PASS
review  -> PASS_WITH_WARNINGS or REWRITE_REQUIRED
weak    -> REWRITE_REQUIRED
blocked -> FAIL_CLOSED
```

The mapping is intentionally conservative. A user-facing answer should pass evidence support, source authority, and access-policy checks before it is delivered as a confident response.

## Calculator/tool evidence

For sizing and math-heavy questions, deterministic tools should create the numeric evidence. The Evidence Ledger should then explain assumptions, limits, and source-backed caveats.

A safe pattern is:

```yaml
supported_claims:
  - source: storage calculator
    claim: Required usable capacity target maps to a specific sizing result under stated RF, resiliency, CPU, RAM, and per-node raw capacity assumptions.

answer_rules:
  - cite calculator assumptions before giving numeric recommendations
  - do not invent capacity numbers from prose-only retrieval
  - ask for missing workload assumptions when the calculator input is underspecified
```

Calculator output can be attached as evidence in report-only evaluation before it is wired into live serving.

## Why this works

The ledger creates a boundary between retrieval and writing. It makes the model answer questions like:

- Which source supports this sentence?
- What obligation is still missing?
- Should this be a confident answer or a review-mode answer?
- Are we using deterministic tools where needed?
- Did the verifier accept the answer or require a rewrite?

## Traceability and limits

For each claim, record a stable source identity, section or tool-result locator, applicable product/source version, and evidence scope. For calculations, include inputs, units, formula/tool version, and assumptions. A source-family label alone is not a checkable citation.

Bind the ledger to the current question and authorized tool results. Missing evidence means “not established by this evidence,” not “the vendor does not support it.” A verifier can miss errors or reject valid claims; measure both failures and require human review for high-impact decisions.
