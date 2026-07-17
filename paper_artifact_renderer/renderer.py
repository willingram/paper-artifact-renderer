from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import __version__
from .schema import validate_job

HAND_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/segoepr.ttf"),
    Path("C:/Windows/Fonts/comic.ttf"),
    Path("/System/Library/Fonts/Supplemental/Comic Sans MS.ttf"),
    Path("/System/Library/Fonts/Supplemental/Marker Felt.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
]
HAND_BOLD_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/segoeprb.ttf"),
    Path("C:/Windows/Fonts/comicbd.ttf"),
    Path("/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Marker Felt.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
]
FALLBACK_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
]


@dataclass(frozen=True)
class RenderPaths:
    truth_path: Path
    pdf_path: Path | None
    image_paths: list[Path]


def render_job(job_path: Path, out_dir: Path) -> dict[str, Any]:
    with job_path.open("r", encoding="utf-8") as handle:
        job = json.load(handle)
    validate_job(job)
    return render_job_data(job, out_dir)


def render_job_data(job: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    validate_job(job)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths_for_job(job, out_dir)

    seed = int(job["seed"])
    image_paths: list[Path] = []
    page_truth: list[dict[str, Any]] = []
    for index, page in enumerate(job["pages"], start=1):
        rng = random.Random(seed + index * 1009)
        image, truth = _render_page(job, page, index, rng)
        image_path = out_dir / f"page_{index:02d}.jpg"
        image.save(
            image_path,
            format="JPEG",
            quality=92,
            subsampling=1,
            optimize=False,
            progressive=False,
        )
        image_paths.append(image_path)
        truth["image"] = image_path.name
        page_truth.append(truth)

    if paths.pdf_path:
        _write_image_only_pdf(image_paths, paths.pdf_path, job)

    sidecar = {
        "renderer": "paper-artifact-renderer",
        "renderer_version": __version__,
        "job_sha256": _stable_json_sha256(job),
        "job_snapshot": job,
        "page_count": len(job["pages"]),
        "pdf": paths.pdf_path.name if paths.pdf_path else None,
        "images": [path.name for path in image_paths],
        "pages": page_truth,
    }
    _write_json_stable(paths.truth_path, sidecar)
    return {
        "page_count": len(image_paths),
        "pdf": str(paths.pdf_path) if paths.pdf_path else None,
        "truth": str(paths.truth_path),
        "images": [str(path) for path in image_paths],
    }


def render_to_temp(job: dict[str, Any]) -> tuple[tempfile.TemporaryDirectory[str], dict[str, Any]]:
    temp = tempfile.TemporaryDirectory(prefix="paper_artifact_verify_")
    manifest = render_job_data(job, Path(temp.name))
    return temp, manifest


def _paths_for_job(job: dict[str, Any], out_dir: Path) -> RenderPaths:
    pdf_path = None
    truth_name = "render.truth.json"
    if job.get("pdf"):
        pdf_name = Path(job["pdf"]["filename"]).name
        pdf_path = out_dir / pdf_name
        truth_name = f"{pdf_path.stem}.truth.json"
    return RenderPaths(out_dir / truth_name, pdf_path, [])


def _render_page(
    job: dict[str, Any], page: dict[str, Any], page_number: int, rng: random.Random
) -> tuple[Image.Image, dict[str, Any]]:
    paper_w, paper_h = _paper_size(job)
    paper = _make_paper(paper_w, paper_h, job, rng)
    draw = ImageDraw.Draw(paper)
    fonts = _fonts(job, page_number)
    pen = _pen_color(job["style"]["pen"])
    grid = (105, 126, 150, 160)

    elements: list[dict[str, Any]] = []
    margin_x = 120
    y = 78
    for line_index, line in enumerate(page["header_lines"]):
        size_key = "title" if line_index == 0 else "subtitle"
        jitter_x = rng.randint(-5, 5)
        jitter_y = rng.randint(-2, 2)
        bbox = _draw_hand_text(
            paper,
            (margin_x + jitter_x, y + jitter_y),
            line,
            fonts[size_key],
            pen,
            rng,
            jitter=0.8,
        )
        elements.append(
            {
                "type": "header",
                "line_index": line_index,
                "text": line,
                "paper_bbox": bbox,
            }
        )
        y += 58 if line_index == 0 else 46

    y += 18
    table_truth = _draw_table(
        surface=paper,
        draw=draw,
        page=page,
        table_style=job.get("table_style", "preprinted"),
        x=margin_x,
        y=y,
        w=paper_w - margin_x * 2,
        fonts=fonts,
        pen=pen,
        grid=grid,
        rng=rng,
    )
    elements.extend(table_truth["elements"])
    y = table_truth["bottom"] + 36

    for annotation_index, annotation in enumerate(page.get("annotations", [])):
        annotation_truth = _draw_annotation(
            surface=paper,
            draw=draw,
            annotation=annotation,
            annotation_index=annotation_index,
            x=margin_x + rng.randint(15, 45),
            y=y + rng.randint(-5, 15),
            max_w=paper_w - margin_x * 2,
            fonts=fonts,
            pen=pen,
            rng=rng,
        )
        elements.append(annotation_truth)
        y = annotation_truth["paper_bbox"][3] + 18

    _add_sparse_wear(paper, page_number, rng)
    photo, photo_truth = _photograph_page(paper, job, page_number, rng)

    return photo, {
        "page_number": page_number,
        "paper_size": [paper_w, paper_h],
        "photo_size": [photo.width, photo.height],
        "photo": photo_truth,
        "text_elements": elements,
    }


def _paper_size(job: dict[str, Any]) -> tuple[int, int]:
    paper = job["style"]["paper"]
    if paper == "ruled-a4-portrait":
        return (1697, 2400)
    if paper == "plain-a4":
        return (1697, 2400)
    return (2400, 1697)


def _make_paper(w: int, h: int, job: dict[str, Any], rng: random.Random) -> Image.Image:
    base = Image.new("RGBA", (w, h), _jitter_color((244, 241, 229, 255), rng, 5))
    draw = ImageDraw.Draw(base, "RGBA")

    if job["style"]["paper"].startswith("ruled") and job.get("table_style", "preprinted") != "preprinted":
        spacing = 56 + rng.randint(-2, 2)
        start = 190 + rng.randint(-5, 5)
        for y in range(start, h - 90, spacing):
            draw.line([(70, y), (w - 70, y)], fill=(104, 150, 188, 54), width=2)
        draw.line([(104, 90), (104, h - 78)], fill=(206, 103, 103, 62), width=2)

    _overlay_texture(base, rng, strength=5, alpha=6)
    return base


def _fonts(job: dict[str, Any], page_number: int) -> dict[str, ImageFont.FreeTypeFont]:
    drift = float(job["style"]["writer_drift"])
    variant_bump = 1 if job["style"]["handwriting_variant"] == "semi-cursive" else 0
    page_bump = int(math.sin(page_number * 1.7) * drift * 2)
    hand_candidates = HAND_FONT_CANDIDATES + FALLBACK_FONT_CANDIDATES
    bold_candidates = HAND_BOLD_FONT_CANDIDATES + hand_candidates
    return {
        "title": _load_font(bold_candidates, 46 + page_bump + variant_bump),
        "subtitle": _load_font(hand_candidates, 34 + page_bump),
        "header": _load_font(hand_candidates, 23 + page_bump),
        "typed_header": _load_font(FALLBACK_FONT_CANDIDATES, 25),
        "cell": _load_font(hand_candidates, 30 + page_bump),
        "note": _load_font(hand_candidates, 23 + page_bump),
        "annotation": _load_font(bold_candidates, 33 + page_bump),
    }


def _load_font(candidates: list[Path], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _pen_color(pen: str) -> tuple[int, int, int, int]:
    if pen == "black-ballpoint":
        return (31, 31, 35, 245)
    if pen == "pencil":
        return (82, 78, 74, 210)
    return (17, 62, 153, 242)


def _draw_table(
    *,
    surface: Image.Image,
    draw: ImageDraw.ImageDraw,
    page: dict[str, Any],
    table_style: str,
    x: int,
    y: int,
    w: int,
    fonts: dict[str, ImageFont.FreeTypeFont],
    pen: tuple[int, int, int, int],
    grid: tuple[int, int, int, int],
    rng: random.Random,
) -> dict[str, Any]:
    columns = page["table"]["columns"]
    rows = page["table"]["rows"]
    weights = []
    for column in columns:
        if column == "DATE":
            weights.append(1.18)
        elif column == "NOTES":
            weights.append(2.45)
        else:
            weights.append(1.05)
    total = sum(weights)
    widths = [int(w * weight / total) for weight in weights]
    widths[-1] += w - sum(widths)

    header_h = 62
    row_h = 86 if len(rows) <= 4 else 78
    table_h = header_h + len(rows) * row_h
    line_width = 3 if table_style == "preprinted" else 2

    x_positions = [x]
    for width in widths:
        x_positions.append(x_positions[-1] + width)

    if table_style == "preprinted":
        form_fill = (248, 247, 239, 255)
        draw.rectangle([x, y, x + w, y + table_h], fill=form_fill, outline=grid, width=line_width)
        for xx in x_positions[1:-1]:
            draw.line([(xx, y), (xx, y + table_h)], fill=grid, width=line_width)
        for yy in [y + header_h] + [y + header_h + row_h * i for i in range(1, len(rows))]:
            draw.line([(x, yy), (x + w, yy)], fill=grid, width=line_width)
    else:
        for xx in x_positions:
            draw.line(
                [(xx + rng.randint(-2, 2), y), (xx + rng.randint(-2, 2), y + table_h)],
                fill=grid,
                width=line_width,
            )
        for yy in [y, y + header_h] + [y + header_h + row_h * i for i in range(1, len(rows) + 1)]:
            draw.line(
                [(x, yy + rng.randint(-2, 2)), (x + w, yy + rng.randint(-2, 2))],
                fill=grid,
                width=line_width,
            )

    elements: list[dict[str, Any]] = []
    for col_index, column in enumerate(columns):
        cell_box = [x_positions[col_index], y, x_positions[col_index + 1], y + header_h]
        header_font = fonts["typed_header"] if table_style == "preprinted" else fonts["header"]
        tx, ty = _center_text(draw, cell_box, column, header_font)
        tx += rng.randint(-1, 1)
        ty += rng.randint(-1, 1)
        header_fill = (61, 70, 82, 205) if table_style == "preprinted" else pen
        if table_style == "preprinted":
            draw.text((tx, ty), column, font=header_font, fill=header_fill)
        else:
            _draw_hand_text(surface, (tx, ty), column, header_font, header_fill, rng, jitter=0.35)
        elements.append(
            {
                "type": "table_header",
                "column_index": col_index,
                "column": column,
                "text": column,
                "paper_bbox": cell_box,
            }
        )

    for row_index, row in enumerate(rows):
        row_y = y + header_h + row_index * row_h
        for col_index, value in enumerate(row):
            column = columns[col_index]
            cell_box = [x_positions[col_index], row_y, x_positions[col_index + 1], row_y + row_h]
            if value:
                if column == "NOTES":
                    tx = cell_box[0] + 14 + rng.randint(-3, 3)
                    ty = cell_box[1] + 22 + rng.randint(-3, 3)
                    font = fonts["note"]
                else:
                    tx, ty = _center_text(draw, cell_box, value, fonts["cell"])
                    tx += rng.randint(-5, 5)
                    ty += rng.randint(-2, 3)
                    font = fonts["cell"]
                bbox = _draw_hand_text(surface, (tx, ty), value, font, pen, rng, jitter=0.55)
            else:
                bbox = cell_box
            elements.append(
                {
                    "type": "cell",
                    "row_index": row_index,
                    "column_index": col_index,
                    "column": column,
                    "text": value,
                    "paper_bbox": bbox,
                    "cell_bbox": cell_box,
                }
            )

    return {"bottom": y + table_h, "elements": elements}


def _draw_annotation(
    *,
    surface: Image.Image,
    draw: ImageDraw.ImageDraw,
    annotation: dict[str, Any],
    annotation_index: int,
    x: int,
    y: int,
    max_w: int,
    fonts: dict[str, ImageFont.FreeTypeFont],
    pen: tuple[int, int, int, int],
    rng: random.Random,
) -> dict[str, Any]:
    font = fonts["annotation"] if annotation["style"] == "emphatic" else fonts["note"]
    lines = _wrap_text(draw, annotation["text"], font, max_w - 120)
    line_h = max(font.getbbox("Ag")[3] - font.getbbox("Ag")[1] + 14, 46)
    bboxes = []
    for index, line in enumerate(lines):
        tx = x + rng.randint(-4, 4)
        ty = y + index * line_h + rng.randint(-3, 3)
        bboxes.append(_draw_hand_text(surface, (tx, ty), line, font, pen, rng, jitter=0.65))
    bbox = [
        min(item[0] for item in bboxes),
        min(item[1] for item in bboxes),
        max(item[2] for item in bboxes),
        max(item[3] for item in bboxes),
    ]
    if annotation["style"] == "emphatic":
        underline_y = bbox[3] + 10
        draw.line([(bbox[0], underline_y), (bbox[2] + 20, underline_y + rng.randint(-1, 1))], fill=pen, width=4)
        draw.line([(bbox[0] + 8, underline_y + 10), (bbox[2] + 12, underline_y + 10)], fill=pen, width=3)
        bbox[3] += 18
    return {
        "type": "annotation",
        "annotation_index": annotation_index,
        "placement": annotation["placement"],
        "style": annotation["style"],
        "text": annotation["text"],
        "paper_bbox": bbox,
    }


def _photograph_page(
    paper: Image.Image, job: dict[str, Any], page_number: int, rng: random.Random
) -> tuple[Image.Image, dict[str, Any]]:
    long_edge = int(job["photo"]["long_edge_px"])
    paper_w, paper_h = paper.size
    if paper_w >= paper_h:
        paper = paper.resize((long_edge - 260, int((long_edge - 260) * paper_h / paper_w)), Image.Resampling.LANCZOS)
    else:
        paper = paper.resize((int((long_edge - 260) * paper_w / paper_h), long_edge - 260), Image.Resampling.LANCZOS)

    if job["photo"]["perspective"] == "slight":
        paper = _apply_perspective(paper, rng)

    skew_min, skew_max = job["photo"]["skew_deg_range"]
    angle = rng.uniform(skew_min, skew_max) * (-1 if page_number % 2 else 1)
    paper = paper.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))

    bg_w = long_edge
    bg_h = int(long_edge * 0.72) if paper_w >= paper_h else long_edge
    bg = _make_background(bg_w, bg_h, job["photo"]["background"], rng)

    shadow = Image.new("RGBA", paper.size, (0, 0, 0, 0))
    shadow_alpha = paper.getchannel("A").filter(ImageFilter.GaussianBlur(18))
    shadow.putalpha(shadow_alpha.point(lambda value: int(value * 0.22)))
    offset_x = (bg_w - paper.width) // 2 + rng.randint(-34, 34)
    offset_y = (bg_h - paper.height) // 2 + rng.randint(-24, 30)
    bg.alpha_composite(shadow, (offset_x + 18, offset_y + 22))
    bg.alpha_composite(paper, (offset_x, offset_y))

    bg = _apply_lighting(bg, rng)
    _overlay_texture(bg, rng, strength=5, alpha=6)
    bg = _apply_vignette(bg, rng)
    bg = bg.filter(ImageFilter.GaussianBlur(0.15))
    bg = ImageEnhance.Contrast(bg).enhance(1.02)
    if max(bg.size) != long_edge:
        scale = long_edge / max(bg.size)
        bg = bg.resize((int(bg.width * scale), int(bg.height * scale)), Image.Resampling.LANCZOS)
    return bg.convert("RGB"), {
        "skew_degrees": round(angle, 3),
        "page_bbox_approx": [offset_x, offset_y, offset_x + paper.width, offset_y + paper.height],
        "background": job["photo"]["background"],
    }


