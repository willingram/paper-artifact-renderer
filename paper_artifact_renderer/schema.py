from __future__ import annotations

from typing import Any


class SchemaError(ValueError):
    """Raised when a render job does not match the v1 schema."""


TOP_KEYS = {
    "seed",
    "style",
    "photo",
    "pdf",
    "table_style",
    "metadata_profile",
    "document_datetime",
    "pages",
}
STYLE_KEYS = {"pen", "handwriting_variant", "writer_drift", "paper"}
PHOTO_KEYS = {"long_edge_px", "skew_deg_range", "perspective", "lighting", "background"}
PDF_KEYS = {"filename", "text_layer"}
PAGE_KEYS = {"header_lines", "table", "annotations"}
TABLE_KEYS = {"columns", "rows"}
ANNOTATION_KEYS = {"text", "placement", "style"}


def reject_unknown(obj: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise SchemaError(f"{path}: unknown field(s): {', '.join(unknown)}")


def require_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{path}: expected object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaError(f"{path}: expected array")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{path}: expected string")
    return value


def validate_job(job: dict[str, Any]) -> None:
    reject_unknown(job, TOP_KEYS, "$")
    for key in ("seed", "style", "photo", "pages"):
        if key not in job:
            raise SchemaError(f"$: missing required field {key!r}")

    if not isinstance(job["seed"], int):
        raise SchemaError("$.seed: expected integer")

    style = require_dict(job["style"], "$.style")
    reject_unknown(style, STYLE_KEYS, "$.style")
    if style.get("pen") not in {"blue-ballpoint", "black-ballpoint", "pencil"}:
        raise SchemaError("$.style.pen: unsupported value")
    if style.get("handwriting_variant") not in {"print", "semi-cursive"}:
        raise SchemaError("$.style.handwriting_variant: unsupported value")
    if style.get("paper") not in {"ruled-a4-landscape", "ruled-a4-portrait", "plain-a4"}:
        raise SchemaError("$.style.paper: unsupported value")
    drift = style.get("writer_drift")
    if not isinstance(drift, (int, float)) or not 0 <= drift <= 1:
        raise SchemaError("$.style.writer_drift: expected number from 0 to 1")

    photo = require_dict(job["photo"], "$.photo")
    reject_unknown(photo, PHOTO_KEYS, "$.photo")
    if not isinstance(photo.get("long_edge_px"), int) or photo["long_edge_px"] < 1000:
        raise SchemaError("$.photo.long_edge_px: expected integer >= 1000")
    skew_range = require_list(photo.get("skew_deg_range"), "$.photo.skew_deg_range")
    if len(skew_range) != 2 or not all(isinstance(v, (int, float)) for v in skew_range):
        raise SchemaError("$.photo.skew_deg_range: expected [min, max]")
    if skew_range[0] < 0 or skew_range[1] < skew_range[0] or skew_range[1] > 8:
        raise SchemaError("$.photo.skew_deg_range: expected 0 <= min <= max <= 8")
    if photo.get("perspective") not in {"none", "slight"}:
        raise SchemaError("$.photo.perspective: unsupported value")
    if photo.get("lighting") not in {"indoor-varied"}:
        raise SchemaError("$.photo.lighting: unsupported value")
    if photo.get("background") not in {"workbench", "desk", "clipboard"}:
        raise SchemaError("$.photo.background: unsupported value")

    if "pdf" in job:
        pdf = require_dict(job["pdf"], "$.pdf")
        reject_unknown(pdf, PDF_KEYS, "$.pdf")
        require_string(pdf.get("filename"), "$.pdf.filename")
        if pdf.get("text_layer") is not False:
            raise SchemaError("$.pdf.text_layer: v1 only supports false")

    if job.get("table_style", "preprinted") not in {"preprinted", "hand-ruled"}:
        raise SchemaError("$.table_style: unsupported value")
    if job.get("metadata_profile", "phone-scan") not in {"phone-scan", "stripped"}:
        raise SchemaError("$.metadata_profile: unsupported value")
    if "document_datetime" in job:
        require_string(job["document_datetime"], "$.document_datetime")

    pages = require_list(job["pages"], "$.pages")
    if not pages:
        raise SchemaError("$.pages: expected at least one page")
    for page_index, page_value in enumerate(pages):
        page_path = f"$.pages[{page_index}]"
        page = require_dict(page_value, page_path)
        reject_unknown(page, PAGE_KEYS, page_path)
        headers = require_list(page.get("header_lines"), f"{page_path}.header_lines")
        if not headers or not all(isinstance(item, str) for item in headers):
            raise SchemaError(f"{page_path}.header_lines: expected non-empty string array")
        table = require_dict(page.get("table"), f"{page_path}.table")
        reject_unknown(table, TABLE_KEYS, f"{page_path}.table")
        columns = require_list(table.get("columns"), f"{page_path}.table.columns")
        rows = require_list(table.get("rows"), f"{page_path}.table.rows")
        if not columns or not all(isinstance(item, str) for item in columns):
            raise SchemaError(f"{page_path}.table.columns: expected non-empty string array")
        for row_index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(columns):
                raise SchemaError(
                    f"{page_path}.table.rows[{row_index}]: expected {len(columns)} cell(s)"
                )
            if not all(isinstance(item, str) for item in row):
                raise SchemaError(f"{page_path}.table.rows[{row_index}]: cells must be strings")
        annotations = require_list(page.get("annotations", []), f"{page_path}.annotations")
        for annotation_index, annotation_value in enumerate(annotations):
            annotation_path = f"{page_path}.annotations[{annotation_index}]"
            annotation = require_dict(annotation_value, annotation_path)
            reject_unknown(annotation, ANNOTATION_KEYS, annotation_path)
            require_string(annotation.get("text"), f"{annotation_path}.text")
            if annotation.get("placement") not in {"below-table", "margin-right", "across-blank-rows"}:
                raise SchemaError(f"{annotation_path}.placement: unsupported value")
            if annotation.get("style") not in {"normal", "emphatic"}:
                raise SchemaError(f"{annotation_path}.style: unsupported value")
