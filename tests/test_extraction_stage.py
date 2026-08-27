"""§7's swappable line extractor, in the app rather than in a spike.

The §2.2 A/B chose the *extracted* condition and the app was feeding raw ink
straight into trapped-ball. This file pins the three facts that fix carries:
segmentation reads the extractor's output, panels and bubbles do not, and the
flats still reach under the artist's real ink.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from comiccolor.extract.base import ExtractionResult
from comiccolor.model.masks import UNASSIGNED
from comiccolor.segmentation.preprocess import binarise_lines
from comiccolor.web.session import Session

WEIGHTS = Path(__file__).resolve().parents[1] / "third_party" / "MangaLineExtraction" / "erika.pth"


class FakeExtractor:
    """Returns a line image the caller supplies, and records what it saw."""

    def __init__(self, lines: np.ndarray):
        self.lines = lines
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake"

    def extract(self, grey: np.ndarray) -> ExtractionResult:
        self.calls += 1
        self.seen = grey
        return ExtractionResult(lines=self.lines)


def brush_page(tmp_path) -> Path:
    """One panel holding a very thick stroke and a solid black block.

    Both are the case the user hit: on raw ink a thick stroke is bounded by
    its own two edges, so trapped-ball fills *inside* it, and a spot black is
    a zone in its own right.
    """
    art = np.full((300, 400), 255, dtype=np.uint8)
    cv2.rectangle(art, (10, 10), (390, 290), 0, 3)
    cv2.line(art, (60, 40), (60, 260), 0, 25)  # thick brush stroke
    cv2.rectangle(art, (200, 60), (330, 200), 0, -1)  # solid black fill

    path = tmp_path / "brush.png"
    cv2.imwrite(str(path), art)
    return path


def test_segmentation_reads_the_extractor_not_the_raw_ink(tmp_path):
    """The bug, as a test: swap the extractor and the zone map must change."""
    page = brush_page(tmp_path)

    # A line image with a single extra divider the raw page does not have.
    # If segmentation were still reading `line_mask`, it could not see it.
    lines = np.full((300, 400), 255, dtype=np.uint8)
    cv2.rectangle(lines, (10, 10), (390, 290), 0, 3)
    cv2.line(lines, (200, 10), (200, 290), 0, 3)

    session = Session(tmp_path / "work", extractor=FakeExtractor(lines))
    session.load_page(page)
    session.detect_panels()
    session.segment_zones()

    assert session.extractor.calls == 1
    assert np.array_equal(session.structural_mask(), binarise_lines(lines))

    panel = session.panels[0]
    left = panel.label_map[150, 100]
    right = panel.label_map[150, 300]
    assert left != UNASSIGNED and right != UNASSIGNED
    assert left != right, "the divider the extractor drew did not split the panel"


def test_the_extractor_never_sees_a_second_page_worth_of_work(tmp_path):
    """Cached per page: it is seconds on a GPU and minutes on a CPU."""
    page = brush_page(tmp_path)
    lines = np.full((300, 400), 255, dtype=np.uint8)
    cv2.rectangle(lines, (10, 10), (390, 290), 0, 3)

    session = Session(tmp_path / "work", extractor=FakeExtractor(lines))
    session.load_page(page)
    session.detect_panels()
    session.segment_zones()
    session.segment_zones()

    assert session.extractor.calls == 1

    session.load_page(page)
    session.detect_panels()
    session.segment_zones()
    assert session.extractor.calls == 2, "a new page must re-extract"


def test_panels_and_bubbles_still_read_the_raw_ink(tmp_path):
    """Deliberate, not an oversight.

    `segment_panels` needs a spot black to stay solid or the gutter network
    leaks through it, and `detect_bubbles` reads glyphs as filled components —
    the extractor turns both into contours.
    """
    page = brush_page(tmp_path)
    # An extractor that returns a blank page. If panel detection went through
    # it, there would be no panel at all.
    blank = np.full((300, 400), 255, dtype=np.uint8)

    session = Session(tmp_path / "work", extractor=FakeExtractor(blank))
    session.load_page(page)

    assert session.detect_panels(), "panel detection must not depend on the extractor"
    session.detect_bubbles()
    assert session.extractor.calls == 0, "neither step may pay for extraction"


def test_flats_still_reach_under_the_artists_real_ink(tmp_path):
    """§10. The layer dropped on top is raw ink, so that is what flats fill under.

    The extractor collapses a 25px stroke toward its centre; if expansion used
    the structural mask, the rest of that stroke would export as a white seam.
    """
    page = brush_page(tmp_path)
    lines = np.full((300, 400), 255, dtype=np.uint8)
    cv2.rectangle(lines, (10, 10), (390, 290), 0, 3)
    cv2.line(lines, (60, 40), (60, 260), 0, 3)  # the stroke, one pixel wide-ish

    session = Session(tmp_path / "work", extractor=FakeExtractor(lines))
    session.load_page(page)
    session.detect_panels()
    session.segment_zones()

    panel = session.panels[0]
    stroke = session.line_mask[150, 55:70]
    assert stroke.any(), "fixture no longer has thick ink here"
    covered = panel.label_map[150 - panel.y, 55 - panel.x : 70 - panel.x]
    assert (covered != UNASSIGNED).all(), "raw ink left unpainted under the line"


@pytest.mark.skipif(not WEIGHTS.exists(), reason="erika.pth not vendored")
def test_the_real_extractor_thins_ink(tmp_path):
    """MangaLineExtraction on the actual fixture, not a stand-in.

    §2.2's teddy note: the extractor converts solid fills into their contours,
    so the ink fraction collapses while the structure survives. That is the
    property the app depends on, so it is measured rather than assumed.
    """
    pytest.importorskip("torch")
    from comiccolor.extract.manga_line import MangaLineExtractor
    from comiccolor.segmentation.preprocess import ink_fraction
    from comiccolor.web.session import _best_device

    page = brush_page(tmp_path)
    session = Session(
        tmp_path / "work", extractor=MangaLineExtractor(device=_best_device())
    )
    session.load_page(page)

    raw = ink_fraction(session.line_mask)
    structural = ink_fraction(session.structural_mask())

    assert structural < raw, f"extractor did not thin the ink ({structural} vs {raw})"


def test_a_spot_black_is_not_a_zone_of_its_own(tmp_path):
    """The extractor's one bad case, removed without giving the extractor up.

    A solid black comes back from the extractor as its outline, so the fill is
    open and trapped-ball returns the inside as a region. The artist could
    select their own black hair, recolour it, and watch nothing happen: their
    ink layer composites over the flat. `drop_inked_zones` takes it, and the
    pixels it took are held back from expansion too — otherwise every
    neighbour floods in and they meet in the middle of the black, which reads
    on screen as zones running straight across the stroke.
    """
    page = brush_page(tmp_path)

    # What MangaLineExtraction does to a fill: keep the outline, drop the ink.
    lines = np.full((300, 400), 255, dtype=np.uint8)
    cv2.rectangle(lines, (10, 10), (390, 290), 0, 3)
    cv2.rectangle(lines, (200, 60), (330, 200), 0, 3)

    session = Session(tmp_path / "work", extractor=FakeExtractor(lines))
    session.load_page(page)
    session.detect_panels()
    session.segment_zones()

    panel = session.panels[0]
    black = panel.label_map[70:190, 210:320]   # well inside the solid black

    assert (black == UNASSIGNED).all(), "the spot black still carries zones"
    assert len(set(np.unique(black)) - {UNASSIGNED}) == 0

    # The drawing either side of it is untouched.
    assert panel.label_map[130, 350] != UNASSIGNED
