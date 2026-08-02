"""Deterministic segmentation. §1.1, §1.3, §1.4.

This is the exact half of the pipeline. Nothing here is probabilistic and
nothing here calls a model. §9: keep the boundary between segmentation
(geometric) and labelling (semantic) inspectable.
"""

from .closure import ClosureParams, close_line_gaps, find_endpoints
from .panels import PanelBox, PanelParams, segment_panels
from .preprocess import estimate_line_width, ink_fraction, load_line_art
from .trappedball import (
    DEFAULT_RADII,
    SegmentationParams,
    expand_under_lines,
    merge_small_regions,
    trapped_ball_segment,
)

__all__ = [
    "DEFAULT_RADII",
    "ClosureParams",
    "PanelBox",
    "PanelParams",
    "SegmentationParams",
    "close_line_gaps",
    "estimate_line_width",
    "expand_under_lines",
    "find_endpoints",
    "ink_fraction",
    "load_line_art",
    "merge_small_regions",
    "segment_panels",
    "trapped_ball_segment",
]
