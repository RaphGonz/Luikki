"""Synthetic page builders shared across the backend test suite.

Every builder here returns freshly allocated numpy arrays from pure
parameters — no image file ever touches disk, following the
``tests/test_panels.py`` / ``tests/test_trappedball.py`` idiom of boolean
arrays built by slice assignment. The glyph-row and single-bubble builders that used to live here went with
the heuristic bubble detector: ``tests/test_bubbles.py`` now builds its own
balloon, because what it needs to vary -- a gap of N degrees in the outline
-- is the whole point of that test and belongs next to it.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest


class MemoryVault(dict):
    """The system password store's stand-in: a dict, gone with the test."""

    def get(self, name):
        return super().get(name)

    def set(self, name, value):
        self[name] = value

    def delete(self, name):
        self.pop(name, None)


@pytest.fixture(autouse=True)
def _no_system_vault(monkeypatch):
    """No test reads or writes the machine's real password store."""
    from luikki import account

    monkeypatch.setattr(account, "KeyringVault", MemoryVault)


def boundary_crossing_page(
    width: int = 600, height: int = 400
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int, int, int]]]:
    """A synthetic two-panel page whose bubble straddles the gutter.

    Returns ``(grey, line_mask, panel_boxes)``: two framed panels
    (``panel_boxes`` as ``(x, y, w, h)`` tuples) separated by a vertical
    gutter, with one closed bubble outline centred on the gutter so its
    pixels fall inside BOTH panel boxes. This is success criterion 4's
    "not only on a clean test page" fixture -- D-20's page-scoped
    ``ProtectedMask`` exists specifically because this case is
    unrepresentable at panel scope.
    """
    gutter = 30
    panel_w = (width - 3 * gutter) // 2
    panel_h = height - 2 * gutter
    panel_y = gutter
    panel1_x = gutter
    panel2_x = gutter + panel_w + gutter

    panel_boxes: list[tuple[int, int, int, int]] = [
        (panel1_x, panel_y, panel_w, panel_h),
        (panel2_x, panel_y, panel_w, panel_h),
    ]

    drawing = np.zeros((height, width), dtype=np.uint8)
    for px, py, pw, ph in panel_boxes:
        cv2.rectangle(drawing, (px, py), (px + pw - 1, py + ph - 1), 1, thickness=2)

    # The bubble is centred on the gutter's midpoint and wide enough that
    # its outline reaches past both panel edges into each panel's interior.
    gutter_mid_x = panel1_x + panel_w + gutter // 2
    centre = (gutter_mid_x, height // 2)
    axes = (gutter + 20, 40)
    cv2.ellipse(drawing, centre, axes, 0, 0, 360, 1, thickness=2)

    line_mask = drawing.astype(bool)
    grey = np.where(line_mask, 0, 255).astype(np.uint8)
    return grey, line_mask, panel_boxes
