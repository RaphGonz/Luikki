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

The upstream model is vendored under third_party/ and imported rather than
reimplemented, so the released ``erika.pth`` state dict loads without a
key-mapping layer between us and their weights.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

from .base import ExtractionResult

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VENDOR_DIR = _REPO_ROOT / "third_party" / "MangaLineExtraction"
_DEFAULT_WEIGHTS = _VENDOR_DIR / "erika.pth"

# The network downsamples five times, so both sides must be multiples of 16.
_STRIDE = 16


class MangaLineExtractor:
    """CPU-capable wrapper around the ``res_skip`` network.

    ``tile`` bounds peak memory and lets full-resolution studio pages (300dpi
    is routinely 3500x5000) run without a GPU. Tiles overlap and are feathered
    together; the seam is invisible at the thresholds we segment at, but the
    overlap must exceed the network's receptive field for that to hold, hence
    the generous default.
    """

    def __init__(
        self,
        weights: str | Path | None = None,
        tile: int | None = 1024,
        overlap: int = 128,
        device: str = "cpu",
    ):
        self.weights = Path(weights) if weights else _DEFAULT_WEIGHTS
        self.tile = tile
        self.overlap = overlap
        self.device = device
        self._model = None

    @property
    def name(self) -> str:
        return "manga_line_extraction"

    def _load(self):
        if self._model is not None:
            return self._model

        import torch

        if not self.weights.exists():
            raise FileNotFoundError(
                f"MangaLineExtraction weights not found at {self.weights}. "
                "Download erika.pth from "
                "https://github.com/ljsabc/MangaLineExtraction_PyTorch/releases/download/v1/erika.pth"
            )
        if str(_VENDOR_DIR) not in sys.path:
            sys.path.insert(0, str(_VENDOR_DIR))

        from model_torch import res_skip  # type: ignore[import-not-found]

        model = res_skip()
        model.load_state_dict(torch.load(self.weights, map_location=self.device))
        model.to(self.device)
        model.eval()
        self._model = model
        return model

    def extract(self, grey: np.ndarray) -> ExtractionResult:
        import torch

        model = self._load()
        started = time.perf_counter()

        if grey.ndim != 2:
            raise ValueError("MangaLineExtractor expects a 2-D greyscale array")

        height, width = grey.shape
        use_tiling = self.tile is not None and max(height, width) > self.tile

        with torch.no_grad():
            if use_tiling:
                lines = self._extract_tiled(model, grey, torch)
            else:
                lines = self._extract_whole(model, grey, torch)

        return ExtractionResult(
            lines=lines,
            meta={
                "extractor": self.name,
                "weights": str(self.weights),
                "tiled": use_tiling,
                "seconds": round(time.perf_counter() - started, 2),
            },
        )

    def _run(self, model, patch: np.ndarray, torch) -> np.ndarray:
        """Run the network on one array, handling the stride-16 padding."""
        height, width = patch.shape
        padded_h = int(np.ceil(height / _STRIDE)) * _STRIDE
        padded_w = int(np.ceil(width / _STRIDE)) * _STRIDE

        # Upstream pads with 1.0 rather than 255. Kept identical so results
        # match the reference implementation; the pad is cropped off anyway.
        buffer = np.ones((1, 1, padded_h, padded_w), dtype=np.float32)
        buffer[0, 0, :height, :width] = patch

        tensor = torch.from_numpy(buffer).to(self.device)
        out = model(tensor).cpu().numpy()[0, 0]
        return np.clip(out[:height, :width], 0, 255)

    def _extract_whole(self, model, grey: np.ndarray, torch) -> np.ndarray:
        return self._run(model, grey.astype(np.float32), torch).astype(np.uint8)

    def _extract_tiled(self, model, grey: np.ndarray, torch) -> np.ndarray:
        height, width = grey.shape
        tile = int(self.tile)
        step = max(1, tile - self.overlap)

        accum = np.zeros((height, width), dtype=np.float32)
        weight = np.zeros((height, width), dtype=np.float32)

        for y0 in range(0, height, step):
            for x0 in range(0, width, step):
                y1 = min(y0 + tile, height)
                x1 = min(x0 + tile, width)
                # Pull short edge tiles back so they keep full context rather
                # than shrinking, which would change the model's field of view.
                y0a = max(0, y1 - tile)
                x0a = max(0, x1 - tile)

                patch = grey[y0a:y1, x0a:x1].astype(np.float32)
                result = self._run(model, patch, torch)

                blend = _feather(result.shape, self.overlap)
                accum[y0a:y1, x0a:x1] += result * blend
                weight[y0a:y1, x0a:x1] += blend

                if x1 >= width:
                    break
            if y0 + tile >= height:
                break

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
