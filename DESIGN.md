# Paper Artifact Renderer Design

## Purpose and boundaries

Paper Artifact Renderer (PAR) is an offline command-line tool that turns a
validated JSON job into photographed-paper-style JPEG pages, an optional
image-only PDF, and a truth sidecar. It can then verify those artifacts by
decoding and parsing them, checking selected PDF properties, and rerendering the
embedded job.

PAR is not a document-authenticity system, a sandbox for hostile files, a
transactional file writer, or a cross-platform byte-reproducibility guarantee.

## Components

- `paper_artifact_renderer.cli` defines the command-line interface.
- `paper_artifact_renderer.schema` validates the v1 job object.
- `paper_artifact_renderer.renderer` creates JPEG, PDF, and truth artifacts.
- `paper_artifact_renderer.verify` validates an existing render directory.
- `scripts/inspect_distribution.py` validates release artifacts without
  publishing them.

The supported entry points are:

- `par` (preferred);
- `paper-artifact-renderer`;
- `python -m paper_artifact_renderer`.

Each exposes `--help`, `--version`, and two required subcommands:

- `render --job PATH --out DIRECTORY`;
- `verify --out DIRECTORY`.

Unhandled validation, parsing, rendering, filesystem, or subprocess errors cause
the command to fail; the CLI does not translate them into a separate stable
error-code taxonomy.

## Job contract

The Python validator in `schema.py` is the current canonical job contract.
Unknown fields are rejected at the top level and within recognized objects.

Required top-level fields:

- `seed`: integer used to seed deterministic variation.
- `style`: object containing:
  - `pen`: `blue-ballpoint`, `black-ballpoint`, or `pencil`;
  - `handwriting_variant`: `print` or `semi-cursive`;
  - `writer_drift`: number from zero through one;
  - `paper`: `ruled-a4-landscape`, `ruled-a4-portrait`, or `plain-a4`.
- `photo`: object containing:
  - `long_edge_px`: integer of at least 1000; there is no upper bound;
  - `skew_deg_range`: two numbers satisfying `0 <= min <= max <= 8`;
  - `perspective`: `none` or `slight`;
  - `lighting`: currently only `indoor-varied`;
  - `background`: `workbench`, `desk`, or `clipboard`.
- `pages`: a non-empty array of page objects.

Each page requires:

- a non-empty string array `header_lines`;
- a `table` with a non-empty string array `columns` and a `rows` array;
- each row must contain exactly one string per column.

`annotations` defaults to an empty array. Each annotation has string `text`,
placement `below-table`, `margin-right`, or `across-blank-rows`, and style
`normal` or `emphatic`.

Optional top-level fields:

- `table_style`: `preprinted` (default) or `hand-ruled`;
- `metadata_profile`: `phone-scan` (default) or `stripped`;
- `document_datetime`: a string. The schema checks only its type; ISO-like
  semantic parsing occurs later while rendering the PDF.
- `pdf`: an object with string `filename` and `text_layer`, which must be
  `false`. The schema checks the filename's type only. Rendering applies
  `Path(filename).name` using the host platform and writes that basename beneath
  the output directory.

The documented minimal contract is in `examples/minimal_job.json`.

## Rendering and output authority

The caller authorizes PAR to create the selected output directory and write
within it. Page images are named `page_01.jpg`, `page_02.jpg`, and so on. Without
a PDF, the truth file is `render.truth.json`. With a PDF, the truth file uses the
PDF stem plus `.truth.json`.

Existing files with generated names are overwritten. Unrelated files and stale
files from a larger previous render are retained. Rendering is not transactional:
JPEGs and the initial PDF are written directly, and a failure can leave partial
or mixed old/new output. Stable JSON uses a neighboring temporary file followed
by a move. Stripped-PDF handling also uses a temporary file for one stage, but
the complete output directory is not atomically replaced.

JPEG pages use deterministic renderer settings, including quality 92,
non-progressive output, and fixed subsampling. The optional PDF contains the
rendered page images and no intended text layer. The `phone-scan` profile assigns
phone-scan-style metadata and configured or default dates; `stripped` removes metadata
before the final fingerprint/date guard.

