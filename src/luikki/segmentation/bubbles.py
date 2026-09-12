"""§1.2 Frame as protection, not detection. Speech-bubble proposal.

D-22's rule -- *a bubble is text surrounded by white* -- was originally read
left to right: find the text with connected-component heuristics, flood-fill
outward from it, cap the area. That version was measured against the six real
test pages and it did not work, in a way no amount of tuning would fix:

* On `tintin_page.jpg` it returned 39 bubbles and not one of them was a
  balloon. The glyph filter keyed on the *page's* median component height,
  which on a scan is compression speckle -- 4 px where the lettering is 7 px.
  It therefore excluded the lettering and admitted the speckle.
* On `moebius_page.jpg` and `antoine_page.png`, which have no balloons at all,
  it read hatching as `iiii` and proposed bubbles around it. On
  `teddy_page.png` it read cup holders as `OOO`.
* On `laurine_page.jpg` it proposed a whole panel as one bubble.

Every one of those is the same failure: deciding "is this text?" from the
geometry of ink blobs. D-23's claim that height similarity plus a shared
baseline separates lettering from hatching is not true of real art.

So detection is now a model -- see `luikki.models.DETECTOR_URL`. This is the seam D-25
reserved for exactly this case ("if one is ever added it belongs behind an
optional seam distributing no restricted weights"), and the licence question
D-25 raised is answered rather than dodged: RT-DETR-v2 under Apache-2.0,
executed through `onnxruntime`, so no AGPL-licensed Ultralytics code enters
the chain. That last point rules out nearly every other comic bubble detector
on GitHub, whatever their model cards say, because they cannot run without
`ultralytics`.

Measured against the artist's own counts (`test_pages/bubble_counts.txt`) at
score >= 0.7: tintin 12/12, laurine 4/4, manga 4/4, and zero on all three
pages that have no balloons. The SFX lettering laurine is covered in -- Blop,
Pop, Hiii -- is correctly ignored.

D-24 (no SFX proposal this phase) still holds, but is now a decision rather
than a limitation: the model also returns a `text_free` class, which is
exactly SFX lettering outside balloons. Turning it on is a one-line change
whenever PROT-02's hand-drawing stops being enough.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..models import BUBBLE_DETECTOR, model_file

# The model's own class ids. `TEXT_IN_BUBBLE` and `TEXT_FREE` are unused today
# and named anyway, because the next person to open this file will want to
# know what else came back before they go looking for another model.
BUBBLE = 0
TEXT_IN_BUBBLE = 1
TEXT_FREE = 2

# The detector was exported at a fixed input size and resizes to it, so a
# 2048 px page costs exactly what a 600 px page costs: about 0.85 s on CPU.
_INPUT_SIZE = 640


@dataclass
class BubbleParams:
    # Detector confidence. Measured on the six test pages, every true balloon
    # scored 0.70-0.96 and the only two false positives scored below 0.5, so
    # this sits in a wide empty band rather than on a cliff.
    score: float = 0.7
    # Rays cast outward from the box centre to find the balloon's outline.
    rays: int = 128
    # How far past the box border a ray may look, as a multiple of the
    # distance from the centre to that border. The detector's box is tight on
    # the balloon, so this is slack for the outline stroke itself.
    reach: float = 1.15
    # Circular median window over the ray lengths. A ray that escapes through
    # a gap in the outline is a lone outlier and its neighbours out-vote it.
    # This is what makes a broken outline a non-event -- see `_trace`.
    smooth: int = 7
    # `approxPolyDP` tolerance as a fraction of contour perimeter, never a
    # fixed pixel constant (02-RESEARCH.md Pitfall 1).
    epsilon_frac: float = 0.008
    # A hard ceiling on returned polygons, so a pathological page cannot
    # produce an unbounded list (T-2-05).
    max_bubbles: int = 64


def model_path() -> Path:
    """Where the detector weights live (`luikki.models`).

    Never downloaded at launch: an installed app carries them, and a source
    checkout fetches them once with `luikki models`. 161 MB does not belong in
    git history, nor in the artist's first press of Detect bubbles.
    """
    return model_file(BUBBLE_DETECTOR)


class BubbleDetector:
    """The ONNX session, loaded once and reused.

    An object rather than a module global, so a test can point it at another
    file and so the app pays the load cost at startup rather than on the
    artist's first click.
    """

    def __init__(self, path: str | Path | None = None):
        import onnxruntime

        self.path = Path(path) if path else model_path()
        self.session = onnxruntime.InferenceSession(
            str(self.path), providers=["CPUExecutionProvider"]
        )

    def boxes(self, grey: np.ndarray, score: float) -> np.ndarray:
        """Bubble boxes as `(x0, y0, x1, y1)` in page coordinates.

        The export carries its own post-processing: it takes the original page
        size and returns boxes already scaled back to it.
        """
        height, width = grey.shape
        rgb = np.repeat(grey[:, :, None], 3, axis=2)
        resized = cv2.resize(
            rgb, (_INPUT_SIZE, _INPUT_SIZE), interpolation=cv2.INTER_LINEAR
        )
        tensor = (resized.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]

        labels, boxes, scores = self.session.run(
            None,
            {
                "images": tensor,
                "orig_target_sizes": np.array([[width, height]], dtype=np.int64),
            },
        )
        keep = (scores[0] >= score) & (labels[0] == BUBBLE)
        return boxes[0][keep]


def _ray_limits(angles: np.ndarray, half_width: float, half_height: float) -> np.ndarray:
    """Distance from the box centre to the box border, per angle."""
    cos, sin = np.cos(angles), np.sin(angles)
    with np.errstate(divide="ignore", invalid="ignore"):
        to_side = np.where(np.abs(cos) > 1e-9, half_width / np.abs(cos), np.inf)
        to_top = np.where(np.abs(sin) > 1e-9, half_height / np.abs(sin), np.inf)
    return np.minimum(to_side, to_top)


def trace_bubble(
    line_mask: np.ndarray, box: np.ndarray, params: BubbleParams | None = None
) -> list[tuple[int, int]]:
    """Radial trace of one balloon's outline, from the box the model gave.

    Cast `rays` rays outward from the centre of the box and keep, on each, the
    distance of the *furthest* ink pixel within reach. That is the balloon's
    outline: the lettering is always nearer the centre than the outline is, so
    text cannot be mistaken for the boundary and the polygon can never fold
    inward around it.

    This replaced a flood fill, and the reason is worth keeping. A balloon
    outline is often not closed at pixel level -- on `manga_page.jpg` it comes
    out of Otsu as a *dotted* line, with gaps on both sides and along the
    bottom. Anything that traces a closed curve fails there completely: an
    open outline is a `C`, and filling a `C` fills the stroke and leaves the
    middle out, which is where the old version's polygons that dived inward
    around the lettering came from. A ray does not care about topology. A gap
    costs one ray, and the circular median puts it back.

    The polygon lands *on* the outline rather than inside it, so the balloon
    border is protected and stays the artist's black.

    The result is star-shaped by construction, so it is always a simple
    polygon. The price is that a genuinely concave balloon -- one with a long
    tail -- is bridged rather than followed.
    """
    params = params or BubbleParams()
    x0, y0, x1, y1 = (float(v) for v in box)
    centre_x, centre_y = (x0 + x1) / 2, (y0 + y1) / 2
    half_width, half_height = (x1 - x0) / 2, (y1 - y0) / 2
    if half_width < 3 or half_height < 3:
        return []

    height, width = line_mask.shape
    # One pixel of dilation, so a ray stepping half a pixel at a time cannot
    # slip between the two sides of a hairline stroke.
    ink = cv2.dilate(line_mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)

    angles = np.linspace(0, 2 * np.pi, params.rays, endpoint=False)
    limits = _ray_limits(angles, half_width, half_height) * params.reach
    steps = np.arange(0.0, float(limits.max()) + 1.0, 0.5)

    # Every ray at every step, sampled in one indexing operation.
    xs = np.clip(
        (centre_x + np.outer(np.cos(angles), steps)).round().astype(int), 0, width - 1
    )
    ys = np.clip(
        (centre_y + np.outer(np.sin(angles), steps)).round().astype(int), 0, height - 1
    )
    hit = ink[ys, xs] & (steps[None, :] <= limits[:, None])

    # Furthest hit per ray; a ray that found no ink falls back to its limit.
    last = np.where(
        hit.any(axis=1), hit.shape[1] - 1 - hit[:, ::-1].argmax(axis=1), -1
    )
    radii = np.where(last >= 0, steps[last], limits)

    if params.smooth > 1:
        pad = params.smooth // 2
        wrapped = np.concatenate([radii[-pad:], radii, radii[:pad]])
        radii = np.array(
            [np.median(wrapped[i : i + params.smooth]) for i in range(params.rays)]
        )

    points = np.stack(
        [centre_x + radii * np.cos(angles), centre_y + radii * np.sin(angles)], axis=1
    )
    contour = points.round().astype(np.int32).reshape(-1, 1, 2)
    simplified = cv2.approxPolyDP(
        contour, params.epsilon_frac * cv2.arcLength(contour, True), True
    )
    if len(simplified) < 3:
        return []

    return [
        (int(np.clip(p[0][0], 0, width - 1)), int(np.clip(p[0][1], 0, height - 1)))
        for p in simplified
    ]


def detect_bubbles(
    grey: np.ndarray,
    line_mask: np.ndarray,
    params: BubbleParams | None = None,
    detector: BubbleDetector | None = None,
) -> list[list[tuple[int, int]]]:
    """One editable polygon per speech balloon, in page coordinates.

    The model says *where* a balloon is; the artwork says what *shape* it is.
    Keeping those two jobs apart is why a spiky balloon, a cloud balloon and a
    borderless caption all come out right -- nothing in the tracing step
    assumes a shape.

    Takes both `grey` and `line_mask` because they answer different questions:
    the model reads the page as the artist drew it, and the trace needs to
    know which pixels are ink.
    """
    params = params or BubbleParams()
    detector = detector or BubbleDetector()

    polygons: list[list[tuple[int, int]]] = []
    for box in detector.boxes(grey, params.score):
        if len(polygons) >= params.max_bubbles:
            break
        polygon = trace_bubble(line_mask, box, params)
        if polygon:
            polygons.append(polygon)
    return polygons
