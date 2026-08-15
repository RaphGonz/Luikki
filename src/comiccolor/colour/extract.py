"""Palette extraction: quantize-then-merge, never chip/contour detection.

D-12 chooses dominant-colour extraction over the whole image instead of
chip/contour detection (OpenCV's contour and connected-component finders,
`.planning/research/STACK.md`'s original proposal for this requirement,
explicitly overridden here). D-13 requires an existing library over a
hand-rolled quantizer or colour-distance formula: the solved 90% is
Pillow's own ``Image.quantize()`` (median cut, zero new dependency —
RESEARCH.md § Standard Stack, verified live to recover a flat chip grid
exactly) plus ``skimage.color`` for the CIELAB distance. The genuinely
project-specific 10% is the adaptive-count merge on top, since neither
library returns a variable colour count natively (D-15).

D-14 makes this the single extractor for both PAL-01 (swatch upload) and
PAL-02 (character sheet): the sheet path differs only by a pre-pass
(``_drop_ink_and_paper``) run before quantization; everything after that
point — quantize, merge, drop-noise, sort — is shared.

Every threshold below is a named constant, deliberately flagged as an
unvalidated starting hypothesis rather than a tuned spec value
(RESEARCH.md Pitfall 5 — the same class of number that
`.planning/research/PITFALLS.md` Pitfall 10 already warns hardens
silently into spec if it is not named and tested in more than one
regime). Real values come from supervised video-call sessions against
real artist uploads, not from this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image
from skimage.color import deltaE_cie76, rgb2lab

# Generous quantization ceiling. This is an unvalidated starting value —
# the adaptive count that survives _merge_similar is what callers see,
# never this number directly.
K_MAX = 24

# CIELAB deltaE_cie76 below which two clusters are treated as the same
# colour by _merge_similar. This is an unvalidated starting value
# (RESEARCH.md Pitfall 5, Assumptions Log A1) — Phase 5's eventual
# snapping-reject threshold is the same *kind* of constant, and
# `.planning/research/PITFALLS.md` Pitfall 10 already warns about exactly
# this class of number quietly hardening into spec.
MERGE_DELTA_E = 12.0

# Clusters holding under this share of kept pixels are dropped as
# extraction noise (anti-aliasing, JPEG artefacts). Unvalidated starting
# value, same caveat as above.
MIN_PIXEL_SHARE = 0.005

# Near-black / near-white bounds for the character-sheet ink/paper
# pre-pass (D-14, ``_drop_ink_and_paper``). Both are unvalidated starting
# values (RESEARCH.md Pitfall 5) — hypotheses to be tuned against real
# character sheets during supervised sessions, not shipped as settled spec.
INK_MAX = 30
PAPER_MIN = 235


@dataclass(frozen=True)
class ExtractedColour:
    """One surviving cluster from the quantize-then-merge pass."""

    rgb: tuple[int, int, int]
    pixel_count: int
    pixel_share: float


class EmptyImageError(ValueError):
    """Raised when nothing survives extraction.

    A ``ValueError`` subclass so the web layer (plan 01-06) can map it to a
    structured 4xx directly rather than the pipeline crashing with an
    unhandled exception on an all-ink or all-paper sheet (RESEARCH.md
    Pitfall 4).
    """


def extract_palette(
    image: Image.Image, *, sheet_mode: bool = False
) -> list[ExtractedColour]:
    """Dominant colours in ``image``, adaptive count, no chip detection.

    Median cut (``Image.quantize``) recovers a flat chip grid exactly — the
    obvious win D-13 chose over a hand-rolled quantizer. Its accepted
    weakness is coarseness on a genuinely photographed, shaded sheet
    compared to a K-means-based library (RESEARCH.md Assumptions Log A5);
    D-15 accepts this class of imperfection, and PAL-03's manual add/delete
    is the recovery path, reachable from the same screen as this result
    rather than a colour-count slider.

    ``sheet_mode=True`` runs :func:`_drop_ink_and_paper` first (D-14); the
    swatch path (``sheet_mode=False``) never does, since an artist's
    deliberate black or white chip must survive.

    No colour-count parameter exists on purpose (D-15) — the image decides
    how many entries come back.
    """
    if image.mode != "RGB":
        image = _flatten_to_rgb(image)

    if sheet_mode:
        image = _drop_ink_and_paper(image)

    counts = _quantize_counts(image)
    if not counts:
        raise EmptyImageError("No pixels survived extraction.")

    merged = _merge_similar(counts)
    total = sum(count for count, _ in merged)
    if total == 0:
        raise EmptyImageError("No pixels survived extraction.")

    survivors = [
        ExtractedColour(rgb=rgb, pixel_count=count, pixel_share=count / total)
        for count, rgb in merged
        if count / total >= MIN_PIXEL_SHARE
    ]
    if not survivors:
        raise EmptyImageError("No pixels survived extraction.")

    survivors.sort(key=lambda entry: entry.pixel_share, reverse=True)
    return survivors


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """Flatten alpha over a fixed mid-neutral background.

    ``MEDIANCUT``/``MAXCOVERAGE`` do not accept RGBA (RESEARCH.md Pattern 3's
    stated caveat) — flattening first keeps swatch PNGs with transparency
    (the common export shape) working without relying on Pillow's own
    unverified RGBA-aware quantization path.
    """
    background = Image.new("RGB", image.size, (128, 128, 128))
    rgba = image.convert("RGBA")
    background.paste(rgba, mask=rgba.split()[3])
    return background


def _quantize_counts(image: Image.Image) -> list[tuple[int, tuple[int, int, int]]]:
    """Median-cut quantize at ``K_MAX``, return ``(pixel_count, rgb)`` pairs."""
    quantized = image.quantize(
        colors=K_MAX, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )
    return quantized.convert("RGB").getcolors(maxcolors=256) or []


def _merge_similar(
    counts: list[tuple[int, tuple[int, int, int]]],
) -> list[tuple[int, tuple[int, int, int]]]:
    """Greedily fold clusters within ``MERGE_DELTA_E`` of a kept cluster.

    Walks clusters in descending pixel count so a flat chip's own
    anti-aliased edge pixels (which quantize can split off as a tiny
    separate cluster) fold into the dominant cluster rather than the
    reverse — the merged entry keeps the larger cluster's RGB, summing
    pixel counts, never averaging colours in a way that would drift a
    chip's own true colour.
    """
    ordered = sorted(counts, key=lambda item: item[0], reverse=True)
    kept: list[list] = []  # each entry: [pixel_count, rgb, lab]
    for count, rgb in ordered:
        lab = rgb2lab(np.array([[rgb]], dtype=np.float64) / 255.0)[0, 0]
        for entry in kept:
            if deltaE_cie76(entry[2], lab) < MERGE_DELTA_E:
                entry[0] += count
                break
        else:
            kept.append([count, rgb, lab])
    return [(count, rgb) for count, rgb, _ in kept]


def _drop_ink_and_paper(image: Image.Image) -> Image.Image:
    """Drop near-black ink and near-white paper before quantizing (D-14).

    Ink and paper are not colour: a character sheet's real palette lives
    only in the pixels between those bands. Filtering the survivors and
    reshaping them into a synthetic ``N x 1`` strip is equivalent for
    palette purposes — median cut reads the colour distribution, not the
    spatial arrangement — and it sidesteps Pillow's unverified RGBA/alpha
    handling entirely (RESEARCH.md Pattern 4), which is why this is a pixel
    filter and not an alpha-channel trick.

    ``INK_MAX`` and ``PAPER_MIN`` are hypotheses, not yet validated against
    real character sheets from this project's artists — expected to be
    tuned during the supervised video-call sessions (RESEARCH.md Pitfall 5,
    Assumptions Log A1).
    """
    arr = np.asarray(image.convert("RGB"))
    near_black = (arr < INK_MAX).all(axis=-1)
    near_white = (arr > PAPER_MIN).all(axis=-1)
    kept = arr[~(near_black | near_white)]
    if kept.size == 0:
        raise EmptyImageError(
            "This sheet is entirely near-black or near-white — nothing "
            "survived the ink/paper pre-pass to extract a palette from."
        )
    return Image.fromarray(kept.reshape(-1, 1, 3), "RGB")
