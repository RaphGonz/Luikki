"""§1.3 leak audit: a line with a hole cuts, a tunnel does not."""

from __future__ import annotations

import cv2
import numpy as np

from luikki.model.masks import UNASSIGNED
from luikki.segmentation.leaks import LeakParams, split_open_borders


def _zones(labels: np.ndarray) -> int:
    return len(np.unique(labels[labels != UNASSIGNED]))


def _one_zone(line_mask: np.ndarray) -> np.ndarray:
    """What a merging segmenter returns: everything fillable in one zone."""
    labels = np.zeros(line_mask.shape, dtype=np.int32)
    labels[~line_mask] = 1
    return labels


def _box(height: int = 80, width: int = 120) -> np.ndarray:
    line = np.zeros((height, width), dtype=bool)
    line[0, :] = line[-1, :] = line[:, 0] = line[:, -1] = True
    return line


def test_line_with_a_hole_is_cut():
    # Two chambers divided by a stroke with a 6px hole in it. The ball that
    # would be stopped by the stroke fits through the hole, so a merging
    # segmenter hands both chambers back as one zone.
    line = _box()
    line[40:42, :] = True
    line[40:42, 57:63] = False

    labels = _one_zone(line)
    assert _zones(labels) == 1

    out = split_open_borders(labels, line, params=LeakParams(min_piece=100))
    assert _zones(out) == 2
    assert out[20, 60] != out[60, 60]
    assert (out[~line] != UNASSIGNED).all()


def test_a_tunnel_is_left_alone():
    # One chamber pinched to a 6px waist — the same width as the hole above.
    # Drawn as art is drawn: a 2px outline with paper beyond it, not a solid
    # mass of ink, so the border a split would draw is open along its whole
    # length. That is a passage, not a leak.
    inside = np.zeros((80, 120), dtype=bool)
    inside[5:36, 20:100] = True  # upper chamber
    inside[45:76, 20:100] = True  # lower chamber
    inside[36:45, 57:63] = True  # the corridor between them

    line = cv2.morphologyEx(
        inside.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)
    ).astype(bool)
    protected = ~inside & ~line

    labels = np.zeros(line.shape, dtype=np.int32)
    labels[inside & ~line] = 1

    out = split_open_borders(
        labels, line, protected=protected, params=LeakParams(min_piece=100)
    )
    assert _zones(out) == 1


def test_a_hairline_stroke_still_cuts():
    # A one-pixel stroke cannot be met from both sides — the expansion has to
    # give it to one of them — but the border the two halves then share still
    # runs along it, so the hole is still read as a hole.
    line = _box()
    line[40, :] = True
    line[40, 57:63] = False
    labels = _one_zone(line)
    out = split_open_borders(labels, line, params=LeakParams(min_piece=100))
    assert _zones(out) == 2


def test_zones_are_only_ever_divided():
    # The audit may carve a zone up; it may never move a pixel from one of the
    # segmenter's zones into another, or hand back a pixel it was given as line.
    line = _box(90, 90)
    line[45:47, :] = True
    line[45:47, 40:46] = False
    line[:, 45:47] = True
    line[20:26, 45:47] = False

    labels = np.zeros(line.shape, dtype=np.int32)
    labels[~line] = 1
    labels[:45, :45][~line[:45, :45]] = 2  # segmenter already split one quarter

    out = split_open_borders(labels, line, params=LeakParams(min_piece=50))

    assert (out[line] == UNASSIGNED).all()
    assert (out[~line] != UNASSIGNED).all()
    for zone in np.unique(out[out != UNASSIGNED]):
        # every output zone lies inside exactly one of the segmenter's zones
        assert len(np.unique(labels[out == zone])) == 1


def test_protected_pixels_stay_unassigned():
    line = _box()
    line[40:42, :] = True
    line[40:42, 57:63] = False
    protected = np.zeros(line.shape, dtype=bool)
    protected[10:25, 10:40] = True

    labels = np.zeros(line.shape, dtype=np.int32)
    labels[~line & ~protected] = 1

    out = split_open_borders(
        labels, line, protected=protected, params=LeakParams(min_piece=100)
    )
    assert (out[protected] == UNASSIGNED).all()
    assert _zones(out) == 2


def test_empty_input_is_returned_unchanged():
    line = np.ones((20, 20), dtype=bool)
    labels = np.zeros((20, 20), dtype=np.int32)
    assert (split_open_borders(labels, line) == labels).all()


def test_the_gap_allowance_is_a_share(tmp_path):
    import pytest

    from luikki.web.session import Session, StepError

    session = Session(workdir=tmp_path)
    for bad in (-0.1, 1.5):
        with pytest.raises(StepError, match="gap_share"):
            session.segment_zones(leak_gap=bad)
