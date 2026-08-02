"""The line-extractor seam.

§7 frames every Tier 3 domain adapter as "a swappable line extractor +
segmentation profile, selected per project. Same core pipeline throughout."
This is that seam.

An extractor takes a page as the artist's file gives it to us and returns a
greyscale line image — dark where line, light where not. It is allowed to be a
learned model, because it sits strictly *upstream* of trapped-ball. The
deterministic guarantee in §9 is about segmentation, and segmentation still
receives a plain raster and still produces exact masks. Swapping the extractor
changes which pixels are considered line; it cannot make a region overlap
another one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass
class ExtractionResult:
    """A greyscale line image plus whatever the extractor wants on the record."""

    # uint8, 0-255. Dark = line. Same convention as the input page, so a
    # threshold applied to either means the same thing.
    lines: np.ndarray
    # Free-form provenance: model name, runtime, downscale factor applied.
    meta: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class LineExtractor(Protocol):
    """Anything that turns a page into a line image."""

    @property
    def name(self) -> str: ...

    def extract(self, grey: np.ndarray) -> ExtractionResult:
        """``grey`` is uint8 greyscale, dark = ink. Returns a line image."""
        ...