def _make_background(w: int, h: int, background: str, rng: random.Random) -> Image.Image:
    if background == "desk":
        base = _jitter_color((154, 130, 99, 255), rng, 7)
    elif background == "clipboard":
        base = _jitter_color((118, 95, 68, 255), rng, 7)
    else:
        base = _jitter_color((112, 103, 87, 255), rng, 7)
    image = Image.new("RGBA", (w, h), base)
    draw = ImageDraw.Draw(image, "RGBA")
    plank_w = rng.randint(280, 420)
    for x in range(-rng.randint(0, plank_w), w + plank_w, plank_w):
        color = _jitter_color((77, 71, 60, 34), rng, 14)
        draw.rectangle([x, -20, x + rng.randint(2, 5), h + 20], fill=color)
        highlight = _jitter_color((146, 132, 104, 16), rng, 12)
        draw.rectangle([x + 10, 0, x + 13, h], fill=highlight)
    for _ in range(38):
        x = rng.randint(0, w)
        y = rng.randint(0, h)
        length = rng.randint(80, 360)
        color = _jitter_color((68, 61, 51, rng.randint(14, 34)), rng, 12)
        draw.line(
            [(x, y), (x + length, y + rng.randint(-18, 18))],
            fill=color,
            width=rng.randint(1, 3),
        )
    _overlay_texture(image, rng, strength=10, alpha=14)
    return image


