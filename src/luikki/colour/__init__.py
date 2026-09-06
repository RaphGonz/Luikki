"""Palette extraction — quantize-then-merge (D-12/D-13/D-14/D-15)."""

from .extract import (
    INK_MAX,
    K_MAX,
    MERGE_DELTA_E,
    MIN_PIXEL_SHARE,
    PAPER_MIN,
    EmptyImageError,
    ExtractedColour,
    extract_palette,
)

__all__ = [
    "INK_MAX",
    "K_MAX",
    "MERGE_DELTA_E",
    "MIN_PIXEL_SHARE",
    "PAPER_MIN",
    "EmptyImageError",
    "ExtractedColour",
    "extract_palette",
]
