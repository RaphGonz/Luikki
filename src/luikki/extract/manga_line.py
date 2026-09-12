"""MangaLineExtraction wrapper — Li et al., *Deep Extraction of Manga
Structural Lines* (SIGGRAPH 2017). MIT licensed (P2, resolved).

The network's stated job is separating **structural** lines from **textural**
strokes: screentone, and hand-drawn hatching. That makes it a candidate
implementation of §7's Tier 3 hatching handler, not merely a convenience for
turning published pages into line art.

Two things to keep in mind when reading its output:

- It is a *manga* model. Franco-Belgian hatching (Moebius, Schuiten) is out of
  its training distribution, and there is no reason to assume the structural /
  textural boundary it learned transfers there. That is a hypothesis this
  wrapper exists to test, not an assumption it relies on.
- The output is soft greyscale, not a binary mask. The threshold applied
  afterwards moves the region count substantially, so it is a parameter of the
  experiment rather than an implementation detail.

The network runs on onnxruntime, from `manga_line.onnx`: the upstream
``erika.pth`` exported once by `luikki models` (`luikki/models.py`). That keeps
torch, and its gigabyte, out of the app an artist installs.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from ..models import MANGA_LINE, model_file
from .base import ExtractionResult

# The network downsamples five times, so both sides must be multiples of 16.
_STRIDE = 16

# In the order worth trying. onnxruntime reports only what its build can run:
# the stock wheel is CPU, `onnxruntime-gpu` adds CUDA, `onnxruntime-directml`
# adds DirectML (any Windows GPU).
_PREFERRED = ("CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider")


def best_providers() -> list[str]:
    """A GPU when this onnxruntime can use one, the CPU otherwise.

    The difference is seconds against minutes on a full page, and nothing else
    in the app needs a GPU, so this degrades rather than refuses.
    """
    import onnxruntime

    available = set(onnxruntime.get_available_providers())
    return [provider for provider in _PREFERRED if provider in available] or ["CPUExecutionProvider"]


class MangaLineExtractor:
    """The ``res_skip`` network on onnxruntime, over overlapping tiles.

    ``tile`` bounds peak memory and lets full-resolution studio pages (300dpi
    is routinely 3500x5000) run without a GPU. Tiles overlap and are feathered
    together; the seam is invisible at the thresholds we segment at, but the
    overlap must exceed the network's receptive field for that to hold, hence
    the generous default.
    """

    def __init__(
        self,
        model: str | Path | None = None,
        tile: int | None = 1024,
        overlap: int = 128,
        providers: list[str] | None = None,
    ):
        self.model = Path(model) if model else None
        self.tile = tile
        self.overlap = overlap
        self.providers = providers
        self._session = None
        self._input = ""

    @property
    def name(self) -> str:
        return "manga_line_extraction"

    def _load(self):
        if self._session is None:
            import onnxruntime

            self.model = self.model or model_file(MANGA_LINE)
            self._session = onnxruntime.InferenceSession(
                str(self.model), providers=self.providers or best_providers()
            )
            self._input = self._session.get_inputs()[0].name
        return self._session

    def _infer(self, batch: np.ndarray) -> np.ndarray:
        """One padded ``1x1xHxW`` float32 batch through the network.

        The only method that knows the runtime, so a comparison can put the
        upstream torch model in its place and keep everything around it.
        """
        return self._load().run(None, {self._input: batch})[0]

    def extract(
        self,
        grey: np.ndarray,
        progress: Callable[[int, int], None] | None = None,
    ) -> ExtractionResult:
        if grey.ndim != 2:
            raise ValueError("MangaLineExtractor expects a 2-D greyscale array")
        session = self._load()
        started = time.perf_counter()

        height, width = grey.shape
        use_tiling = self.tile is not None and max(height, width) > self.tile
        if use_tiling:
            lines = self._extract_tiled(grey, progress)
        else:
            lines = self._run(grey.astype(np.float32)).astype(np.uint8)
            if progress is not None:
                progress(1, 1)

        return ExtractionResult(
            lines=lines,
            meta={
                "extractor": self.name,
                "model": str(self.model),
                "providers": session.get_providers(),
                "tiled": use_tiling,
                "seconds": round(time.perf_counter() - started, 2),
            },
        )

    def _run(self, patch: np.ndarray) -> np.ndarray:
        """Run the network on one array, handling the stride-16 padding."""
        height, width = patch.shape
        padded_h = int(np.ceil(height / _STRIDE)) * _STRIDE
        padded_w = int(np.ceil(width / _STRIDE)) * _STRIDE

        # Upstream pads with 1.0 rather than 255. Kept identical so results
        # match the reference implementation; the pad is cropped off anyway.
        buffer = np.ones((1, 1, padded_h, padded_w), dtype=np.float32)
        buffer[0, 0, :height, :width] = patch

        out = self._infer(buffer)[0, 0]
        return np.clip(out[:height, :width], 0, 255)

    def _tiles(self, height: int, width: int) -> list[tuple[int, int, int, int]]:
        """Every tile as ``(y0, y1, x0, x1)``, listed up front so it can be counted."""
        tile = int(self.tile)
        step = max(1, tile - self.overlap)
        tiles = []
        for y0 in range(0, height, step):
            for x0 in range(0, width, step):
                y1 = min(y0 + tile, height)
                x1 = min(x0 + tile, width)
                # Pull short edge tiles back so they keep full context rather
                # than shrinking, which would change the model's field of view.
                tiles.append((max(0, y1 - tile), y1, max(0, x1 - tile), x1))
                if x1 >= width:
                    break
            if y0 + tile >= height:
                break
        return tiles

    def _extract_tiled(
        self,
        grey: np.ndarray,
        progress: Callable[[int, int], None] | None = None,
    ) -> np.ndarray:
        height, width = grey.shape
        accum = np.zeros((height, width), dtype=np.float32)
        weight = np.zeros((height, width), dtype=np.float32)

        tiles = self._tiles(height, width)
        for done, (y0a, y1, x0a, x1) in enumerate(tiles, start=1):
            patch = grey[y0a:y1, x0a:x1].astype(np.float32)
            result = self._run(patch)

            blend = _feather(result.shape, self.overlap)
            accum[y0a:y1, x0a:x1] += result * blend
            weight[y0a:y1, x0a:x1] += blend
            if progress is not None:
                progress(done, len(tiles))

        weight[weight == 0] = 1.0
        return np.clip(accum / weight, 0, 255).astype(np.uint8)


def _feather(shape: tuple[int, int], overlap: int) -> np.ndarray:
    """Cosine ramp on all four edges, so overlapping tiles cross-fade."""
    height, width = shape
    ramp_h = _ramp(height, overlap)
    ramp_w = _ramp(width, overlap)
    return np.outer(ramp_h, ramp_w).astype(np.float32)


def _ramp(length: int, overlap: int) -> np.ndarray:
    window = np.ones(length, dtype=np.float32)
    fade = min(overlap, length // 2)
    if fade <= 0:
        return window
    edge = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade, dtype=np.float32)))
    window[:fade] = edge
    window[-fade:] = edge[::-1]
    return window


def downscale_to(grey: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    """Bound the long side, returning the image and the scale applied.

    Useful for a first pass on CPU. Note this trades away exactly the detail
    that decides whether fine hatching is texture or boundary, so P3 numbers
    from a downscaled run are not comparable to full-resolution ones.
    """
    height, width = grey.shape
    longest = max(height, width)
    if longest <= max_side:
        return grey, 1.0
    scale = max_side / longest
    resized = cv2.resize(
        grey, (int(round(width * scale)), int(round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale
