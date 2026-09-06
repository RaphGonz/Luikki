"""Palette extraction, as tests.

D-12 chooses quantize-then-merge over chip/contour detection: "if it was
already an image with chips ... 100% of the time" it must recover the
exact source colours, so quantization has to be exact-on-flats before it
is asked to be adaptive on anything harder. D-13 fixes the mechanism —
Pillow's median-cut ``quantize()``, not a new dependency. D-14 is the
sheet pre-pass: a swatch image already has no ink or paper to filter,
but a character sheet does, and the filter is a pixel-level pre-pass,
not an alpha trick. D-15 makes the entry count adaptive — a CIELAB merge
collapses near-duplicate chips rather than always returning ``K_MAX``
entries.
"""

import numpy as np
import pytest
from PIL import Image

from luikki.colour import (
    INK_MAX,
    K_MAX,
    MERGE_DELTA_E,
    MIN_PIXEL_SHARE,
    PAPER_MIN,
    EmptyImageError,
    extract_palette,
)


def test_flat_chip_grid_recovers_exact_colours():
    """D-12: 'if it was already an image with chips ... 100% of the
    time.' A synthetic 40x40 four-chip image comes back as exactly the
    four source colours, no more, no fewer."""
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[0:20, 0:20] = [255, 0, 0]
    arr[0:20, 20:40] = [0, 255, 0]
    arr[20:40, 0:20] = [0, 0, 255]
    arr[20:40, 20:40] = [255, 255, 0]
    image = Image.fromarray(arr, "RGB")

    entries = extract_palette(image)

    assert {e.rgb for e in entries} == {
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
    }
    assert len(entries) == 4


def test_adaptive_count_collapses_near_duplicates():
    """D-15: two chips one CIELAB step apart come back as a single
    palette entry — the count is adaptive, not pinned to ``K_MAX``."""
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[:20, :] = [100, 150, 200]
    arr[20:, :] = [104, 152, 202]
    image = Image.fromarray(arr, "RGB")

    entries = extract_palette(image)

    assert len(entries) == 1
    assert entries[0].pixel_count == 40 * 40


def test_sheet_prepass_drops_ink_and_paper():
    """D-14: with ``sheet_mode=True``, near-black and near-white pixels
    contribute no palette entry — they are ink and paper, not colour."""
    arr = np.zeros((80, 80, 3), dtype=np.uint8)
    arr[0:20, :] = [10, 10, 10]  # ink
    arr[20:40, :] = [200, 50, 50]  # real colour 1
    arr[40:60, :] = [50, 50, 200]  # real colour 2
    arr[60:80, :] = [250, 250, 250]  # paper
    image = Image.fromarray(arr, "RGB")

    sheet_entries = extract_palette(image, sheet_mode=True)
    assert {e.rgb for e in sheet_entries} == {(200, 50, 50), (50, 50, 200)}

    swatch_entries = extract_palette(image, sheet_mode=False)
    assert len(swatch_entries) > len(sheet_entries)


def test_noisy_gradient_returns_a_sane_count():
    """A smooth gradient returns at least 1 and fewer than ``K_MAX``
    entries — the adaptive merge does not degenerate to either extreme
    on continuous input. This is Pitfall 5's second regime: constants
    must behave reasonably on non-flat input, not only the flat chip
    grid they were tuned against (D-15)."""
    width = 256
    arr = np.zeros((16, width, 3), dtype=np.uint8)
    ramp = np.linspace(0, 255, width, dtype=np.uint8)
    arr[:, :, :] = ramp[np.newaxis, :, np.newaxis]
    image = Image.fromarray(arr, "RGB")

    entries = extract_palette(image)

    assert 1 <= len(entries) < K_MAX
    assert all(e.pixel_share >= MIN_PIXEL_SHARE for e in entries)


def test_thresholds_are_named_constants():
    """RESEARCH.md Pitfall 5: no unvalidated magic numbers buried in
    expressions (D-13) — every threshold is an importable module-level
    name with its documented starting value."""
    assert K_MAX == 24
    assert MERGE_DELTA_E == 12.0
    assert MIN_PIXEL_SHARE == 0.005
    assert INK_MAX == 30
    assert PAPER_MIN == 235


def test_all_ink_sheet_raises_empty_image_error():
    """D-14/RESEARCH.md Pitfall 4: an all-near-black sheet raises
    ``EmptyImageError`` (a ``ValueError``), never crashes the pipeline
    with an unhandled exception."""
    arr = np.full((20, 20, 3), 5, dtype=np.uint8)
    image = Image.fromarray(arr, "RGB")

    with pytest.raises(EmptyImageError):
        extract_palette(image, sheet_mode=True)


def test_entries_are_ordered_by_descending_share():
    """01-UI-SPEC.md §4 renders extraction results in grid order; the
    dominant colour must lead (D-15's adaptive count is meaningless if
    the artist can't tell which entry is dominant at a glance)."""
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[:, :] = [10, 200, 10]  # dominant background
    arr[0:4, 0:4] = [200, 10, 10]  # 16px minority chip
    arr[4:10, 4:10] = [10, 10, 200]  # 36px mid-size chip
    image = Image.fromarray(arr, "RGB")

    entries = extract_palette(image)

    shares = [e.pixel_share for e in entries]
    assert shares == sorted(shares, reverse=True)
    assert len(entries) >= 2


def test_rgba_input_does_not_crash():
    """RESEARCH.md Pattern 3: ``MEDIANCUT`` does not accept RGBA
    directly — the common swatch PNG export shape must not raise."""
    arr = np.zeros((20, 20, 4), dtype=np.uint8)
    arr[:, :, :3] = [80, 160, 240]
    arr[:, :, 3] = 255
    image = Image.fromarray(arr, "RGBA")

    entries = extract_palette(image)

    assert len(entries) >= 1
