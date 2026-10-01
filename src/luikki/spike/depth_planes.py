"""§G0 spike: can depth and character masks split a page into planes?

Per panel, Depth Anything V2 Small gives relative depth (larger = nearer),
cut into three planes by k-means on its values; skytnt's anime-seg ISNet
gives a character mask. Both run on onnxruntime, both Apache-2.0. Renders go
to ``reports/depth/<page>/``, to be judged by eye — there is no ground truth
to count against.

    python -m luikki.spike.depth_planes MODELS_DIR [PAGE ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime

from ..segmentation.panels import segment_panels

# Plane 1 (nearest) warm, plane 3 (farthest) cool; characters magenta.
PLANE_TINTS = np.array([(60, 90, 235), (80, 200, 120), (230, 160, 60)], np.float32)
CHARACTER_TINT = np.array((200, 60, 200), np.float32)
_MEAN = np.array((0.485, 0.456, 0.406), np.float32)
_STD = np.array((0.229, 0.224, 0.225), np.float32)


def read_grey(path: Path) -> np.ndarray:
    # cv2.imread cannot open a non-ASCII path on Windows.
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_GRAYSCALE)


def depth(session, crop: np.ndarray, side: int = 518) -> np.ndarray:
    height, width = crop.shape
    scale = side / max(height, width)
    new_h = max(14, int(round(height * scale / 14)) * 14)
    new_w = max(14, int(round(width * scale / 14)) * 14)
    rgb = cv2.cvtColor(cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2RGB)
    batch = ((rgb / 255.0 - _MEAN) / _STD).transpose(2, 0, 1)[None].astype(np.float32)
    name = session.get_inputs()[0].name
    out = session.run(None, {name: batch})[0].reshape(new_h, new_w)
    return cv2.resize(out, (width, height), interpolation=cv2.INTER_LINEAR)


def characters(session, crop: np.ndarray, side: int = 1024) -> np.ndarray:
    height, width = crop.shape
    scale = side / max(height, width)
    new_h, new_w = int(height * scale), int(width * scale)
    canvas = np.zeros((side, side, 3), np.float32)
    top, left = (side - new_h) // 2, (side - new_w) // 2
    resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas[top:top + new_h, left:left + new_w] = cv2.cvtColor(resized, cv2.COLOR_GRAY2RGB) / 255.0
    name = session.get_inputs()[0].name
    out = session.run(None, {name: canvas.transpose(2, 0, 1)[None]})[0][0, 0]
    out = out[top:top + new_h, left:left + new_w]
    return cv2.resize(out, (width, height)) > 0.5


def planes(depth_map: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """0 = nearest, 2 = farthest, -1 outside the panel."""
    values = depth_map[inside].reshape(-1, 1).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1e-3)
    _, labels, centres = cv2.kmeans(values, 3, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    rank = np.argsort(-centres.ravel())  # largest depth value = nearest
    order = np.empty(3, int)
    order[rank] = np.arange(3)
    result = np.full(depth_map.shape, -1, np.int8)
    result[inside] = order[labels.ravel()]
    return result


def run_page(path: Path, depth_session, seg_session, out_dir: Path) -> None:
    grey = read_grey(path)
    _, ink = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    panels = segment_panels(ink.astype(bool))
    height, width = grey.shape
    depth_page = np.zeros((height, width), np.float32)
    plane_page = np.full((height, width), -1, np.int8)
    char_page = np.zeros((height, width), bool)
    for panel in panels:
        x, y, w, h = panel.x, panel.y, panel.width, panel.height
        inside = np.zeros((h, w), np.uint8)
        polygon = np.array(panel.polygon, np.int32) - (x, y)
        cv2.fillPoly(inside, [polygon], 1)
        inside = inside.astype(bool)
        crop = grey[y:y + h, x:x + w]
        d = depth(depth_session, crop)
        span = d[inside].max() - d[inside].min()
        normalised = (d - d[inside].min()) / (span or 1)
        depth_page[y:y + h, x:x + w][inside] = normalised[inside]
        plane_page[y:y + h, x:x + w][inside] = planes(d, inside)[inside]
        char_page[y:y + h, x:x + w] |= characters(seg_session, crop) & inside

    out_dir.mkdir(parents=True, exist_ok=True)
    line = (grey.astype(np.float32) / 255.0)[..., None]
    depth_render = cv2.applyColorMap((depth_page * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    _write(out_dir / "1_depth.png", depth_render * line)
    tinted = np.full((height, width, 3), 255, np.float32)
    for index in range(3):
        tinted[plane_page == index] = PLANE_TINTS[index]
    _write(out_dir / "2_planes.png", tinted * line)
    tinted[char_page] = CHARACTER_TINT
    _write(out_dir / "3_planes_characters.png", tinted * line)
    print(f"{path.name}: {len(panels)} panels, characters {char_page.mean():.1%} of page")


def _write(path: Path, image: np.ndarray) -> None:
    cv2.imencode(".png", np.clip(image, 0, 255).astype(np.uint8))[1].tofile(str(path))


def main() -> None:
    models = Path(sys.argv[1])
    pages = [Path(p) for p in sys.argv[2:]]
    options = onnxruntime.SessionOptions()
    depth_session = onnxruntime.InferenceSession(str(models / "depth_small.onnx"), options)
    seg_session = onnxruntime.InferenceSession(str(models / "isnetis.onnx"), options)
    for page in pages:
        run_page(page, depth_session, seg_session, Path("reports/depth") / page.stem)


if __name__ == "__main__":
    main()
