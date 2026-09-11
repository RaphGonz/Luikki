"""Step 6. Snapping is a stage the artist can see, disagree with and undo.

Flats used to resolve a zone's colour and snap it in one pass, which made
snapping the only step of the pipeline with no boundary — nothing to inspect,
nothing to refuse. These pin the split: flats propose, the artist snaps, and
nothing merges zones behind their back.
"""

from __future__ import annotations

import numpy as np
import pytest

from luikki.colour.segments import build_segments
from luikki.colour.snap import SNAP_MAX_DELTA
from luikki.model.masks import UNASSIGNED
from luikki.web.session import Session, StepError


def _page(path, size=(64, 96)):
    """A two-panel page: black frames on white, nothing inside them."""
    import cv2

    height, width = size
    page = np.full((height, width), 255, np.uint8)
    cv2.rectangle(page, (4, 4), (width - 5, height // 2 - 4), 0, 2)
    cv2.rectangle(page, (4, height // 2 + 4), (width - 5, height - 5), 0, 2)
    cv2.imwrite(str(path), page)
    return path


def _sheet(path, colours=((200, 30, 40), (30, 90, 200))):
    import cv2

    band = np.zeros((16, 16 * len(colours), 3), np.uint8)
    for i, colour in enumerate(colours):
        band[:, i * 16 : (i + 1) * 16] = colour[::-1]
    cv2.imwrite(str(path), band)
    return path


def _ready(tmp_path, with_sheet=True):
    session = Session(tmp_path / "work")
    if with_sheet:
        # A reference offers colours; the palette is what the artist took.
        # These tests want the whole sheet in, which is a choice they have to
        # make like anyone else.
        stored = session.add_reference(
            _sheet(tmp_path / "sheet.png"), original_name="sheet.png"
        )
        for rgb in session.candidates(stored[0].id):
            session.include_candidate(stored[0].id, rgb)
    session.load_page(_page(tmp_path / "page.png"), original_name="page.png")
    session.detect_panels()
    session.segment_zones()
    session.generate_flats()
    return session


def test_flats_never_snap(tmp_path):
    """The split, stated as its consequence.

    Every segment comes out of flats holding its own colour, even though a
    reference palette is loaded and some of those colours are certainly within
    SNAP_MAX_DELTA of it. Anything else is the old invisible step returning.
    """
    session = _ready(tmp_path)

    assert session.segments, "flats must produce segments"
    assert not any(segment.snapped for segment in session.segments)

    entry_ids = {segment.palette_entry_id for segment in session.segments}
    chosen_ids = {entry.id for entry in session._palette}
    assert not (entry_ids & chosen_ids), "a segment was snapped by generate_flats"


def test_each_segment_keeps_its_own_entry(tmp_path):
    """No merging. Two segments that agree on colour are still two segments."""
    session = _ready(tmp_path)

    keys = [segment.key for segment in session.segments]
    assert len(keys) == len(set(keys))
    # One private entry each, so re-pointing one can never move another.
    assert len({s.palette_entry_id for s in session.segments}) == len(session.segments)


def test_a_click_finds_the_segment_under_it(tmp_path):
    session = _ready(tmp_path)
    target = max(session.segments, key=lambda s: s.area)

    found = session.segment_at(*target.anchor)

    assert found is not None and found.key == target.key


def test_a_click_outside_every_zone_finds_nothing(tmp_path):
    session = _ready(tmp_path)
    assert session.segment_at(-5, -5) is None


def test_snapping_one_segment_moves_only_that_segment(tmp_path):
    session = _ready(tmp_path)
    target = max(session.segments, key=lambda s: s.area)
    others = {s.key: s.palette_entry_id for s in session.segments if s.key != target.key}
    entry_id = session._palette[0].id

    session.snap_segment(target.panel, target.label, entry_id)

    assert target.palette_entry_id == entry_id
    assert target.snapped is True
    assert session.panels[target.panel].assignments[target.label] == entry_id
    assert {s.key: s.palette_entry_id for s in session.segments if s.key != target.key} == others


def test_a_snap_can_be_undone(tmp_path):
    """A decision the artist cannot reverse is not a decision they were offered."""
    session = _ready(tmp_path)
    target = session.segments[0]
    original = target.palette_entry_id

    session.snap_segment(target.panel, target.label, session._palette[0].id)
    session.unsnap_segment(target.panel, target.label)

    assert target.palette_entry_id == original
    assert target.snapped is False
    assert session.panels[target.panel].assignments[target.label] == original


def test_the_suggestion_never_offers_the_segment_itself(tmp_path):
    """Suggestions come from the reference half only.

    Every segment owns a private entry holding its own colour, so a suggestion
    drawn from the whole palette would return that entry at distance zero and
    the step would recommend doing nothing, always.
    """
    session = _ready(tmp_path)
    segment = session.segments[0]

    entry, distance = session.snap_suggestion(segment)

    assert entry is not None
    assert entry.id in {e.id for e in session._palette}
    assert distance > 0


def test_snap_all_respects_the_threshold(tmp_path):
    session = _ready(tmp_path)

    result = session.snap_all(threshold=0.0)

    assert result["snapped"] == 0
    assert result["skipped"] == result["segments"]
    assert not any(segment.snapped for segment in session.segments)


def test_snap_all_without_a_threshold_snaps_everything(tmp_path):
    """The deliberate override — every segment onto its nearest palette colour."""
    session = _ready(tmp_path)

    result = session.snap_all(threshold=None)

    assert result["snapped"] == len(session.segments)
    chosen_ids = {entry.id for entry in session._palette}
    assert all(s.palette_entry_id in chosen_ids for s in session.segments)


def test_snap_all_has_no_guard_by_default(tmp_path):
    """No threshold means every segment lands on a colour the artist chose."""
    session = _ready(tmp_path)

    result = session.snap_all()

    assert result["snapped"] == len(session.segments)
    assert result["skipped"] == 0


def test_snap_all_goes_through_the_same_door_as_a_click(tmp_path):
    """Bulk must not be able to do what clicking cannot, so it stays undoable."""
    session = _ready(tmp_path)
    session.snap_all(threshold=None)

    for segment in list(session.segments):
        session.unsnap_segment(segment.panel, segment.label)

    assert not any(segment.snapped for segment in session.segments)


def test_snapping_before_flats_is_refused(tmp_path):
    session = Session(tmp_path / "work")
    session.load_page(_page(tmp_path / "page.png"), original_name="page.png")
    session.detect_panels()
    session.segment_zones()

    with pytest.raises(StepError):
        session.snap_all()


def test_segments_are_dropped_when_segmentation_is_rerun(tmp_path):
    """Re-running a step clears what depended on it — segments included."""
    session = _ready(tmp_path)
    assert session.segments

    session.detect_panels()

    assert session.segments == []


def test_build_segments_anchors_inside_the_zone(tmp_path):
    """A crescent's bounding-box centre is not in the crescent."""
    label_map = np.full((20, 20), UNASSIGNED, np.int32)
    label_map[2:18, 2:6] = 7          # a tall bar, hollow centre of the bbox
    label_map[2:6, 6:18] = 7

    segment = build_segments(0, label_map, {7: 3}, (0, 0))[0]
    x, y = segment.anchor

    assert label_map[y, x] == 7
    assert segment.area == int((label_map == 7).sum())


def test_build_segments_anchors_a_zone_in_two_pieces():
    """The mean of the two middle rows can be a row the zone is not on.

    Zones come out of absorption and the orphan pass in several pieces; this
    one's pixel rows are 0, 0, 3, 3 and `np.median` put the anchor on row 1,
    which crashed `Generate flats` on `teddy_page`.
    """
    label_map = np.full((5, 5), UNASSIGNED, np.int32)
    label_map[0, 0:2] = 7
    label_map[3, 0:2] = 7

    segment = build_segments(0, label_map, {7: 3}, (0, 0))[0]
    x, y = segment.anchor

    assert label_map[y, x] == 7
