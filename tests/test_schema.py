import pytest

from paper_artifact_renderer.schema import SchemaError, validate_job


def minimal_job() -> dict:
    return {
        "seed": 1,
        "style": {
            "pen": "blue-ballpoint",
            "handwriting_variant": "print",
            "writer_drift": 0.25,
            "paper": "plain-a4",
        },
        "photo": {
            "long_edge_px": 1200,
            "skew_deg_range": [0, 1],
            "perspective": "none",
            "lighting": "indoor-varied",
            "background": "desk",
        },
        "pages": [
            {
                "header_lines": ["Example"],
                "table": {"columns": ["DATE", "OK"], "rows": [["01/04", "10"]]},
                "annotations": [],
            }
        ],
    }


def test_minimal_job_validates() -> None:
    validate_job(minimal_job())


def test_unknown_top_level_field_is_rejected() -> None:
    job = minimal_job()
    job["surprise"] = True

    with pytest.raises(SchemaError, match="unknown field"):
        validate_job(job)
