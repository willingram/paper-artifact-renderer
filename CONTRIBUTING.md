# Contributing to Paper Artifact Renderer

Thank you for improving Paper Artifact Renderer (PAR). Contributions should keep
the command-line interface, job format, generated artifacts, verifier, and
distribution behavior explicit and testable.

## Development setup

PAR requires Python 3.11 or later. The repository uses `uv` and commits its lock
file:

```sh
uv sync --extra dev --frozen
```

Run the supported commands through the synchronized environment:

```sh
uv run --frozen par --help
uv run --frozen pytest
```

## Making changes

Keep changes focused. Before a substantial behavioral or public-contract change,
open a discussion with the repository owner so the intended compatibility and
security consequences are clear.

Changes to any of the following require focused regression tests and matching
documentation:

- the `par`, `paper-artifact-renderer`, or module entry points;
- `render` or `verify` arguments and exit behavior;
- accepted job fields or validation rules;
- JPEG, PDF, or truth-sidecar names, contents, or determinism;
- verifier checks, path authority, or optional Poppler behavior;
- wheel or source-distribution contents.

Do not include generated renders, truth sidecars, credentials, private documents,
virtual environments, caches, or build artifacts in commits or fixtures. Use
small fictional examples.

## Quality checks

Run the complete local checks:

```sh
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest
```

If formatting is required, run `uv run --frozen ruff format .`, then review the
result before committing.

## Distribution validation

Remove an existing `dist` directory, then run:

```sh
uv run --frozen python -m build
uv run --frozen twine check --strict dist/*
uv run --frozen python scripts/inspect_distribution.py dist
```

These commands do not publish anything. The inspector enforces the repository's
lean-wheel and complete-source-distribution policies. For packaging changes,
also install the wheel in an environment outside the checkout and exercise all
entry points plus a real `render` and `verify` cycle.

## Pull-request checklist

- The change is focused and does not include unrelated formatting or cleanup.
- Public behavior and compatibility implications are documented.
- New behavior and failure cases have regression tests.
- Ruff, formatting, and the full test suite pass.
- Packaging changes pass build, strict Twine, inspection, and isolated-wheel
  validation.
- Examples and test data are fictional and contain no sensitive information.
