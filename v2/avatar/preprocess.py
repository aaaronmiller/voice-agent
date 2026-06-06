"""Slice each sprite sheet into 9 viseme frames with transparent backgrounds.

The source sheets render onto a baked-in gray checker pattern, not real alpha.
We strip the checker with a corner-anchored flood-fill that walks any pixel
whose colour is close to one of the two checker tones, then save the cleaned
cell as ``frames/<character>/<VISEME>.png``.

Run directly to (re)build every character:

    .venv/bin/python -m v2.avatar.preprocess
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Iterable

import yaml
from PIL import Image

VISEMES: tuple[str, ...] = ("X", "A", "B", "C", "D", "E", "F", "G", "H")

# Two checker tones the image-gen tools draw, sampled across the available
# sheets. We accept any pixel within ``COLOUR_TOLERANCE`` of either one.
CHECKER_TONES: tuple[tuple[int, int, int], ...] = (
    (192, 192, 192),  # light gray
    (128, 128, 128),  # mid gray
    (102, 102, 102),  # darker variant some sheets use
    (224, 224, 224),  # lighter variant some sheets use
)
COLOUR_TOLERANCE = 28


def _near(p: tuple[int, int, int], ref: tuple[int, int, int]) -> bool:
    return (
        abs(p[0] - ref[0]) <= COLOUR_TOLERANCE
        and abs(p[1] - ref[1]) <= COLOUR_TOLERANCE
        and abs(p[2] - ref[2]) <= COLOUR_TOLERANCE
        and abs(max(p) - min(p)) <= 12  # checker is desaturated
    )


def _is_checker(p: tuple[int, int, int]) -> bool:
    return any(_near(p, ref) for ref in CHECKER_TONES)


def strip_checker(cell: Image.Image) -> Image.Image:
    """Flood-fill from each corner; any reachable checker-coloured pixel becomes
    transparent. The character is connected interior pixels and survives.
    """
    rgba = cell.convert("RGBA")
    w, h = rgba.size
    pixels = rgba.load()
    visited = bytearray(w * h)

    seeds: list[tuple[int, int]] = []
    for x in (0, w - 1):
        for y in (0, h - 1):
            seeds.append((x, y))
    # Also seed along the top/bottom/left/right edges every 24 px so a thick
    # checker border survives even when corners hit hair/tail strands.
    for x in range(0, w, 24):
        seeds.append((x, 0))
        seeds.append((x, h - 1))
    for y in range(0, h, 24):
        seeds.append((0, y))
        seeds.append((w - 1, y))

    queue: deque[tuple[int, int]] = deque()
    for sx, sy in seeds:
        if 0 <= sx < w and 0 <= sy < h and not visited[sy * w + sx]:
            r, g, b, _ = pixels[sx, sy]
            if _is_checker((r, g, b)):
                queue.append((sx, sy))

    while queue:
        x, y = queue.popleft()
        idx = y * w + x
        if visited[idx]:
            continue
        visited[idx] = 1
        r, g, b, _ = pixels[x, y]
        if not _is_checker((r, g, b)):
            continue
        pixels[x, y] = (r, g, b, 0)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny * w + nx]:
                queue.append((nx, ny))
    return rgba


def autocrop_alpha(img: Image.Image, padding: int = 4) -> Image.Image:
    """Crop to non-transparent content, with a small padding margin."""
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        return img
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - padding)
    y0 = max(0, y0 - padding)
    x1 = min(img.size[0], x1 + padding)
    y1 = min(img.size[1], y1 + padding)
    return img.crop((x0, y0, x1, y1))


def union_alpha_bbox(images: list[Image.Image], padding: int = 6) -> tuple[int, int, int, int]:
    """Compute one bbox that contains the non-transparent area of every image.
    All images must share the same size. Returns (x0, y0, x1, y1) clamped to
    the canvas with ``padding`` added on each side.
    """
    if not images:
        raise ValueError("union_alpha_bbox requires at least one image")
    w, h = images[0].size
    x0, y0, x1, y1 = w, h, 0, 0
    any_alpha = False
    for img in images:
        bbox = img.split()[-1].getbbox()
        if bbox is None:
            continue
        any_alpha = True
        bx0, by0, bx1, by1 = bbox
        x0 = min(x0, bx0)
        y0 = min(y0, by0)
        x1 = max(x1, bx1)
        y1 = max(y1, by1)
    if not any_alpha:
        return (0, 0, w, h)
    x0 = max(0, x0 - padding)
    y0 = max(0, y0 - padding)
    x1 = min(w, x1 + padding)
    y1 = min(h, y1 + padding)
    return (x0, y0, x1, y1)


def slice_grid(sheet: Image.Image, cols: int, rows: int) -> list[Image.Image]:
    w, h = sheet.size
    cell_w = w // cols
    cell_h = h // rows
    cells: list[Image.Image] = []
    for r in range(rows):
        for c in range(cols):
            box = (c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h)
            cells.append(sheet.crop(box))
    return cells


def build_character(name: str, spec: dict, base: Path) -> None:
    source = base / spec["source"]
    if not source.exists():
        raise FileNotFoundError(f"sprite source missing: {source}")
    grid = spec["grid"]
    cols, rows = int(grid["cols"]), int(grid["rows"])
    visemes: dict[str, int] = spec["visemes"]

    sheet = Image.open(source).convert("RGBA")
    cells = slice_grid(sheet, cols, rows)

    # First pass: chroma-key every cell we'll actually use. We may reuse the
    # same cell for multiple visemes (e.g. owl-wizard maps both F and E to
    # cell 5), so memoise by cell index.
    cleaned_by_index: dict[int, Image.Image] = {}
    for viseme in VISEMES:
        if viseme not in visemes:
            raise KeyError(f"{name}: viseme {viseme!r} missing in manifest")
        cell_index = visemes[viseme]
        if cell_index >= len(cells):
            raise IndexError(f"{name}: viseme {viseme} index {cell_index} out of range")
        if cell_index not in cleaned_by_index:
            cleaned_by_index[cell_index] = strip_checker(cells[cell_index])

    # Compute one shared bbox across every cleaned cell so the head stays
    # anchored when we swap visemes. Without this the center jitters because
    # an open mouth has a taller alpha bbox than a closed one.
    bbox = union_alpha_bbox(list(cleaned_by_index.values()), padding=8)

    out_dir = base / "frames" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    for viseme in VISEMES:
        cell_index = visemes[viseme]
        cropped = cleaned_by_index[cell_index].crop(bbox)
        cropped.save(out_dir / f"{viseme}.png", optimize=True)
    print(
        f"[avatar] built {len(VISEMES)} frames -> {out_dir} "
        f"(shared bbox {bbox[2] - bbox[0]}x{bbox[3] - bbox[1]})",
        flush=True,
    )


def build_all(only: Iterable[str] | None = None) -> None:
    base = Path(__file__).resolve().parent
    manifest = yaml.safe_load((base / "characters.yaml").read_text())
    only_set = set(only) if only else None
    for name, spec in manifest["characters"].items():
        if only_set is not None and name not in only_set:
            continue
        build_character(name, spec, base)


if __name__ == "__main__":
    args = sys.argv[1:]
    build_all(args if args else None)
