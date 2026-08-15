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
entries. These stubs are Wave 0 scaffolding for plan 01-05.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-05")
def test_flat_chip_grid_recovers_exact_colours():
    """D-12: 'if it was already an image with chips ... 100% of the
    time.' A synthetic 40x40 four-chip image comes back as exactly the
    four source colours, no more, no fewer."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-05")
def test_adaptive_count_collapses_near_duplicates():
    """D-15: two chips one CIELAB step apart come back as a single
    palette entry — the count is adaptive, not pinned to ``K_MAX``."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-05")
def test_sheet_prepass_drops_ink_and_paper():
    """D-14: with ``sheet_mode=True``, near-black and near-white pixels
    contribute no palette entry — they are ink and paper, not colour."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-05")
def test_noisy_gradient_returns_a_sane_count():
    """A smooth gradient returns at least 1 and fewer than ``K_MAX``
    entries — the adaptive merge does not degenerate to either extreme
    on continuous input."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-05")
def test_thresholds_are_named_constants():
    """``K_MAX``, ``MERGE_DELTA_E``, ``MIN_PIXEL_SHARE``, ``INK_MAX`` and
    ``PAPER_MIN`` are importable module-level names — no unvalidated
    magic numbers buried inline."""
    ...
