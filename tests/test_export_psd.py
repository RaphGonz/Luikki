"""§1.10 / §G3 export. One layer per plane — or a group per plane, one layer
per colour inside it — and no line art unless asked for.

Rules 1 and 7 are both properties of the written file rather than of any call
site, so both are checked by reopening the PSD.
"""

from __future__ import annotations

import numpy as np
import pytest

from luikki.export.flat_colours import FLAT_PALETTE, adjacency, assign_flat_colours
from luikki.export.psd import PanelFlats, flats_preview, layer_count, write_psd
from luikki.model.entities import PaletteEntry
from luikki.segmentation.planes import CHARACTER, FAR, NEAR

psd_tools = pytest.importorskip("psd_tools")


def palette() -> dict[int, PaletteEntry]:
    return {
        1: PaletteEntry(project_id=0, rgb=(200, 30, 40), label="hair", id=1),
        2: PaletteEntry(project_id=0, rgb=(30, 80, 200), label="coat", id=2),
    }


def two_panels(planes=None) -> list[PanelFlats]:
    left = np.zeros((40, 40), dtype=np.int32)
    left[5:20, 5:20] = 1
    left[22:35, 5:20] = 2

    right = np.zeros((40, 40), dtype=np.int32)
    right[10:30, 10:30] = 1

    return [
        PanelFlats(order=0, x=0, y=0, label_map=left, assignments={1: 1, 2: 2},
                   planes=None if planes is None else planes[0]),
        PanelFlats(order=1, x=50, y=0, label_map=right, assignments={1: 1},
                   planes=None if planes is None else planes[1]),
    ]


def names(path) -> list[str]:
    return [layer.name for layer in psd_tools.PSDImage.open(path)]


def test_without_planes_the_page_is_one_layer_of_flats(tmp_path):
    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(), palette())
    assert names(path) == ["Flats"]


def test_one_layer_per_plane_characters_on_top(tmp_path):
    planes = [{1: CHARACTER, 2: FAR}, {1: NEAR}]
    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(planes), palette())
    # psd-tools lists bottom to top.
    assert names(path) == ["Background", "Foreground", "Characters"]


def test_balloons_sit_above_the_planes(tmp_path):
    balloon = np.zeros((40, 100), bool)
    balloon[2:8, 60:90] = True
    path = write_psd(
        tmp_path / "flats.psd", (100, 40), two_panels([{1: FAR, 2: FAR}, {1: FAR}]), palette(),
        balloons=[balloon],
    )
    assert names(path) == ["Background", "Balloons"]


def test_the_app_names_the_layers_in_the_artists_language(tmp_path):
    path = write_psd(
        tmp_path / "flats.psd", (100, 40), two_panels(), palette(), names={"flats": "Aplats"}
    )
    assert names(path) == ["Aplats"]


def test_by_colour_a_group_per_plane(tmp_path):
    planes = [{1: NEAR, 2: NEAR}, {1: FAR}]
    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(planes), palette(), "colour")
    groups = [layer for layer in psd_tools.PSDImage.open(path) if layer.is_group()]
    assert [group.name for group in groups] == ["Background", "Foreground"]
    assert [sorted(layer.name for layer in group) for group in groups] == [["hair"], ["coat", "hair"]]


def test_layer_colour_comes_from_the_palette_entry(tmp_path):
    """Rule 1: nothing between the zone map and the layer holds an RGB."""
    recoloured = palette()
    recoloured[1] = PaletteEntry(project_id=0, rgb=(5, 250, 15), label="hair", id=1)

    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(), recoloured, "colour")
    hair = next(
        layer
        for layer in psd_tools.PSDImage.open(path).descendants()
        if layer.name == "hair"
    )

    # `composite`, not `topil`: the document is RGB, so psd-tools puts the
    # layer's transparency in a layer mask rather than in a fourth channel.
    pixels = np.asarray(hair.composite().convert("RGBA"))
    opaque = pixels[pixels[:, :, 3] > 0]
    assert np.allclose(opaque[:, :3], (5, 250, 15), atol=2)


def test_layers_are_cropped_to_what_they_cover(tmp_path):
    """A page-sized transparent layer per colour is the 400 MB failure mode."""
    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(), palette(), "colour")
    coat = next(
        layer
        for layer in psd_tools.PSDImage.open(path).descendants()
        if layer.name == "coat"
    )
    assert coat.size == (15, 13)
    assert coat.offset == (5, 22)

    flats = psd_tools.PSDImage.open(write_psd(tmp_path / "p.psd", (100, 40), two_panels(), palette()))[0]
    assert flats.offset == (5, 5)
    assert flats.size == (75, 30)


def test_unassigned_zones_emit_nothing(tmp_path):
    """A zone with no colour stays a hole, not a black patch."""
    label_map = np.zeros((20, 20), dtype=np.int32)
    label_map[2:10, 2:10] = 1
    label_map[12:18, 2:10] = 7  # segmented, never assigned

    path = write_psd(
        tmp_path / "flats.psd",
        (20, 20),
        [PanelFlats(order=0, x=0, y=0, label_map=label_map, assignments={1: 1})],
        palette(),
        "colour",
    )
    layers = [layer for layer in psd_tools.PSDImage.open(path).descendants() if not layer.is_group()]
    assert len(layers) == 1


