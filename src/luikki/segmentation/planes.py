"""§G2 Depth planes: which zones are near, which are far.

Per panel, Depth Anything V2 Small (Apache-2.0, onnxruntime) reads relative
depth off the artist's page; its values are cut into three groups; every zone
takes the group that dominates under its pixels. The depth map itself never
draws a boundary: its edges are soft and do not follow the ink (`reports/
depth/`), so the zones — cut on the line — stay the only geometry, and a plane
is a label on a zone.

Three planes, the trade's norm: 1st plane, 2nd plane, background. A fourth
label, `CHARACTER`, exists only because the artist puts it on zones: no model
is asked who is a character (anime-seg missed every character of the Tintin
page and took a machine for one).
"""

from __future__ import annotations

import cv2
import numpy as np

from ..model.masks import UNASSIGNED

NEAR, MIDDLE, FAR, CHARACTER = 0, 1, 2, 3
PLANES = (NEAR, MIDDLE, FAR, CHARACTER)

# The side the model reads, in pixels, on the panel's long side. 518 is what it
# was trained at (37 patches of 14), and what G0 was judged on.
DEPTH_SIDE = 518
_MEAN = np.array((0.485, 0.456, 0.406), np.float32)
_STD = np.array((0.229, 0.224, 0.225), np.float32)


class DepthEstimator:
    """Depth Anything V2 Small on onnxruntime. Larger values are nearer."""

    def __init__(self, model=None):
        from ..models import DEPTH, model_file

        self.model = model or model_file(DEPTH)
        self._session = None

    def _run(self, batch: np.ndarray) -> np.ndarray:
        if self._session is None:
            import onnxruntime

            from ..extract.manga_line import best_providers

            self._session = onnxruntime.InferenceSession(
                str(self.model), providers=best_providers()
            )
        name = self._session.get_inputs()[0].name
        return self._session.run(None, {name: batch})[0]

    def depth(self, crop: np.ndarray) -> np.ndarray:
        """Relative depth of a greyscale crop, at the crop's own size."""
        height, width = crop.shape
        scale = DEPTH_SIDE / max(height, width)
        # Both sides a multiple of the model's 14-pixel patch.
        new_h = max(14, int(round(height * scale / 14)) * 14)
        new_w = max(14, int(round(width * scale / 14)) * 14)
        small = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_GRAY2RGB).astype(np.float32) / 255.0
        batch = ((rgb - _MEAN) / _STD).transpose(2, 0, 1)[None].astype(np.float32)
        out = self._run(batch).reshape(new_h, new_w)
        return cv2.resize(out, (width, height), interpolation=cv2.INTER_LINEAR)


def depth_groups(depth: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """Three planes from one panel's depth: NEAR, MIDDLE, FAR, or -1 outside.

    A one-dimensional k-means over the panel's own values, so a panel is near
    or far against itself and never against the page. Started from the
    quantiles rather than from random centres: the same page gives the same
    planes on every run. A panel with no relief (a close-up) still gets three
    groups — the artist sees it and moves the zones.
    """
    values = depth[inside].astype(np.float64)
    result = np.full(depth.shape, -1, np.int8)
    if values.size == 0:
        return result
    centres = np.quantile(values, (1 / 6, 1 / 2, 5 / 6))
    for _ in range(30):
        nearest = np.abs(values[:, None] - centres[None, :]).argmin(axis=1)
        moved = np.array(
            [values[nearest == k].mean() if (nearest == k).any() else centres[k] for k in range(3)]
        )
        if np.allclose(moved, centres):
            break
        centres = moved
    nearest = np.abs(values[:, None] - centres[None, :]).argmin(axis=1)
    # Larger depth is nearer: the highest centre is the 1st plane.
    rank = np.empty(3, np.int8)
    rank[np.argsort(-centres)] = np.arange(3)
    result[inside] = rank[nearest]
    return result


def vote(label_map: np.ndarray, groups: np.ndarray) -> dict[int, int]:
    """Each zone's plane: the one most of its pixels fall in, never an average.

    A floor running from the background to the foreground would average into
    the middle. A zone is never split: it is one thing to the artist, and it
    stays in one layer. Pixels with no zone (balloons, spot blacks, outside
    the panel) do not vote.
    """
    voting = (label_map != UNASSIGNED) & (groups >= 0)
    labels = label_map[voting].astype(np.int64)
    if labels.size == 0:
        return {}
    counts = np.bincount(labels * 3 + groups[voting], minlength=(int(labels.max()) + 1) * 3)
    counts = counts.reshape(-1, 3)
    present = np.flatnonzero(counts.sum(axis=1))
    return {int(label): int(counts[label].argmax()) for label in present}


def panel_planes(
    estimator: DepthEstimator,
    grey: np.ndarray,
    label_map: np.ndarray,
    inside: np.ndarray,
) -> tuple[dict[int, int], np.ndarray]:
    """One panel, from its crop to `zone -> plane`, and the depth groups it
    was voted on: kept, so a zone cut or merged later votes again."""
    groups = depth_groups(estimator.depth(grey), inside)
    return planes_from(label_map, groups), groups


def planes_from(label_map: np.ndarray, groups: np.ndarray) -> dict[int, int]:
    """Every zone's plane by vote. Every zone gets one."""
    planes = vote(label_map, groups)
    # A zone whose every pixel fell outside the polygon still needs a layer.
    for label in np.unique(label_map):
        if int(label) != UNASSIGNED:
            planes.setdefault(int(label), FAR)
    return planes