def _apply_lighting(image: Image.Image, rng: random.Random) -> Image.Image:
    image = image.convert("RGBA")
    w, h = image.size
    direction = rng.choice(("left", "right", "top-left", "bottom-right"))
    alpha_line = []
    for x in range(w):
        t = x / max(1, w - 1)
        if direction in {"right", "bottom-right"}:
            t = 1 - t
        alpha_line.append(int(8 + 28 * t))
    alpha = Image.new("L", (w, 1))
    alpha.putdata(alpha_line)
    alpha = alpha.resize((w, h), Image.Resampling.BILINEAR)
    overlay = Image.new("RGBA", (w, h), (255, 246, 224, 0))
    overlay.putalpha(alpha)
    return Image.alpha_composite(image, overlay)


def _apply_vignette(image: Image.Image, rng: random.Random) -> Image.Image:
    image = image.convert("RGBA")
    w, h = image.size
    vignette = Image.new("L", (w, h), 0)
    px = vignette.load()
    cx = w * rng.uniform(0.46, 0.54)
    cy = h * rng.uniform(0.46, 0.54)
    max_d = math.sqrt(cx * cx + cy * cy)
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / max_d
            value = int(max(0, min(42, (d - 0.35) * 58)))
            px[x, y] = value
    vignette = vignette.resize((w, h), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(16))
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shade.putalpha(vignette)
    return Image.alpha_composite(image, shade)


