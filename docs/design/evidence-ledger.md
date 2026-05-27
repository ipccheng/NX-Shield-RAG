# Evidence-Ledger Answering

The Evidence Ledger is the most important design pattern in NX-Shield RAG.

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

```yaml
answer_obligations:
  - identify whether the replacement path is documented
  - list required configuration checks after hardware replacement
  - call out production-impacting risks

supported_claims:
  - source: Hardware Admin Guide
    claim: NIC replacement requires validating host networking after physical change.
  - source: Prism networking docs
    claim: Uplink/vSwitch mappings may need to be reviewed after NIC changes.

weak_or_missing_claims:
  - exact Broadcom-to-Intel replacement certification evidence was not found
  - customer-specific firmware/driver compatibility is not proven by retrieved docs

answer_rules:
  - do not state the exact replacement is certified unless evidence says so
  - provide a pre-change and post-change checklist
  - mark production-impacting steps as requiring maintenance planning
```

## Verdicts

Use verdicts to decide answer posture:

- **strong** — enough direct, authoritative evidence to answer normally.
- **review** — useful evidence exists, but production impact or partial evidence requires caution.
- **weak** — evidence is thin or one-sided; answer should focus on what is known and what to verify.
- **blocked** — policy/access/source constraints prevent answering.

## Why this works

The ledger creates a boundary between retrieval and writing. It makes the model answer questions like:

- Which source supports this sentence?
- What obligation is still missing?
- Should this be a confident answer or a review-mode answer?
- Are we using deterministic tools where needed?

## Implementation notes

In the private source bundle, this pattern maps mainly to the active RAG search script and answer-formatting path:

```text
ipccheng/NX-Shield-RAG-src
└── rag/hermes-nutanix/scripts/openclaw/nutanix_rag_search.py
```

The exact implementation can change, but the public design contract should remain stable: **the final answer must be traceable to evidence and rules.**
