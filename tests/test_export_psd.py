"""§1.10 export. One group per panel, one layer per colour, no line art.

Rules 1 and 7 are both properties of the written file rather than of any call
site, so both are checked by reopening the PSD.
"""

from __future__ import annotations

import numpy as np
import pytest

from luikki.export.psd import PanelFlats, flats_preview, write_psd
from luikki.model.entities import PaletteEntry

psd_tools = pytest.importorskip("psd_tools")


def palette() -> dict[int, PaletteEntry]:
    return {
        1: PaletteEntry(project_id=0, rgb=(200, 30, 40), label="hair", id=1),
        2: PaletteEntry(project_id=0, rgb=(30, 80, 200), label="coat", id=2),
    }


def two_panels() -> list[PanelFlats]:
    left = np.zeros((40, 40), dtype=np.int32)
    left[5:20, 5:20] = 1
    left[22:35, 5:20] = 2

    right = np.zeros((40, 40), dtype=np.int32)
    right[10:30, 10:30] = 1

    return [
        PanelFlats(order=0, x=0, y=0, label_map=left, assignments={1: 1, 2: 2}),
        PanelFlats(order=1, x=50, y=0, label_map=right, assignments={1: 1}),
    ]


def test_group_per_panel_layer_per_colour(tmp_path):
    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(), palette())
    reopened = psd_tools.PSDImage.open(path)

    groups = [layer for layer in reopened if layer.is_group()]
    assert [group.name for group in groups] == ["Panel 1", "Panel 2"]
    assert [len(group) for group in groups] == [2, 1]
    assert {layer.name for layer in groups[0]} == {"hair", "coat"}


def test_layer_colour_comes_from_the_palette_entry(tmp_path):
    """Rule 1: nothing between the zone map and the layer holds an RGB."""
    recoloured = palette()
    recoloured[1] = PaletteEntry(project_id=0, rgb=(5, 250, 15), label="hair", id=1)

    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(), recoloured)
    hair = next(
        layer
        for layer in psd_tools.PSDImage.open(path).descendants()
        if layer.name == "hair"
    )

    pixels = np.asarray(hair.topil().convert("RGBA"))
    opaque = pixels[pixels[:, :, 3] > 0]
    assert np.allclose(opaque[:, :3], (5, 250, 15), atol=2)


def test_layers_are_cropped_to_the_colour_not_the_page(tmp_path):
    """A page-sized transparent layer per colour is the 400 MB failure mode."""
    path = write_psd(tmp_path / "flats.psd", (100, 40), two_panels(), palette())
    coat = next(
        layer
        for layer in psd_tools.PSDImage.open(path).descendants()
        if layer.name == "coat"
    )

    assert coat.size == (15, 13)
    assert coat.offset == (5, 22)


def test_unassigned_zones_emit_nothing(tmp_path):
    """A zone nothing proposed a colour for stays a hole, not a black patch."""
    label_map = np.zeros((20, 20), dtype=np.int32)
    label_map[2:10, 2:10] = 1
    label_map[12:18, 2:10] = 7  # segmented, never assigned

    path = write_psd(
        tmp_path / "flats.psd",
        (20, 20),
        [PanelFlats(order=0, x=0, y=0, label_map=label_map, assignments={1: 1})],
        palette(),
    )
    layers = [layer for layer in psd_tools.PSDImage.open(path).descendants() if not layer.is_group()]
    assert len(layers) == 1


def test_written_preview_matches_the_layers(tmp_path):
    """Guards the private-API shortcut in `_set_preview`.

    The export fills the PSD's flattened preview itself instead of letting
    psd-tools re-composite every layer, which is the difference between a
    fifteen-second export and an eight-minute one. If a psd-tools upgrade
    moves `_record` or `_updated`, this is where it surfaces.
    """
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
