# Example Query Obligations

[Documentation index](../docs/README.md) · [Project home](../README.md)

> **Scope:** Independent project design guidance, not a Nutanix-approved implementation. This page does not establish deployed behavior, measured effectiveness, or vendor support. The public repository does not include a runnable service.

## Reading this page

These are fictional question patterns, not retrieved vendor evidence, executed tests, or approved procedures. An **obligation** is a specific question the answer must address. **NIC** means network interface card; **RF** means replication factor; **FT** means fault tolerance. **AOS** refers to Nutanix storage software, and **Prism** to its management interfaces. Product/version-specific claims require authorized, current sources. Start with the [evidence-ledger design](../docs/design/evidence-ledger.md) and [fillable template](../templates/evidence-ledger-template.yaml).

## Hardware replacement / networking procedure

User asks whether a NIC can be replaced and what to configure afterward.

Obligations:

- identify exact hardware/support evidence,
- distinguish documented compatibility from inference,
- list pre-change checks,
- list post-change Prism/AOS/networking checks,
- mark production-impacting steps,
- disclose missing exact-match evidence.

## Competitive comparison

User asks to compare two platforms.

Obligations:

- retrieve evidence for both sides,
- identify source authority for each side,
- avoid claims about licensing/pricing/roadmap unless directly supported,
- disclose one-sided evidence,
- separate facts from positioning.

## Storage sizing

User asks how much usable capacity a cluster provides.

Obligations:

- run deterministic calculator path,
- state RF/FT/compression assumptions,
- use RAG for terminology and caveats,
- avoid hand-calculated numbers in prose without tool support.
