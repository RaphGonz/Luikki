"""Line extraction — the swappable half of every §7 Tier 3 domain adapter."""

from .base import ExtractionResult, LineExtractor
from .manga_line import MangaLineExtractor, downscale_to
from .passthrough import PassthroughExtractor

__all__ = [
    "ExtractionResult",
    "LineExtractor",
    "MangaLineExtractor",
    "PassthroughExtractor",
    "downscale_to",
]