def _overlay_texture(image: Image.Image, rng: random.Random, *, strength: int, alpha: int) -> None:
    w, h = image.size
    small_w = max(80, w // 22)
    small_h = max(60, h // 22)
    values = [rng.randint(128 - strength, 128 + strength) for _ in range(small_w * small_h)]
    noise = Image.new("L", (small_w, small_h))
    noise.putdata(values)
    noise = noise.resize((w, h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(0.7))
    light = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    scale = alpha / max(1, strength)
    light.putalpha(noise.point(lambda value: int(max(0, value - 128) * scale)))
    dark.putalpha(noise.point(lambda value: int(max(0, 128 - value) * scale)))
    image.alpha_composite(light)
    image.alpha_composite(dark)


def _apply_perspective(image: Image.Image, rng: random.Random) -> Image.Image:
    w, h = image.size
    max_dx = int(w * 0.018)
    max_dy = int(h * 0.018)
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [
        (rng.randint(0, max_dx), rng.randint(0, max_dy)),
        (w - rng.randint(0, max_dx), rng.randint(0, max_dy)),
        (w - rng.randint(0, max_dx), h - rng.randint(0, max_dy)),
        (rng.randint(0, max_dx), h - rng.randint(0, max_dy)),
    ]
    coeffs = _perspective_coefficients(dst, src)
    return image.transform(
        (w, h),
        Image.Transform.PERSPECTIVE,
        coeffs,
        Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )


def _perspective_coefficients(points_a: list[tuple[int, int]], points_b: list[tuple[int, int]]) -> list[float]:
    matrix = []
    vector = []
    for (x, y), (u, v) in zip(points_a, points_b, strict=True):
        matrix.append([float(x), float(y), 1.0, 0.0, 0.0, 0.0, float(-u * x), float(-u * y)])
        matrix.append([0.0, 0.0, 0.0, float(x), float(y), 1.0, float(-v * x), float(-v * y)])
        vector.append(float(u))
        vector.append(float(v))
    return _solve_linear_system(matrix, vector)


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector, strict=True)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            raise RuntimeError("singular perspective transform")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        augmented[col] = [value / pivot_value for value in augmented[col]]
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            augmented[row] = [
                value - factor * pivot_value for value, pivot_value in zip(augmented[row], augmented[col], strict=True)
            ]
    return [augmented[row][-1] for row in range(n)]


def _add_sparse_wear(paper: Image.Image, page_number: int, rng: random.Random) -> None:
    draw = ImageDraw.Draw(paper, "RGBA")
    w, h = paper.size
    # Punch holes on most pages.
    if page_number % 3 != 0:
        for y in (h // 2 - 230, h // 2, h // 2 + 230):
            draw.ellipse([38, y - 22, 82, y + 22], fill=(226, 222, 210, 120), outline=(180, 174, 160, 82), width=2)
    # One or two mundane marks across a full job, deterministic by page.
    if page_number in {4, 9}:
        cx = rng.randint(w - 360, w - 190)
        cy = rng.randint(150, 300)
        draw.ellipse([cx - 86, cy - 55, cx + 86, cy + 55], outline=(126, 92, 58, 64), width=7)
        draw.ellipse([cx - 68, cy - 43, cx + 68, cy + 43], outline=(126, 92, 58, 32), width=3)
    if page_number % 5 == 0:
        corner = [(w - 120, h - 32), (w - 32, h - 32), (w - 32, h - 118)]
        draw.polygon(corner, fill=(218, 214, 202, 185), outline=(190, 184, 171, 130))
    for _ in range(2):
        x = rng.randint(260, w - 260)
        y = rng.randint(180, h - 180)
        draw.line([(x, y), (x + rng.randint(22, 75), y + rng.randint(-5, 8))], fill=(42, 54, 64, 22), width=rng.randint(2, 4))


def _write_image_only_pdf(image_paths: list[Path], pdf_path: Path, job: dict[str, Any]) -> None:
    from reportlab import rl_config
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    rl_config.invariant = 1
    first_size: tuple[int, int] | None = None
    page_sizes: list[tuple[int, int]] = []
    for image_path in image_paths:
        with Image.open(image_path) as image:
            size = image.size
        page_sizes.append(size)
        if first_size is None:
            first_size = size
    if first_size is None:
        raise RuntimeError("cannot create PDF with no images")

    pdf = canvas.Canvas(str(pdf_path), pagesize=first_size, pageCompression=1, invariant=1)
    pdf.setAuthor("")
    pdf.setCreator("Files")
    pdf.setProducer("iOS Version 18.4.1 Quartz PDFContext")
    pdf.setTitle(pdf_path.stem)
    pdf.setSubject("")
    pdf.setKeywords("")
    for image_path, (w, h) in zip(image_paths, page_sizes, strict=True):
        pdf.setPageSize((w, h))
        pdf.drawImage(ImageReader(str(image_path)), 0, 0, width=w, height=h, mask=None)
        pdf.showPage()
    pdf.save()
    profile = job.get("metadata_profile", "phone-scan")
    if profile == "stripped":
        _strip_pdf_metadata(pdf_path)
    else:
        _patch_pdf_dates_and_guard(pdf_path, _pdf_date_from_job(job))


def _center_text(draw: ImageDraw.ImageDraw, box: list[int], text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    return (
        int(box[0] + (box[2] - box[0] - text_w) / 2),
        int(box[1] + (box[3] - box[1] - text_h) / 2 - 2),
    )


def _text_bbox(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.FreeTypeFont) -> list[int]:
    bbox = draw.textbbox(xy, text, font=font)
    return [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]


def _draw_hand_text(
    surface: Image.Image,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    rng: random.Random,
    *,
    jitter: float,
) -> list[int]:
    x, y = xy
    cursor = float(x)
    boxes: list[list[int]] = []
    for char in text:
        advance = font.getlength(char)
        if char == " ":
            cursor += advance
            continue
        bbox = font.getbbox(char)
        cw = max(1, bbox[2] - bbox[0] + 10)
        ch = max(1, bbox[3] - bbox[1] + 12)
        glyph = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        glyph_draw = ImageDraw.Draw(glyph)
        ink = (
            max(0, min(255, fill[0] + rng.randint(-5, 5))),
            max(0, min(255, fill[1] + rng.randint(-5, 5))),
            max(0, min(255, fill[2] + rng.randint(-5, 5))),
            max(160, min(255, fill[3] + rng.randint(-10, 5))),
        )
        glyph_draw.text((5 - bbox[0], 5 - bbox[1]), char, font=font, fill=ink)
        angle = rng.uniform(-1.7, 1.7) * jitter
        if abs(angle) > 0.08:
            glyph = glyph.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))
        px = int(cursor + rng.uniform(-1.6, 1.6) * jitter)
        py = int(y + rng.uniform(-1.8, 1.8) * jitter)
        surface.alpha_composite(glyph, (px, py))
        boxes.append([px, py, px + glyph.width, py + glyph.height])
        cursor += advance + rng.uniform(-0.8, 0.9) * jitter
    if not boxes:
        return [x, y, x, y]
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if current and bbox[2] - bbox[0] > max_w:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def _jitter_color(color: tuple[int, int, int, int], rng: random.Random, amount: int) -> tuple[int, int, int, int]:
    r, g, b, a = color
    return (
        max(0, min(255, r + rng.randint(-amount, amount))),
        max(0, min(255, g + rng.randint(-amount, amount))),
        max(0, min(255, b + rng.randint(-amount, amount))),
        a,
    )


def _stable_json_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json_stable(path: Path, value: Any) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    shutil.move(str(temp_path), str(path))


def _patch_pdf_dates_and_guard(pdf_path: Path, pdf_date: str) -> None:
    data = pdf_path.read_bytes()
    invariant_date = b"D:20000101000000+00'00'"
    replacement = pdf_date.encode("ascii")
    if len(replacement) != len(invariant_date):
        raise RuntimeError("PDF date replacement must preserve byte length")
    data = data.replace(invariant_date, replacement)
    lowered = data.lower()
    replacements = {
        b"reportlab": b"QuartzPDF",
        b"pillow": b"imagex",
        b"pypdf": b"qscan",
        b"fpdf": b"scan",
        b"pil": b"img",
    }
    for needle, replacement in replacements.items():
        if len(needle) != len(replacement):
            raise RuntimeError(f"PDF scrub replacement length mismatch for {needle!r}")
        data = _replace_case_insensitive_bytes_outside_streams(data, needle, replacement)

    lowered = _pdf_bytes_outside_streams(data).lower()
    forbidden = [
        b"paper-artifact-renderer",
        b"paper_artifact_renderer",
        __version__.encode("ascii"),
        b"reportlab",
        b"pillow",
        b"pil",
        b"pypdf",
        b"fpdf",
    ]
    hits = [item.decode("ascii", "ignore") for item in forbidden if item and item.lower() in lowered]
    if hits:
        raise RuntimeError(f"PDF metadata/content contains renderer identifier(s): {', '.join(hits)}")
    pdf_path.write_bytes(data)


def _replace_case_insensitive_bytes_outside_streams(data: bytes, needle: bytes, replacement: bytes) -> bytes:
    lower = data.lower()
    output: list[bytes] = []
    position = 0
    while True:
        stream_start = lower.find(b"stream", position)
        if stream_start < 0:
            output.append(_replace_case_insensitive_bytes(data[position:], needle, replacement))
            return b"".join(output)

        output.append(_replace_case_insensitive_bytes(data[position:stream_start], needle, replacement))
        stream_end = lower.find(b"endstream", stream_start)
        if stream_end < 0:
            output.append(data[stream_start:])
            return b"".join(output)
        stream_end += len(b"endstream")
        output.append(data[stream_start:stream_end])
        position = stream_end


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


def _replace_case_insensitive_bytes(data: bytes, needle: bytes, replacement: bytes) -> bytes:
    lowered = data.lower()
    needle = needle.lower()
    start = 0
    chunks: list[bytes] = []
    while True:
        index = lowered.find(needle, start)
        if index < 0:
            chunks.append(data[start:])
            return b"".join(chunks)
        chunks.append(data[start:index])
        chunks.append(replacement)
        start = index + len(needle)


def _pdf_date_from_job(job: dict[str, Any]) -> str:
    value = job.get("document_datetime", "2026-04-15T14:26:00+01:00")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError(f"document_datetime must be ISO-like, got {value!r}") from exc
    offset = parsed.utcoffset() or dt.timedelta()
    sign = "+" if offset >= dt.timedelta() else "-"
    offset = abs(offset)
    hours = int(offset.total_seconds() // 3600)
    minutes = int((offset.total_seconds() % 3600) // 60)
    return (
        f"D:{parsed.year:04d}{parsed.month:02d}{parsed.day:02d}"
        f"{parsed.hour:02d}{parsed.minute:02d}{parsed.second:02d}"
        f"{sign}{hours:02d}'{minutes:02d}'"
    )


def _strip_pdf_metadata(pdf_path: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.metadata = None
    temp_path = pdf_path.with_suffix(".stripped.tmp.pdf")
    with temp_path.open("wb") as handle:
        writer.write(handle)
    shutil.move(str(temp_path), str(pdf_path))
    _patch_pdf_dates_and_guard(pdf_path, "D:20260415142600+01'00'")
