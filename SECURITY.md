# Security and publication issues

[Project home](README.md) · [Documentation index](docs/README.md) · [Contribution rules](CONTRIBUTING.md)

This repository distributes a design handbook and documentation tooling, not a running RAG service. No supported runtime versions or security guarantees are implied.

## Report without amplifying an exposure

Do not put credentials, restricted excerpts, customer information, internal endpoints, or exploit payloads in a public issue. Use GitHub private vulnerability reporting **if enabled** for this repository; otherwise request a private contact route from the maintainer without including the sensitive material. Do not assume a private reporting channel or response-time commitment exists.

A safe initial report identifies the affected public file and describes the class of problem without reproducing the payload. Keep detailed evidence in an authorized private channel. If a credential is exposed, its owner should revoke or rotate it through the appropriate security process; removing a file does not remove copies or Git history.

## Maintainer response

Pause publication of affected content, preserve restricted evidence privately, assess rights and exposure, and coordinate remediation with the owner. History rewriting, credential changes, and disclosure require explicit scope and authorization. Revalidate links and safety checks after the fix; do not interpret a passing scanner as proof the incident is resolved.
