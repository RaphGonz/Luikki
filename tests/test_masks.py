import numpy as np
import pytest

from luikki.model.masks import (
    UNASSIGNED,
    LabelMapInvariantError,
    assert_invariant,
    check_coverage,
    load_label_map,
    region_count,
    region_stats,
    relabel_sequential,
    save_label_map,
)


def test_region_stats_areas_and_boxes():
    labels = np.zeros((10, 10), dtype=np.int32)
    labels[2:5, 3:7] = 1  # 3x4 = 12 px at (3, 2)
    labels[7:9, 1:3] = 2  # 2x2 = 4 px at (1, 7)

    stats = region_stats(labels)
    assert stats[1] == (12, (3, 2, 4, 3))
    assert stats[2] == (4, (1, 7, 2, 2))
    assert region_count(labels) == 2


def test_region_stats_ignores_gaps_in_label_numbering():
    labels = np.zeros((4, 4), dtype=np.int32)
    labels[0, 0] = 1
    labels[1, 1] = 5  # 2, 3, 4 unused
    stats = region_stats(labels)
    assert set(stats) == {1, 5}
    assert region_count(labels) == 2


def test_coverage_detects_unassigned_fillable_pixels():
    line = np.zeros((6, 6), dtype=bool)
    line[3, :] = True

    labels = np.zeros((6, 6), dtype=np.int32)
    labels[:3, :] = 1
    # Bottom half deliberately left unassigned.

    report = check_coverage(labels, line)
    assert report["exhaustive"] is False
    assert report["uncovered_pixels"] == 12
    assert report["leaked_pixels"] == 0


def test_coverage_detects_leaks_onto_lines():
    line = np.zeros((4, 4), dtype=bool)
    line[0, :] = True

    labels = np.ones((4, 4), dtype=np.int32)  # covers the line row too

    report = check_coverage(labels, line)
    assert report["exhaustive"] is True
    assert report["leaked_pixels"] == 4


def test_coverage_excludes_protected_area():
    line = np.zeros((4, 4), dtype=bool)
    protected = np.zeros((4, 4), dtype=bool)
    protected[0:2, 0:2] = True

    labels = np.zeros((4, 4), dtype=np.int32)
    labels[protected == False] = 1  # noqa: E712 - explicit for clarity

    report = check_coverage(labels, line, protected)
    assert report["exhaustive"] is True


def test_exclusivity_is_structural():
    """A pixel holds one label. Overlap is not representable."""
    labels = np.zeros((5, 5), dtype=np.int32)
    labels[1:4, 1:4] = 1
    labels[2:3, 2:3] = 2  # "adding" region 2 necessarily removes those px from 1

    stats = region_stats(labels)
    assert stats[1][0] + stats[2][0] == 9
    assert stats[2][0] == 1


def test_relabel_sequential_compacts_and_keeps_zero():
    labels = np.array([[0, 3], [7, 3]], dtype=np.int32)
    out = relabel_sequential(labels)
    assert out[0, 0] == UNASSIGNED
    assert sorted(np.unique(out)) == [0, 1, 2]
    assert out[0, 1] == out[1, 1]


def test_label_map_roundtrip(tmp_path):
    labels = np.random.default_rng(0).integers(0, 40, size=(64, 48)).astype(np.int32)
    path = tmp_path / "panel.npz"
    save_label_map(path, labels)
    assert np.array_equal(load_label_map(path), labels)


def test_assert_invariant_passes_on_a_fully_covered_map():
    """A fully-labelled, non-leaking map raises nothing."""
    line = np.zeros((4, 4), dtype=bool)
    line[0, :] = True

    labels = np.zeros((4, 4), dtype=np.int32)
    labels[1:, :] = 1

    assert_invariant(labels, line)  # must not raise


def test_assert_invariant_raises_on_uncovered_pixels():
    """A gap — a fillable pixel with no label — raises with the count in
    the message, not a bare 'invariant violated'."""
    line = np.zeros((6, 6), dtype=bool)
    line[3, :] = True

    labels = np.zeros((6, 6), dtype=np.int32)
    labels[:3, :] = 1
    # Bottom half deliberately left unassigned: 12 uncovered pixels.

    with pytest.raises(LabelMapInvariantError) as excinfo:
        assert_invariant(labels, line)
    assert "12" in str(excinfo.value)


def test_assert_invariant_ignores_protected_pixels():
    """A protected region carrying label 0 is correct, not a violation."""
    line = np.zeros((4, 4), dtype=bool)
    protected = np.zeros((4, 4), dtype=bool)
    protected[0:2, 0:2] = True

    labels = np.zeros((4, 4), dtype=np.int32)
    labels[protected == False] = 1  # noqa: E712 - explicit for clarity

    assert_invariant(labels, line, protected)  # must not raise


def test_assert_invariant_raises_on_a_label_leaking_onto_a_line():
    """A label sitting on a line pixel is a leak, not a gap — ``check_coverage``
    still reports ``exhaustive: True`` for this, so the leak needs its own
    check rather than riding along on the exhaustiveness one."""
    line = np.zeros((4, 4), dtype=bool)
    line[0, :] = True

    labels = np.ones((4, 4), dtype=np.int32)  # covers the line row too

    with pytest.raises(LabelMapInvariantError) as excinfo:
        assert_invariant(labels, line)
    assert "4" in str(excinfo.value)


def test_exclusivity_needs_no_check():
    """Extends ``test_exclusivity_is_structural``: after writing label 2 over
    part of label 1, the areas sum to the original, so overlap is
    unrepresentable and ``assert_invariant`` has nothing to check for it — a
    fully-covered, non-leaking map with a "second write" baked in passes the
    same as any other fully-covered map."""
    line = np.zeros((5, 5), dtype=bool)

    labels = np.zeros((5, 5), dtype=np.int32)
    labels[1:4, 1:4] = 1
    labels[2:3, 2:3] = 2  # "adding" region 2 necessarily removes those px from 1

    stats = region_stats(labels)
    assert stats[1][0] + stats[2][0] == 9

    labels[0, :] = 1
    labels[4, :] = 1
    labels[:, 0] = 1
    labels[:, 4] = 1
    assert_invariant(labels, line)  # must not raise: fully covered, no leak
