"""§1.7. The two decisions that look like tuning and are not.

Mode-not-average and L*-downweighting are both stated in the spec as the
reason the flats come out usable rather than muddy. Both are one constant away
from being silently undone, so both are pinned here.
"""

from __future__ import annotations

import numpy as np

from comiccolor.colour.snap import (
    SNAP_MAX_DELTA,
    assign_zones,
    nearest_entry,
    zone_modes,
)
from comiccolor.model.entities import PaletteEntry


def entry(id_: int, rgb: tuple[int, int, int]) -> PaletteEntry:
    return PaletteEntry(project_id=0, rgb=rgb, label=f"e{id_}", id=id_)


def test_mode_beats_average_on_a_bimodal_zone():
    """A shaded zone is bimodal; the average lands where nothing is.

    Two thirds skin, one third a dark outline. The average is a muddy colour
    that appears nowhere in the zone. The mode is the skin.
    """
    label_map = np.ones((30, 30), dtype=np.int32)
    proposal = np.zeros((30, 30, 3), dtype=np.uint8)
    proposal[:20] = (232, 190, 160)  # skin
    proposal[20:] = (40, 30, 30)  # outline

    mode = zone_modes(proposal, label_map)[1]
    average = proposal.reshape(-1, 3).mean(axis=0)

    assert np.allclose(mode, (232, 190, 160), atol=8)
    assert abs(mode[0] - average[0]) > 50


def test_mode_averages_within_the_winning_bin():
    """Sub-bin precision: anti-aliasing inside one bin still moves the answer."""
    label_map = np.ones((10, 10), dtype=np.int32)
    proposal = np.zeros((10, 10, 3), dtype=np.uint8)
    proposal[:, :5] = (100, 100, 100)
    proposal[:, 5:] = (108, 108, 108)  # same 16-wide bin as 100

    assert zone_modes(proposal, label_map)[1] == (104, 104, 104)


def test_unassigned_pixels_never_contribute():
    label_map = np.zeros((10, 10), dtype=np.int32)
    label_map[:5] = 1
    proposal = np.zeros((10, 10, 3), dtype=np.uint8)
    proposal[:5] = (200, 100, 50)
    proposal[5:] = (0, 255, 0)  # line and protected pixels

    modes = zone_modes(proposal, label_map)
    assert set(modes) == {1}
    assert modes[1] == (200, 100, 50)


def test_shading_does_not_split_one_flat_in_two():
    """The L* downweight, stated as its consequence.

    Lit skin and shadowed skin differ almost only in lightness. Weighted
    equally they read as two colours and snap to two entries, and the
    colourist gets two flats where they wanted one.
    """
    palette = [entry(1, (232, 190, 160)), entry(2, (70, 60, 130))]

    lit, lit_distance = nearest_entry((240, 200, 172), palette)
    shadowed, shadow_distance = nearest_entry((150, 120, 100), palette)

    assert lit.id == shadowed.id == 1
    assert shadow_distance <= SNAP_MAX_DELTA


def test_a_distant_colour_is_flagged_not_snapped():
    """§1.7 reject-before-snapping. A wrong snap is worse than an extra entry."""
    palette = [entry(1, (232, 190, 160))]
    label_map = np.ones((8, 8), dtype=np.int32)
    proposal = np.full((8, 8, 3), (20, 200, 60), dtype=np.uint8)  # nothing like skin

    assignments, created = assign_zones(proposal, label_map, palette, next_id=99)

    assert len(created) == 1
    assert assignments[0].flagged is True
    assert assignments[0].palette_entry_id == 99
    assert palette == [entry(1, (232, 190, 160))]  # the caller's list is untouched


def test_no_palette_means_every_zone_gets_its_own_entry():
    """The palette-less path: nothing to snap to, so nothing is merged."""
    label_map = np.zeros((10, 30), dtype=np.int32)
    label_map[:, :10] = 1
    label_map[:, 10:20] = 2
    label_map[:, 20:] = 3
    proposal = np.zeros((10, 30, 3), dtype=np.uint8)
    proposal[:, :10] = (200, 10, 10)
    proposal[:, 10:20] = (202, 12, 12)  # near-identical, must NOT be merged
    proposal[:, 20:] = (10, 10, 200)

    assignments, created = assign_zones(proposal, label_map, [], threshold=None)

    assert len({a.palette_entry_id for a in assignments}) == 3
    assert len(created) == 3
    assert not any(a.flagged for a in assignments)


def test_assignments_carry_ids_not_colours():
    """Rule 1, structurally: there is nowhere on a ZoneAssignment for an RGB."""
    label_map = np.ones((4, 4), dtype=np.int32)
    proposal = np.full((4, 4, 3), 128, dtype=np.uint8)

    assignment = assign_zones(proposal, label_map, [], threshold=None)[0][0]

    assert not hasattr(assignment, "rgb")
    assert isinstance(assignment.palette_entry_id, int)
