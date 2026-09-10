"""The null extractor: use the page's own pixels as the line image.

This is the honest baseline for P3. On a real ink layer it is not a fallback
but the *correct* extractor — the ink layer already is the line image, and
running a learned model over it can only lose information. On a published,
screentoned page it is the disaster case, which is precisely what makes it
worth measuring against.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .base import ExtractionResult


class PassthroughExtractor:
    """Returns the page unchanged."""

    @property
    def name(self) -> str:
        return "passthrough"

    def extract(
        self,
        grey: np.ndarray,
        progress: Callable[[int, int], None] | None = None,
    ) -> ExtractionResult:
        result = ExtractionResult(lines=grey.copy(), meta={"extractor": self.name})
        if progress is not None:
            progress(1, 1)
        return result
