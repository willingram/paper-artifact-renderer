import json
from pathlib import Path

import pytest
from PIL import Image

from paper_artifact_renderer import verify
from paper_artifact_renderer.renderer import render_job

EXAMPLE_JOB = Path(__file__).resolve().parents[1] / "examples" / "minimal_job.json"


def write_sidecar(tmp_path: Path, *, images: object, pdf: object) -> None:
    job = json.loads(EXAMPLE_JOB.read_text(encoding="utf-8"))
    (tmp_path / "render.truth.json").write_text(
        json.dumps(
            {
                "job_snapshot": job,
                "page_count": 1,
                "images": images,
                "pdf": pdf,
            }
        ),
        encoding="utf-8",
    )


def test_pdf_render_check_reports_unavailable_poppler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify, "_find_pdftoppm", lambda: None)

    assert verify._verify_pdf_renders(Path("unused.pdf"), 1) is False


@pytest.mark.parametrize(
    ("poppler_checked", "expected", "forbidden"),
    (
        (True, "PDF renders 1 page(s) with Poppler", "PDF render check skipped"),
        (False, "PDF render check skipped (Poppler unavailable)", "page(s) with Poppler"),
    ),
)
def test_verify_report_truthfully_describes_poppler_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    poppler_checked: bool,
    expected: str,
    forbidden: str,
) -> None:
    render_job(EXAMPLE_JOB, tmp_path)
    monkeypatch.setattr(verify, "_verify_pdf_renders", lambda _path, _pages: poppler_checked)

    report = verify.verify_output(tmp_path)

    assert expected in report
    assert not any(forbidden in line for line in report)


@pytest.mark.parametrize(
    "value",
    (
        "",
        ".",
        "..",
        "../outside.jpg",
        "nested/page.jpg",
        r"nested\page.jpg",
        "/absolute.jpg",
        r"C:\absolute.jpg",
        "C:drive-relative.jpg",
        r"\\server\share\page.jpg",
        "trailing.",
        "trailing ",
        7,
        None,
    ),
)
def test_output_member_rejects_path_unsafe_or_malformed_references(tmp_path: Path, value: object) -> None:
    with pytest.raises(RuntimeError, match="path-safe basename"):
        verify._resolve_output_member(tmp_path, value, "test field")


@pytest.mark.parametrize(
    "images",
    (
        [""],
        ["../outside.jpg"],
        ["nested/page.jpg"],
        [r"nested\page.jpg"],
        [1],
    ),
)
def test_verify_rejects_malformed_image_references_before_parsing(tmp_path: Path, images: object) -> None:
    write_sidecar(tmp_path, images=images, pdf=None)

    with pytest.raises(RuntimeError, match=r"truth\.images\[0\].*path-safe basename"):
        verify.verify_output(tmp_path)


@pytest.mark.parametrize(
    "pdf",
    (
        "",
        "../outside.pdf",
        "nested/output.pdf",
        r"nested\output.pdf",
        1,
    ),
)
def test_verify_rejects_malformed_pdf_references_before_parsing(tmp_path: Path, pdf: object) -> None:
    Image.new("RGB", (2, 2)).save(tmp_path / "page_01.jpg")
    write_sidecar(tmp_path, images=["page_01.jpg"], pdf=pdf)

    with pytest.raises(RuntimeError, match=r"truth\.pdf.*path-safe basename"):
        verify.verify_output(tmp_path)


def test_output_member_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    link = out_dir / "page_01.jpg"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(RuntimeError, match="escapes output directory"):
        verify._resolve_output_member(out_dir, link.name, "truth.images[0]")
