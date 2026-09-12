"""The app's icon, drawn from `favicon.svg`, so the logo has one source.

Pillow does not read SVG, and this one is two shapes: a path of straight lines
and one cubic curve, and a circle. That much is drawn here rather than adding
an SVG renderer to the build. Anything else in the file is refused, so a new
logo cannot be drawn wrong without a word.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]
# Drawn this large, then reduced for each size: the reduction is the antialiasing.
_CANVAS = 1024
_MARGIN = 0.03
_CURVE_POINTS = 48


def _path_points(d: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    command = ""
    tokens = re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?", d)
    i = 0
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
            if command not in "MLCZ":
                raise ValueError(f"path command {command!r} is not drawn by icon.py")
            continue
        if command in ("M", "L"):
            points.append((float(tokens[i]), float(tokens[i + 1])))
            i += 2
        elif command == "C":
            x0, y0 = points[-1]
            x1, y1, x2, y2, x3, y3 = map(float, tokens[i : i + 6])
            i += 6
            for step in range(1, _CURVE_POINTS + 1):
                t = step / _CURVE_POINTS
                u = 1 - t
                points.append(
                    (
                        u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
                        u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3,
                    )
                )
        else:
            raise ValueError(f"numbers after {command!r} in {d!r}")
    return points


def draw(svg: Path) -> Image.Image:
    """The logo on a transparent square, centred."""
    root = ElementTree.parse(svg).getroot()
    left, top, width, height = map(float, root.get("viewBox").split())
    scale = _CANVAS * (1 - 2 * _MARGIN) / max(width, height)
    dx = (_CANVAS - width * scale) / 2 - left * scale
    dy = (_CANVAS - height * scale) / 2 - top * scale

    image = Image.new("RGBA", (_CANVAS, _CANVAS), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    for element in root:
        tag = element.tag.rsplit("}", 1)[-1]
        fill = element.get("fill")
        if tag == "path":
            pen.polygon([(x * scale + dx, y * scale + dy) for x, y in _path_points(element.get("d"))], fill=fill)
        elif tag == "circle":
            cx, cy, r = (float(element.get(name)) for name in ("cx", "cy", "r"))
            pen.ellipse(
                [(cx - r) * scale + dx, (cy - r) * scale + dy, (cx + r) * scale + dx, (cy + r) * scale + dy],
                fill=fill,
            )
        else:
            raise ValueError(f"<{tag}> is not drawn by icon.py")
    return image


def write_icon(svg: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    draw(svg).save(out, sizes=[(size, size) for size in SIZES])
    return out
