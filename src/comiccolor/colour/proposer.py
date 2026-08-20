"""§1.6 The colour proposer seam.

The architectural claim of the whole project is that the generative model is a
*colour proposer*, not the output path (`flatting-pipeline-spec.md` §1).
This module is where that claim becomes a type: everything downstream —
`snap.assign_zones`, the export — consumes a proposal raster and cannot tell
which proposer produced it.

A proposer takes one panel and returns one HxWx3 uint8 RGB raster the same
size as the panel crop. That raster is an intermediate and is **never shown to
the artist and never exported** (§ rule 6). Its only consumer is per-zone mode
extraction.

Two implementations live behind this protocol:

- `DistinctColourProposer` here — no model, no GPU, no weights. It paints each
  zone its own well-separated colour, which is what a production flatter does
  by hand: the flats exist to make selections, and semantics come later.
- `CobraProposer` in `cobra.py` — the real thing, on a machine with the VRAM
  for it.

Swapping between them changes one constructor call and nothing else.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from ..model.masks import UNASSIGNED


@dataclass
class PanelRequest:
    """One panel's worth of input, in the panel's own pixel frame."""

    # HxWx3 uint8 RGB. The panel crop of the page, greyscale replicated across
    # channels for a plain ink layer.
    line_art: np.ndarray
    # HxW int32 zone map from segmentation. UNASSIGNED on line and protected
    # pixels. A model proposer ignores this; a deterministic one needs it.
    label_map: np.ndarray
    # Character sheets, HxWx3 uint8 RGB, page-scoped so every panel gets the
    # same list. May be empty.
    references: list[np.ndarray] = field(default_factory=list)
    # Optional spatial colour hints, in the panel's own frame: `hint_colours`
    # HxWx3 uint8 RGB, meaningful only where `hint_mask` is True.
    #
    # A palette cannot be turned into these — a palette is a set of colours
    # with no positions, and the position is the whole content of a hint. They
    # come from somewhere that knows *where*: an artist clicking a zone, or a
    # page that has already been coloured. A deterministic proposer ignores
    # both fields.
    hint_colours: np.ndarray | None = None
    hint_mask: np.ndarray | None = None

    @property
    def size(self) -> tuple[int, int]:
        """(height, width) of the panel crop."""
        return self.line_art.shape[0], self.line_art.shape[1]


@runtime_checkable
class ColourProposer(Protocol):
    @property
    def name(self) -> str: ...

    def propose(self, request: PanelRequest) -> np.ndarray:
        """HxWx3 uint8 RGB proposal, same size as `request.line_art`."""
        ...


# Golden-angle hue step. Successive zones land far apart on the hue circle
# instead of walking it in order, so neighbouring zones — which are usually
# consecutive labels — never come out as neighbouring colours.
_GOLDEN_ANGLE = 0.61803398875

# Cycled so that zones beyond the first hue lap stay distinguishable from
# their lap-1 counterparts on more than hue alone.
_TIERS = ((0.65, 0.95), (0.90, 0.70), (0.45, 0.99), (0.75, 0.55))


def distinct_colour(index: int) -> tuple[int, int, int]:
    """A well-separated flat colour for the `index`-th zone."""
    hue = (index * _GOLDEN_ANGLE) % 1.0
    saturation, value = _TIERS[index % len(_TIERS)]
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


class DistinctColourProposer:
    """Every zone its own colour. No model, no GPU, no weights.

    This is not a placeholder for Cobra — it is the classical flatting output,
    and a colourist can work from it directly: the flats give one-click
    selections per zone and they recolour from there. What it cannot do is
    know that *this* patch is Kaito's hair. That is the whole of what the
    model adds, and it is why the seam exists.
    """

    @property
    def name(self) -> str:
        return "distinct"

    def propose(self, request: PanelRequest) -> np.ndarray:
        height, width = request.size
        proposal = np.zeros((height, width, 3), dtype=np.uint8)

        labels = request.label_map
        present = np.unique(labels)
        present = present[present != UNASSIGNED]

        # A lookup table indexed by label beats masking per zone — panels run
        # to several hundred zones on a hatched page.
        table = np.zeros((int(labels.max()) + 1, 3), dtype=np.uint8)
        for index, label in enumerate(present):
            table[label] = distinct_colour(index)

        inside = labels != UNASSIGNED
        proposal[inside] = table[labels[inside]]
        return proposal
