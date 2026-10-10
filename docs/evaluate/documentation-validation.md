# Documentation validation

[Documentation index](../README.md) · [Project home](../../README.md) · [Contribution rules](../../CONTRIBUTING.md)

These checks validate the public handbook, **not** a RAG implementation, deployment, evaluation dataset, or benchmark. They require no model credentials or private corpus.

## Run locally

Use Python 3.11 or newer and an isolated tooling environment. From the repository root:

```sh
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install PyYAML==6.0.3
.venv-docs/bin/python -m unittest discover -s tools -p 'test_*.py' -v
.venv-docs/bin/python tools/validate_docs.py
git diff --check
```

For real Mermaid syntax parsing, use Node.js 22 or newer and a separate temporary dependency directory. Set `DOCS_NODE_ROOT` to that directory before running:

```sh
npm install --prefix "$DOCS_NODE_ROOT" --no-save --package-lock=false mermaid@11.12.0 jsdom@26.1.0
node tools/validate_mermaid.mjs "$DOCS_NODE_ROOT"
```

The [CI workflow](../../.github/workflows/docs.yml) runs the same gates for pushes and pull requests with read-only repository permissions and no deployment step. Dependencies are version-pinned; action references use fixed commit revisions. Changing these pins requires review. Local execution does not prove that hosted CI has run.

## What is checked

- Git-tracked and nonignored new files, including missing tracked files.
- Relative Markdown links and image assets, repository containment, and ordinary ATX-heading anchors.
- Fenced code block closure, documentation-index coverage, and return navigation.
- Python syntax, YAML files and fenced examples through a real parser, and SVG XML structure.
- Mermaid files and fenced Mermaid blocks through the actual Mermaid parser.
- Selected textual publication hazards, including personal home paths, private addresses/hostnames, and recognizable access tokens/private keys. Commercial model-provider names require editorial review.
- Byte equality of the canonical PNG and its compatibility copy.

## Limits and human review

The link checker supports this repository's inline links and reference definitions; it is not a complete Markdown renderer. Use ordinary headings and links rather than raw HTML, complex nested destinations, or generated anchors. External links are not fetched. Mermaid parsing is not visual rendering. PNG bytes are preserved and compared, not inspected for readability or sensitive pixels by this script.

Safety checks are heuristic, not a comprehensive secret detector or a license/endorsement review. All supported text files, including tooling, are scanned. Review every tooling diff manually as well. New file types also require human inspection. Check images and metadata when changing them, review claims against authorized evidence, and keep private review receipts outside this repository.

Preserve the first failed validation result before making a correction. Run the full checks again on the final tree and distinguish pre-existing issues, tooling defects, and introduced regressions. Do not label a partial or skipped gate as passed.
