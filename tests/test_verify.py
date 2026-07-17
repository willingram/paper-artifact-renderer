from pathlib import Path

import pytest

from paper_artifact_renderer import verify
from paper_artifact_renderer.renderer import render_job

EXAMPLE_JOB = Path(__file__).resolve().parents[1] / "examples" / "minimal_job.json"


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