The truth sidecar contains the renderer name and version, a stable hash and full
snapshot of the job, page and output lists, approximate text coordinates, and
photo/render details. It is operational metadata, not a signature or proof of
authenticity. Because it embeds the job, job content should not contain secrets
or information that should not accompany the render.

## Determinism

The renderer derives page-specific pseudorandom streams from the job seed and
page number and writes stable JSON. `verify` rerenders the embedded job in a
temporary directory and byte-compares the expected JPEG, optional PDF, and truth
sidecar files.

Determinism is a same-environment property. Byte output can change with the
package version, Python version, Pillow and PDF-library versions, installed
fonts, font-selection results, operating system, and related runtime behavior.
The verifier demonstrates reproducibility in its current environment; it does
not promise identical bytes across those boundaries.

## Verification

`verify` resolves the selected output directory and requires exactly one
top-level `*.truth.json` sidecar. Sidecar, image, and PDF references must be
non-empty path-safe basenames: absolute paths, drive-qualified paths, nested
paths, both slash conventions, dot traversal, and resolved symlink/reparse
escapes are rejected. Resolved targets must remain beneath the output directory.

The verifier:

1. parses and validates the embedded job snapshot;
2. checks that the image list matches `page_count` and that every image decodes;
3. if a PDF is listed, checks page counts and absence of extractable text with
   both `pypdf` and `pdfplumber`;
4. checks PDF metadata and bytes outside streams for selected renderer/library
   fingerprints and invariant test dates;
5. if `pdftoppm` is discoverable, invokes it to render the expected pages and
   fails if the process cannot run, exits unsuccessfully, or yields the wrong
   page count;
6. if `pdftoppm` is unavailable, truthfully reports that the optional render
   check was skipped while retaining the other PDF checks;
7. rerenders and byte-compares the expected artifacts.

Poppler is the only runtime subprocess. It has no timeout. Unrelated files in the
output directory are ignored, except that multiple truth sidecars make selection
ambiguous and cause failure.

## Network, trust, and resource model

PAR makes no runtime network requests. It reads caller-selected JSON and output
paths, invokes in-process image/PDF libraries, and may invoke a locally installed
`pdftoppm`. Dependency installation is separate from runtime behavior.

The parser and renderer do not impose upper bounds on JSON file size, number of
pages, headers, rows or annotations, text length, or `long_edge_px`. Image and
PDF parsers operate in-process without PAR-level memory, CPU, recursion, or time
limits. Poppler has no PAR-enforced timeout. Large or hostile inputs can exhaust
resources or exercise vulnerabilities in Python or third-party parsers. Run
untrusted material in an appropriately isolated environment with external
resource controls.

## Distribution contract

The wheel is intentionally lean: importable package code plus standard metadata
and the license. It does not contain examples, tests, the inspector, or project
governance documents.

The source distribution contains the files required to rebuild and test the
project: package sources, metadata and manifest, README and license, the
distribution inspector, all tests, the documented minimal example, and
`CONTRIBUTING.md`, `CHANGELOG.md`, `DESIGN.md`, and `SECURITY.md`.

The inspector enforces normalized artifact names, safe archive paths, exact
entry points, required metadata, wheel `RECORD`, lean wheel contents, complete
source contents, and absence of common development residue, generated outputs,
credential-like files, and local-machine markers.

Wheel `METADATA` and source-distribution `PKG-INFO` must each contain exactly the
canonical Homepage, Repository, Issues, and Changelog project links declared in
`pyproject.toml`. Missing, changed, extra, malformed, or duplicate labels fail
artifact inspection.

CI runs Ruff and the tests on Ubuntu, Windows, and macOS with Python 3.11 and
3.14. A separate Ubuntu/Python 3.11 job builds the sdist and wheel, runs strict
Twine and the inspector, installs the wheel outside the checkout, checks every
entry point and import location, and performs a real render/verify cycle. These
checks validate artifacts; they do not publish, tag, or create a release.
