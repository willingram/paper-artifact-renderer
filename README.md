# Paper Artifact Renderer

Offline command-line tool for rendering photographed, handwritten paper artifacts from a JSON job file.

It writes one JPEG per page, optionally combines those pages into an image-only PDF, and writes a `.truth.json` sidecar with the render inputs and approximate text coordinates. The verifier checks image/PDF readability, absence of extractable PDF text, absence of obvious library fingerprints in PDF metadata/outside-stream bytes, and deterministic re-rendering.

## Install

Use Python 3.11 or later.

With `uv`:

```sh
uv tool install .
paper-artifact-renderer --help
```

For editable development:

```sh
uv sync --extra dev
uv run paper-artifact-renderer --help
```

With `pip`:

```sh
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS, Linux, or WSL:

```sh
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Usage

Render the included example:

```sh
paper-artifact-renderer render --job examples/minimal_job.json --out outputs/example
paper-artifact-renderer verify --out outputs/example
```

The module entry point is equivalent:

```sh
python -m paper_artifact_renderer render --job examples/minimal_job.json --out outputs/example
python -m paper_artifact_renderer verify --out outputs/example
```

The renderer is deterministic for a given job, package version, Python/Pillow stack, and available fonts. On Windows it prefers Segoe Print. On macOS/Linux it falls back through common system fonts and then Pillow's built-in default font, so exact visual appearance can vary across operating systems.

## Job Format

Jobs are JSON objects with these main sections:

- `seed`: integer used for deterministic variation.
- `style`: paper, pen, handwriting variant, and writer drift settings.
- `photo`: output size, perspective/skew, lighting, and background.
- `pdf`: optional image-only PDF settings.
- `metadata_profile`: optional PDF metadata mode, either `phone-scan` or `stripped`.
- `document_datetime`: optional ISO-like timestamp used for PDF dates.
- `pages`: headers, table rows, and handwritten annotations for each page.

See [examples/minimal_job.json](examples/minimal_job.json) for a complete small job.

## Verification

`paper-artifact-renderer verify` expects a render directory containing exactly one `.truth.json` sidecar. It checks:

- every listed JPEG decodes;
- optional PDF parses with `pypdf` and `pdfplumber`;
- optional PDF has the expected page count and no extractable text layer;
- optional PDF metadata and outside-stream bytes do not contain common renderer/library identifiers;
- optional PDF renders through Poppler's `pdftoppm` when Poppler is installed;
- a fresh render from the embedded job snapshot byte-matches the current output.

Poppler is optional. Without it, PDF stream rendering is skipped; the other PDF checks still run.

Install Poppler separately if you want that extra check:

- Windows: install Poppler and put `pdftoppm.exe` on `PATH`.
- macOS: `brew install poppler`
- Debian/Ubuntu/WSL: `sudo apt-get install poppler-utils`

## Development

Common checks:

```sh
uv run --extra dev ruff check .
uv run --extra dev pytest
```

Build a distribution:

```sh
uv build
```

The package has no network dependency at runtime.
