"""The segmentation seam: line raster in, exact label map out.

Both implementations produce the same thing — an int32 label map where 0 is
line/protected and every other value is one region — so they are directly
comparable and swappable. §1.4 requires the stage be deterministic and exact;
it does not require it be ours.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from .trappedball import SegmentationParams, trapped_ball_segment

_VENDOR_DIR = Path(__file__).resolve().parents[3] / "third_party" / "LineFiller"


def _install_quiet_logger() -> None:
    """Pre-empt LineFiller's ``log.logger`` module.

    Importing it opens a FileHandler on ``./log/app.log`` relative to the
    working directory, so a vendored library decides where our process writes
    files and crashes if that path does not exist. Registering a silent
    stand-in under the same name first means the real one is never imported.
    """
    if "log.logger" in sys.modules:
        return

    import logging
    import types

    quiet = logging.getLogger("linefiller")
    quiet.addHandler(logging.NullHandler())
    quiet.setLevel(logging.WARNING)
    quiet.propagate = False

    package = types.ModuleType("log")
    module = types.ModuleType("log.logger")
    module.logger = quiet  # type: ignore[attr-defined]
    package.logger = module  # type: ignore[attr-defined]

    sys.modules["log"] = package
    sys.modules["log.logger"] = module


@runtime_checkable
class Segmenter(Protocol):
    @property
    def name(self) -> str: ...

    def segment(
        self,
        line_mask: np.ndarray,
        protected: np.ndarray | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> np.ndarray:
        """``line_mask`` True on ink. Returns an int32 label map, 0 = unassigned.

        ``progress(done, total)`` is called as each internal pass finishes.
        """
        ...


class TrappedBallSegmenter:
    """Our own implementation. Kept as the comparison baseline."""

    def __init__(self, params: SegmentationParams | None = None):
        self.params = params or SegmentationParams()

    @property
    def name(self) -> str:
        return "trappedball"

    def segment(
        self,
        line_mask: np.ndarray,
        protected: np.ndarray | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> np.ndarray:
        labels = trapped_ball_segment(line_mask, protected=protected, params=self.params)
        if progress is not None:
            progress(1, 1)
        return labels


class LineFillerSegmenter:
    """hepesu/LineFiller — MIT. The reference trapped-ball implementation.

    Two things it does that ours did not:

    - **It discards small fills at each radius rather than committing them.**
      ``method='max'`` keeps only the largest fill found at that radius,
      ``'mean'`` keeps those at or above the mean. Everything smaller is left
      unfilled for a smaller ball to claim. That is what stops a wide ball from
      shattering a thin corridor into one region per bulge: the bulges are
      small, so they are dropped rather than kept as regions.
    - **It merges afterwards** (``merge_fill``), absorbing tiny regions and
      those with a single neighbour into their surroundings.

    Radii and methods are paired positionally, largest first, following the
    upstream reference pipeline.
    """

    def __init__(
        self,
        radii: tuple[int, ...] = (3, 2, 1),
        methods: tuple[str, ...] = ("max", "mean", "mean"),
        merge: bool = True,
        merge_iterations: int = 10,
    ):
        if len(radii) != len(methods):
            raise ValueError("radii and methods must be the same length")
        self.radii = radii
        self.methods = methods
        self.merge = merge
        self.merge_iterations = merge_iterations
        self.last_timing: dict[str, float] = {}

    @property
    def name(self) -> str:
        return "linefiller" if self.merge else "linefiller_nomerge"

    @staticmethod
    def _load():
        if not _VENDOR_DIR.exists():
            raise FileNotFoundError(
                f"LineFiller not vendored at {_VENDOR_DIR}. "
                "git clone https://github.com/hepesu/LineFiller.git"
            )
        if str(_VENDOR_DIR) not in sys.path:
            sys.path.insert(0, str(_VENDOR_DIR))

        _install_quiet_logger()

        from linefiller import trappedball_fill  # type: ignore[import-not-found]

        return trappedball_fill

    def segment(
        self,
        line_mask: np.ndarray,
        protected: np.ndarray | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> np.ndarray:
        lf = self._load()
        # One pass per radius, then the flood, then the merge.
        passes = len(self.radii) + 2

        def passed(done: int) -> None:
            if progress is not None:
                progress(done, passes)

        # Upstream convention: uint8, 255 = unfilled area, 0 = line or filled.
        # Protected areas are handed over as line, so they are never filled and
        # come back as label 0 — the same contract as our own segmenter.
        image = np.full(line_mask.shape, 255, dtype=np.uint8)
        image[line_mask] = 0
        if protected is not None:
            image[protected] = 0

        started = time.perf_counter()
        fills: list = []
        result = image

        for done, (radius, method) in enumerate(zip(self.radii, self.methods), start=1):
            fill = lf.trapped_ball_fill_multi(result, radius, method=method)
            fills += fill
            result = lf.mark_fill(result, fill)
            passed(done)

        fills += lf.flood_fill_multi(result)
        ball_seconds = time.perf_counter() - started
        passed(passes - 1)

        fillmap = lf.build_fill_map(result, fills)

        merge_started = time.perf_counter()
        if self.merge:
            fillmap = lf.merge_fill(fillmap, max_iter=self.merge_iterations)
        merge_seconds = time.perf_counter() - merge_started
        passed(passes)

        self.last_timing = {
            "ball_seconds": round(ball_seconds, 2),
            "merge_seconds": round(merge_seconds, 2),
        }
        return np.ascontiguousarray(fillmap, dtype=np.int32)