def test_written_preview_matches_the_layers(tmp_path):
    """Guards the private-API shortcut in `_set_preview`: if a psd-tools
    upgrade moves `_record` or `_updated`, this is where it surfaces."""
    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(), palette())
    preview = np.asarray(psd_tools.PSDImage.open(path).topil().convert("RGB"))

    assert tuple(preview[10, 10]) == (200, 30, 40)
    assert tuple(preview[25, 10]) == (30, 80, 200)
    assert tuple(preview[15, 60]) == (200, 30, 40)
    assert tuple(preview[0, 45]) == (255, 255, 255)  # gutter stays paper


def test_preview_and_export_agree_on_colour():
    """The UI must not be a second renderer that can drift from the file."""
    preview = flats_preview((100, 40), two_panels(), palette())

    assert tuple(preview[10, 10][:3]) == (200, 30, 40)
    assert tuple(preview[25, 10][:3]) == (30, 80, 200)
    assert tuple(preview[15, 60][:3]) == (200, 30, 40)  # second panel, offset applied
    assert preview[0, 0][3] == 0  # nothing outside a zone


@pytest.mark.parametrize("granularity", ["plane", "colour"])
@pytest.mark.parametrize("planes", [None, [{1: CHARACTER, 2: FAR}, {1: NEAR}]])
def test_the_announced_layer_count_is_the_written_one(tmp_path, granularity, planes):
    panels, entries = two_panels(planes), palette()
    balloon = np.zeros((40, 100), bool)
    balloon[2:5, 2:5] = True
    path = write_psd(
        tmp_path / "flats.psd", (100, 40), panels, entries, granularity, balloons=[balloon]
    )

    written = [
        layer
        for layer in psd_tools.PSDImage.open(path).descendants()
        if not layer.is_group()
    ]
    assert len(written) == layer_count(panels, entries, granularity, balloons=1)


def test_an_unknown_granularity_is_refused(tmp_path):
    with pytest.raises(ValueError):
        write_psd(tmp_path / "flats.psd", (100, 40), two_panels(), palette(), "panel")


def test_the_supporting_grey_is_the_ink_twice(tmp_path):
    """The one export that carries line art, and only when asked for. Print
    colourists build it by hand: the ink on Multiply so it darkens the flats,
    and under it the same ink at 20% grey with its transparency locked, which
    makes a stencil of the drawing to paint the line's support into."""
    from psd_tools.constants import BlendMode

    from luikki.export.psd import SUPPORT_GREY

    ink = np.zeros((40, 100), dtype=bool)
    ink[10:14, 5:55] = True

    plain = psd_tools.PSDImage.open(
        write_psd(tmp_path / "plain.psd", (100, 40), two_panels(), palette())
    )
    assert not [layer for layer in plain if layer.name in {"Lines", "Support grey"}]

    path = write_psd(
        tmp_path / "support.psd",
        (100, 40),
        two_panels(),
        palette(),
        line_mask=ink,
        support_grey=True,
    )
    psd = psd_tools.PSDImage.open(path)
    # Written last, so both sit above every flat.
    assert [layer.name for layer in psd][-2:] == ["Support grey", "Lines"]

    grey, lines = psd[-2], psd[-1]
    assert lines.blend_mode == BlendMode.MULTIPLY
    assert grey.locks.transparency
    patch = np.array(grey.numpy())[..., :3]
    assert np.allclose(patch.reshape(-1, 3)[0] * 255, SUPPORT_GREY, atol=1)
    assert (grey.height, grey.width) == (4, 50)


def test_the_supporting_grey_needs_the_ink(tmp_path):
    with pytest.raises(ValueError, match="line mask"):
        write_psd(
            tmp_path / "no.psd", (100, 40), two_panels(), palette(), support_grey=True
        )


# -- the fake flats ------------------------------------------------------------


def _grid(rows: int, cols: int, cell: int = 6) -> np.ndarray:
    """A chessboard of zones, every one touching eight others."""
    labels = np.zeros((rows * cell, cols * cell), np.int32)
    for row in range(rows):
        for col in range(cols):
            labels[row * cell : (row + 1) * cell, col * cell : (col + 1) * cell] = row * cols + col + 1
    return labels


def test_touching_zones_never_share_a_colour():
    """What lets a magic wand take one zone: its neighbours, diagonals
    included, are all another colour."""
    labels = _grid(6, 7)
    colours = assign_flat_colours((labels.shape[1], labels.shape[0]), [(0, 0, labels)])[0]
    for a, b in adjacency(labels).tolist():
        assert colours[a] != colours[b], (a, b)
    assert set(colours.values()) <= {entry.id for entry in FLAT_PALETTE}


def test_zones_meeting_across_a_panel_edge_differ_too():
    left = np.ones((10, 10), np.int32)
    right = np.ones((10, 10), np.int32)
    colours = assign_flat_colours((20, 10), [(0, 0, left), (10, 0, right)])
    assert colours[0][1] != colours[1][1]


def test_the_eight_colours_are_spread_over_the_page():
    """Not two colours doing all the work: that read as a chequerboard."""
    labels = np.zeros((10, 160), np.int32)
    for index in range(16):
        labels[2:8, index * 10 + 2 : index * 10 + 8] = index + 1
    colours = assign_flat_colours((160, 10), [(0, 0, labels)])[0]
    assert sorted(np.bincount(list(colours.values()))[1:].tolist()) == [2] * 8
