from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from . import __version__
from .renderer import render_to_temp
from .schema import validate_job

PDF_BYTE_DENYLIST = [
    b"paper-artifact-renderer",
    b"paper_artifact_renderer",
    __version__.encode("ascii"),
    b"reportlab",
    b"pillow",
    b"pil",
    b"pypdf",
    b"fpdf",
    b"pdfkit",
    b"weasyprint",
    b"cairo",
]


def verify_output(out_dir: Path) -> list[str]:
    out_dir = out_dir.resolve()
    sidecars = sorted(out_dir.glob("*.truth.json"))
    if len(sidecars) != 1:
        raise RuntimeError(f"expected exactly one *.truth.json in {out_dir}, found {len(sidecars)}")
    sidecar_path = sidecars[0]
    with sidecar_path.open("r", encoding="utf-8") as handle:
        truth = json.load(handle)

    job = truth.get("job_snapshot")
    if not isinstance(job, dict):
        raise RuntimeError("truth sidecar is missing job_snapshot")
    validate_job(job)

    report: list[str] = []
    images = truth.get("images")
    if not isinstance(images, list) or len(images) != truth.get("page_count"):
        raise RuntimeError("truth sidecar image list does not match page_count")
    for image_name in images:
        image_path = out_dir / image_name
        if not image_path.exists():
            raise RuntimeError(f"missing image {image_name}")
        with Image.open(image_path) as image:
            image.verify()
        report.append(f"decoded {image_name}")

    pdf_name = truth.get("pdf")
    if pdf_name:
        _verify_pdf_no_text(out_dir / pdf_name, len(images))
        metadata = _verify_pdf_metadata(out_dir / pdf_name)
        poppler_checked = _verify_pdf_renders(out_dir / pdf_name, len(images))
        report.append(f"PDF {pdf_name} parses with zero extractable text")
        report.append(f"PDF metadata acceptable: {metadata}")
        if poppler_checked:
            report.append(f"PDF renders {len(images)} page(s) with Poppler")
        else:
            report.append("PDF render check skipped (Poppler unavailable)")

    temp, fresh_manifest = render_to_temp(job)
    try:
        fresh_out = Path(temp.name)
        expected_names = list(images)
        if pdf_name:
            expected_names.append(pdf_name)
        expected_names.append(sidecar_path.name)
        for name in expected_names:
            current = out_dir / name
            fresh = fresh_out / name
            if not fresh.exists():
                raise RuntimeError(f"determinism re-render did not create {name}")
            if not filecmp.cmp(current, fresh, shallow=False):
                raise RuntimeError(f"determinism check failed for {name}")
        report.append(f"determinism byte-compare passed for {len(expected_names)} file(s)")
    finally:
        temp.cleanup()

    return report


def _verify_pdf_no_text(pdf_path: Path, expected_pages: int) -> None:
    if not pdf_path.exists():
        raise RuntimeError(f"missing PDF {pdf_path.name}")

    import pdfplumber
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    if len(reader.pages) != expected_pages:
        raise RuntimeError(f"pypdf page count {len(reader.pages)} != expected {expected_pages}")
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            raise RuntimeError(f"pypdf extracted text from page {index}: {text[:80]!r}")

    with pdfplumber.open(str(pdf_path)) as pdf:
        if len(pdf.pages) != expected_pages:
            raise RuntimeError(f"pdfplumber page count {len(pdf.pages)} != expected {expected_pages}")
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                raise RuntimeError(f"pdfplumber extracted text from page {index}: {text[:80]!r}")


def _verify_pdf_metadata(pdf_path: Path) -> dict[str, str]:
    import pdfplumber

    data = _pdf_bytes_outside_streams(pdf_path.read_bytes()).lower()
    hits = [item.decode("ascii", "ignore") for item in PDF_BYTE_DENYLIST if item and item.lower() in data]
    if hits:
        raise RuntimeError(f"PDF byte stream contains library/tool fingerprint(s): {', '.join(hits)}")

    with pdfplumber.open(str(pdf_path)) as pdf:
        metadata = {str(key): str(value) for key, value in (pdf.metadata or {}).items()}
    for key, value in metadata.items():
        lowered = value.lower()
        metadata_hits = [
            item.decode("ascii", "ignore")
            for item in PDF_BYTE_DENYLIST
            if item and item.lower().decode("ascii", "ignore") in lowered
        ]
        if metadata_hits:
            raise RuntimeError(
                f"PDF metadata field {key!r} contains library/tool fingerprint(s) {', '.join(metadata_hits)}: {value!r}"
            )
        if value.startswith("D:2000"):
            raise RuntimeError(f"PDF metadata field {key!r} has invariant test date: {value!r}")
    if metadata and not any("2026" in value for value in metadata.values()):
        raise RuntimeError(f"PDF metadata does not contain an in-world 2026 date: {metadata!r}")
    return metadata


def _verify_pdf_renders(pdf_path: Path, expected_pages: int) -> bool:
    pdftoppm = _find_pdftoppm()
    if not pdftoppm:
        return False
    with tempfile.TemporaryDirectory(prefix="paper_artifact_pdf_render_") as temp_dir:
        prefix = str(Path(temp_dir) / "page")
        result = subprocess.run(
            [
                pdftoppm,
                "-r",
                "36",
                "-f",
                "1",
                "-l",
                str(expected_pages),
                "-png",
                str(pdf_path),
                prefix,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"Poppler failed to render PDF streams: {detail}")
        rendered = sorted(Path(temp_dir).glob("page-*.png"))
        if len(rendered) != expected_pages:
            raise RuntimeError(f"Poppler rendered {len(rendered)} page(s), expected {expected_pages}")
    return True


def _find_pdftoppm() -> str | None:
    found = shutil.which("pdftoppm")
    if not found:
        return None
    path = Path(found)
    if path.suffix.lower() == ".cmd":
        bundled_exe = path.parent.parent / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe"
        if bundled_exe.exists():
            return str(bundled_exe)
    return found


def _pdf_bytes_outside_streams(data: bytes) -> bytes:
    lower = data.lower()
    output: list[bytes] = []
    position = 0
    while True:
        stream_start = lower.find(b"stream", position)
        if stream_start < 0:
            output.append(data[position:])
            return b"".join(output)
        output.append(data[position:stream_start])
        stream_end = lower.find(b"endstream", stream_start)
        if stream_end < 0:
            return b"".join(output)
        position = stream_end + len(b"endstream")
