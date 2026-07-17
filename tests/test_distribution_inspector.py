import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.inspect_distribution import (  # noqa: E402
    EXPECTED_ENTRY_POINTS,
    Archive,
    distribution_paths,
    path_errors,
    residue_errors,
    sdist_errors,
    source_files,
    wheel_errors,
)


def archive(kind: str, names: tuple[str, ...]) -> Archive:
    return Archive(Path("artifact"), kind, names, {name: b"" for name in names})


def test_member_paths_reject_unsafe_and_nonportable_forms() -> None:
    errors = path_errors(
        (
            "../escape",
            "/absolute",
            "folder\\file",
            "C:/drive",
            "folder//file",
            "trailing.",
            "duplicate",
            "duplicate",
            "Package/module.py",
            "package/module.py",
        )
    )

    assert any("traversal" in error for error in errors)
    assert any("absolute" in error for error in errors)
    assert any("backslash" in error for error in errors)
    assert any("drive-qualified" in error for error in errors)
    assert any("non-portable segments" in error for error in errors)
    assert any("trailing character" in error for error in errors)
    assert any("duplicate member path" in error for error in errors)
    assert any("case-insensitive path collision" in error for error in errors)


def test_setuptools_egg_info_is_allowed_only_at_sdist_root() -> None:
    root = "paper_artifact_renderer-0.1.0"
    valid = archive("sdist", (f"{root}/paper_artifact_renderer.egg-info/PKG-INFO",))
    misplaced = archive(
        "sdist",
        (f"{root}/nested/paper_artifact_renderer.egg-info/PKG-INFO",),
    )

    assert residue_errors(valid, root) == []
    assert any("unexpected egg-info" in error for error in residue_errors(misplaced, root))


def test_rejects_generated_outputs_secrets_and_development_residue() -> None:
    candidate = archive(
        "wheel",
        (
            ".pytest_cache/state",
            "outputs/page_01.jpg",
            "render.truth.json",
            "credentials.json",
        ),
    )

    errors = residue_errors(candidate, "unused")
    assert any("forbidden development path" in error for error in errors)
    assert sum("forbidden file" in error for error in errors) >= 3


def test_sdist_requires_single_top_level_directory() -> None:
    root = "paper_artifact_renderer-0.1.0"
    candidate = archive("sdist", (f"{root}/README.md", "outside.txt"))

    assert any("outside its single top-level directory" in error for error in residue_errors(candidate, root))


def test_sdist_contract_requires_only_documented_minimal_example() -> None:
    assert source_files(ROOT, "examples") == {"examples/minimal_job.json"}
    candidate = archive("sdist", ())

    errors = sdist_errors(candidate, ROOT, "paper-artifact-renderer", "0.1.0")

    assert any("missing required sdist member: examples/minimal_job.json" in error for error in errors)


def test_distribution_filenames_require_setuptools_underscore_normalization(tmp_path: Path) -> None:
    (tmp_path / "paper_artifact_renderer-0.1.0-py3-none-any.whl").touch()
    incorrect_sdist = tmp_path / "paper-artifact-renderer-0.1.0.tar.gz"
    incorrect_sdist.touch()

    try:
        distribution_paths(tmp_path, "paper-artifact-renderer", "0.1.0")
    except ValueError as exc:
        assert "expected sdist filename paper_artifact_renderer-0.1.0.tar.gz" in str(exc)
    else:
        raise AssertionError("hyphen-normalized sdist name was accepted")

    incorrect_sdist.unlink()
    correct_sdist = tmp_path / "paper_artifact_renderer-0.1.0.tar.gz"
    correct_sdist.touch()
    wheel, sdist = distribution_paths(tmp_path, "paper-artifact-renderer", "0.1.0")
    assert wheel.name == "paper_artifact_renderer-0.1.0-py3-none-any.whl"
    assert sdist == correct_sdist


def test_par_entry_point_contract_is_exact() -> None:
    assert EXPECTED_ENTRY_POINTS == {
        "par": "paper_artifact_renderer.cli:main",
        "paper-artifact-renderer": "paper_artifact_renderer.cli:main",
    }


def test_wheel_rejects_files_outside_package_and_metadata() -> None:
    candidate = archive("wheel", ("examples/minimal_job.json",))

    errors = wheel_errors(candidate, ROOT, "paper-artifact-renderer", "0.1.0")
    assert any("unexpected wheel member: examples/minimal_job.json" in error for error in errors)
