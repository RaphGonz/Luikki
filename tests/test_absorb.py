"""§1.4 micro-zone absorption: a crumb joins its neighbour, a button does not."""

from __future__ import annotations

import numpy as np

from luikki.model.masks import UNASSIGNED
from luikki.segmentation.absorb import AbsorbParams, absorb_micro_zones
from luikki.segmentation.trappedball import expand_under_lines, inked_zones

PANEL = 100 * 100


def _empty(shape=(100, 100)) -> np.ndarray:
    return np.zeros(shape, dtype=bool)


def _background() -> np.ndarray:
    """One region filling the panel. Crumbs are punched into it by the tests."""
    return np.ones((100, 100), dtype=np.int32)


def test_a_crumb_enclosed_by_one_region_joins_it():
    labels = _background()
    labels[48:53, 48:53] = 2  # 25px, wholly inside region 1

    out = absorb_micro_zones(
        labels, _empty(), _empty(), PANEL, params=AbsorbParams(max_area_share=0.01)
    )
    assert out[50, 50] == 1
    assert set(np.unique(out)) == {1}


def test_a_region_between_two_neighbours_is_left_alone():
    # Half the panel each, and the crumb sits astride the seam. Picking either
    # side would be a guess, and a guess is what the artist has to undo.
    labels = _background()
    labels[:, 50:] = 2
    labels[48:53, 45:55] = 3

    out = absorb_micro_zones(
        labels, _empty(), _empty(), PANEL, params=AbsorbParams(max_area_share=0.01)
    )
    assert out[50, 50] == 3


def test_a_region_above_the_ceiling_is_left_alone():
    # Enclosed on all sides, exactly like the crumb above. Only its size says
    # it was drawn on purpose, which is why the ceiling is the whole decision.
    labels = _background()
    labels[30:70, 30:70] = 2  # 1600px, 16% of the panel

    out = absorb_micro_zones(
        labels, _empty(), _empty(), PANEL, params=AbsorbParams(max_area_share=0.01)
    )
    assert out[50, 50] == 2


def test_the_ceiling_follows_the_panel_and_not_the_pixel():
    """The same figure, two panel sizes, two answers.

    This is the whole reason the threshold is a share: a mark that is a crumb
    on a splash page is a drawn thing on a nine-panel grid, and a constant in
    pixels calls them the same.
    """
    labels = _background()
    labels[48:53, 48:53] = 2
    params = AbsorbParams(max_area_share=0.001)  # 25px is 0.25% of 100x100

    small_panel = absorb_micro_zones(labels, _empty(), _empty(), PANEL, params=params)
    assert small_panel[50, 50] == 2  # over the ceiling here

    big_panel = absorb_micro_zones(
        labels, _empty(), _empty(), PANEL * 10, params=params
    )
    assert big_panel[50, 50] == 1  # the same 25px, ten times the panel


def test_a_highlight_inside_the_artists_black_survives():
    """The guard. A catchlight in a mass of ink must not join the ink.

    The black is punched out after expansion — it is the artist's own layer and
    a zone under it is invisible. Absorbed into it, the highlight would go with
    it and come back white, which is worse than the crumb this pass removes.
    """
    labels = _background()
    labels[20:80, 20:80] = 2  # the spot black
    labels[48:53, 48:53] = 3  # a highlight in it

    ink = _empty()
    ink[labels == 2] = True
    assert inked_zones(labels, ink)[2]

    out = absorb_micro_zones(
        labels, _empty(), ink, PANEL, params=AbsorbParams(max_area_share=0.01)
    )
    assert out[50, 50] == 3


def test_a_chain_of_crumbs_resolves_to_the_far_end():
    labels = _background()
    labels[40:60, 40:60] = 2  # 400px, itself under the ceiling
    labels[49:52, 49:52] = 3  # 9px, inside it

    out = absorb_micro_zones(
        labels, _empty(), _empty(), PANEL, params=AbsorbParams(max_area_share=0.05)
    )
    assert out[50, 50] == 1
    assert set(np.unique(out)) == {1}


def test_regions_separated_by_a_line_still_see_each_other():
    """Adjacency is measured under the ink, or nothing touches anything.

    Two regions with a stroke between them share no 4-neighbour contact at all
    until the stroke is filled in. Measuring before that would make every crumb
    borderless and this pass a no-op on real art.
    """
    # A crumb ringed by its own stroke: not one pixel of it touches region 1.
    line = _empty()
    line[58:65, 58:65] = True
    line[60:63, 60:63] = False

    labels = _background()
    labels[line] = UNASSIGNED
    labels[60:63, 60:63] = 2

    out = absorb_micro_zones(
        labels, line, _empty(), PANEL, params=AbsorbParams(max_area_share=0.01)
    )
    assert out[61, 61] == 1
    assert (out[line] == UNASSIGNED).all()


# -- the residue, step 4's second expansion ---------------------------------
#
# Zones are cut on the structural lines and grown under the *real* ink, so a
# pixel the extractor called line and the artist's ink does not cover belongs
# to no zone: no segment to click, no colour, transparent in every PSD layer,
# white on the flattened page. These press the sequence `segment_zones` runs.


def test_the_residue_takes_the_nearest_label():
    labels = _background()
    labels[:, 50:] = 2
    labels[:, 49:51] = UNASSIGNED  # what the extractor called a line

    ink = _empty()  # ...and the artist's ink covers none of it
    expanded = expand_under_lines(labels, ink)
    assert (expanded[:, 49:51] == UNASSIGNED).all(), "ink-only expansion leaves it"

    filled = expand_under_lines(expanded, np.ones_like(ink))
    assert filled[50, 49] == 1
    assert filled[50, 50] == 2
    assert (filled != UNASSIGNED).all()


def test_the_two_deliberate_holes_stay_holes():
    labels = _background()
    labels[10:20, 10:20] = 2  # the artist's spot black
    labels[80:90, 80:90] = UNASSIGNED  # a bubble

    protected = _empty()
    protected[80:90, 80:90] = True
    ink = _empty()
    ink[10:20, 10:20] = True

    doomed = inked_zones(labels, ink)
    expanded = expand_under_lines(labels, ink, protected=protected)
    spot_black = doomed[expanded]
    expanded = expand_under_lines(expanded, ~spot_black, protected=protected)
    expanded[spot_black] = UNASSIGNED

    assert (expanded[10:20, 10:20] == UNASSIGNED).all()
    assert (expanded[80:90, 80:90] == UNASSIGNED).all()
    assert (expanded[40:60, 40:60] == 1).all()
