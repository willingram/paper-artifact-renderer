# Changelog

This file records notable changes to Paper Artifact Renderer. Package metadata
currently declares version `0.1.0`; this changelog does not assert that a version
has been tagged, released, or published to a package index.

## Unreleased

### Added

- Cross-platform CI for Python 3.11 and 3.14.
- Local wheel and source-distribution inspection, strict metadata checking, and
  isolated installed-wheel smoke tests.
- Project contribution, design, security, and changelog documentation.
- Canonical project links in wheel and source-distribution metadata, with exact
  artifact validation.

### Changed

- The preferred command is `par`, with `paper-artifact-renderer` and
  `python -m paper_artifact_renderer` retained as supported equivalent entry
  points.
- The verifier confines truth-sidecar, image, PDF, and determinism references to
  path-safe basenames that resolve beneath the selected output directory.

### Fixed

- Verification now reports whether optional Poppler PDF rendering was performed
  or skipped, rather than claiming it ran when `pdftoppm` was unavailable.
