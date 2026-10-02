"""§1.10 / §G3 Layered export. PSD, one layer per plane — or per colour.

P4 settled the format: `.clip` is an undocumented SQLite container, and Clip
Studio imports PSD with groups intact, so one path serves both applications
and matches what studios already pass around.

The stack, top to bottom (ROADMAP G3):

    [Lines, Support grey]   only when asked for (`support_grey`)
    Balloons                the balloon shapes, filled
    Characters              the zones the artist called characters
    Foreground              1st plane
    Middle ground           2nd plane
    Background              the rest

A page whose planes were skipped has one layer, **Flats**, under the balloons.
About five layers a page, where one layer per colour used to make 956.

Inside a layer every zone has one of eight fake colours, and two zones that
touch never share one (`flat_colours`): the colourist takes a zone with the
magic wand, as on flats made by hand, and replaces the colour.

Two rules from the spec are enforced here rather than trusted:

- **No line art in an export the artist did not ask for** (rule 7). The one
  exception is `support_grey`, asked for by name at the press — see
  `_write_support`.
- **Colour comes from the palette, by id** (rule 1). A zone holds a
  `palette_entry_id`, and its RGB is looked up at write time.

`granularity` is the artist's choice of stack: `"plane"` (the default) is the
stack above; `"colour"` turns each plane into a group with one layer per
colour inside it, for the artist who wants objects apart: 8 x 4 + 1 = 33
layers at most.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from ..model.entities import PaletteEntry
from ..model.masks import UNASSIGNED
from ..segmentation.planes import CHARACTER, FAR, MIDDLE, NEAR

GRANULARITIES = ("plane", "colour")

# What the ink is tinted to for the supporting layer: 20 % grey, the value
# print colourists lay under a line to keep it from breaking up on paper.
SUPPORT_GREY = (204, 204, 204)

# Balloons are paper: white, like the lettering's ground.
BALLOON_RGB = (255, 255, 255)

# Layer names, in English for the command line. The app sends its own, in the
# artist's language (`POST /api/export`).
LAYER_NAMES = {
    "balloons": "Balloons",
    "characters": "Characters",
    "near": "Foreground",
    "middle": "Middle ground",
    "far": "Background",
    "flats": "Flats",
    # One colour's layer inside a plane's group; `{n}` is its entry id.
    "colour": "Colour {n}",
    "lines": "Lines",
    "support": "Support grey",
}

# Bottom to top: the order the layers are created in.
_PLANE_STACK = ((FAR, "far"), (MIDDLE, "middle"), (NEAR, "near"), (CHARACTER, "characters"))


@dataclass
class PanelFlats:
    """One panel's zone map, its colours and its planes, ready to rasterise."""

    order: int

    x: int
    y: int
    label_map: np.ndarray

    assignments: dict[int, int] = field(default_factory=dict)
    # zone label -> plane. None when the artist skipped the planes.
    planes: dict[int, int] | None = None


def _labels_mask(label_map: np.ndarray, labels) -> np.ndarray:
    """Boolean mask covering every zone in `labels`."""
    lookup = np.zeros(int(label_map.max()) + 1, dtype=bool)
    for label in labels:
        if 0 < label < lookup.size:
            lookup[label] = True
    return lookup[label_map]


def _has_planes(panels: list[PanelFlats]) -> bool:
    return any(panel.planes is not None for panel in panels)


def _layers(panels: list[PanelFlats]) -> list[tuple[str, dict[int, list[int]]]]:
    """(name key, panel order -> its labels) per layer, bottom to top, empty ones left out."""
    if not _has_planes(panels):
        whole = {panel.order: list(panel.assignments) for panel in panels}
        return [("flats", whole)] if any(whole.values()) else []
    stack = []
    for plane, name in _PLANE_STACK:
        chosen = {
            panel.order: [
                label for label in panel.assignments if (panel.planes or {}).get(label, FAR) == plane
            ]
            for panel in panels
        }
        if any(chosen.values()):
            stack.append((name, chosen))
    return stack


def layer_count(
    panels: list[PanelFlats],
    palette: dict[int, PaletteEntry],
    granularity: str = "plane",
    balloons: int = 0,
) -> int:
    """How many layers `write_psd` would write, without writing them.

    Counted on ids and never on rasters: the sidebar asks for this on every
    state poll. That it agrees with the file is what `test_export_psd` checks.
    """
    by_order = {panel.order: panel for panel in panels}
    count = 1 if balloons else 0
    for _, chosen in _layers(panels):
        if granularity == "colour":
            count += len(
                {
                    by_order[order].assignments[label]
                    for order, labels in chosen.items()
                    for label in labels
                    if by_order[order].assignments[label] in palette
                }
            )
        else:
            count += 1
    return count


def write_psd(
    path: str | Path,
    page_size: tuple[int, int],
    panels: list[PanelFlats],
    palette: dict[int, PaletteEntry],
    granularity: str = "plane",
    line_mask: np.ndarray | None = None,
    support_grey: bool = False,
    balloons: list[np.ndarray] | None = None,
    names: dict[str, str] | None = None,
) -> Path:
    """Write the flats to `path`. Returns the path.

    `page_size` is `(width, height)` in page pixels. `balloons` are the
    balloon masks, page-sized. `names` overrides `LAYER_NAMES` key by key.

    `support_grey` adds the two ink layers a printer wants on top of the
    stack — see `_write_support`. It is the only thing that puts line art in
    an export, it is off unless asked for, and it needs `line_mask`.
    """
    from psd_tools import PSDImage

    if granularity not in GRANULARITIES:
        raise ValueError(
            f"unknown granularity {granularity!r}, expected one of {GRANULARITIES}"
        )
    named = {**LAYER_NAMES, **(names or {})}

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = page_size
    psd = PSDImage.new("RGB", (width, height), color=255)
    by_order = {panel.order: panel for panel in panels}

    for name, chosen in _layers(panels):
        if granularity == "colour":
            layers = []
            for entry_id in sorted(palette):
                mask = _page_mask(page_size, by_order, chosen, entry_id)
                if mask.any():
                    layers.append(
                        _ink_layer(psd, mask, palette[entry_id].rgb, named["colour"].format(n=entry_id))
                    )
            if layers:
                psd.create_group(layer_list=layers, name=named[name])
        else:
            _flats_layer(psd, page_size, by_order, chosen, palette, named[name])

    if balloons:
        ink = np.zeros((height, width), bool)
        for mask in balloons:
            ink |= mask
        if ink.any():
            _ink_layer(psd, ink, BALLOON_RGB, named["balloons"])

    if support_grey:
        if line_mask is None:
            raise ValueError("support_grey needs the line mask")
        _write_support(psd, line_mask, named)

    _set_preview(psd, page_size, panels, palette)
    psd.save(str(path))
    return path


def _page_mask(page_size, by_order, chosen, entry_id: int | None = None) -> np.ndarray:
    """The chosen zones of every panel on one page-sized mask, optionally of one colour."""
    width, height = page_size
    mask = np.zeros((height, width), dtype=bool)
    for order, labels in chosen.items():
        panel = by_order[order]
        if entry_id is not None:
            labels = [label for label in labels if panel.assignments.get(label) == entry_id]
        if not labels:
            continue
        patch = _labels_mask(panel.label_map, labels)
        rows = min(patch.shape[0], height - panel.y)
        cols = min(patch.shape[1], width - panel.x)
        if rows <= 0 or cols <= 0:
            continue
        window = mask[panel.y : panel.y + rows, panel.x : panel.x + cols]
        np.logical_or(window, patch[:rows, :cols], out=window)
    return mask


def _flats_layer(psd, page_size, by_order, chosen, palette, name: str):
    """One layer, every chosen zone in its own colour, cropped to what it covers."""
    width, height = page_size
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    for order, labels in chosen.items():
        panel = by_order[order]
        table = np.zeros((int(panel.label_map.max()) + 1, 4), dtype=np.uint8)
        for label in labels:
            entry = palette.get(panel.assignments.get(label))
            if entry is not None and 0 < label < table.shape[0]:
                table[label] = (*entry.rgb, 255)
        rows = min(panel.label_map.shape[0], height - panel.y)
        cols = min(panel.label_map.shape[1], width - panel.x)
        if rows <= 0 or cols <= 0:
            continue
        patch = table[panel.label_map[:rows, :cols]]
        painted = patch[:, :, 3] > 0
        window = rgba[panel.y : panel.y + rows, panel.x : panel.x + cols]
        window[painted] = patch[painted]
    covered = rgba[:, :, 3] > 0
    if not covered.any():
        return None
    rows = np.flatnonzero(covered.any(axis=1))
    cols = np.flatnonzero(covered.any(axis=0))
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    # The document is RGB, so psd-tools carries the layer's transparency as a
    # layer mask rather than a fourth channel. Photoshop and CSP honour it;
    # `layer.topil()` does not, which is why the tests read `composite()`.
    return psd.create_pixel_layer(
        Image.fromarray(np.ascontiguousarray(rgba[y0:y1, x0:x1]), mode="RGBA"),
        name=name,
        top=y0,
        left=x0,
    )


def _write_support(psd, line_mask: np.ndarray, named: dict[str, str]) -> None:
    """The supporting grey, on top of the flats: the ink, twice.

    What print colourists build by hand. **Lines** is the artist's ink set to
    Multiply, so it darkens the flats instead of covering them. **Support
    grey** underneath is the same ink at 20 % grey with its transparency
    locked, which turns it into a stencil of the drawing: paint into it and
    the paint can only land on the line, which is how a line is kept from
    breaking up at print size.

    Written last, so both sit above every flat.
    """
    from psd_tools.constants import BlendMode, ProtectedFlags, Tag
    from psd_tools.psd.tagged_blocks import ProtectedSetting

    ink = np.asarray(line_mask).astype(bool)
    if not ink.any():
        return

    grey = _ink_layer(psd, ink, SUPPORT_GREY, named["support"])
    # The tagged block directly, not `Layer.lock`: that helper reads the block
    # back before it has written one, so the flag never reaches the file
    # (psd-tools 1.18). Checked by the test, which reopens what was saved.
    grey.tagged_blocks.set_data(
        Tag.PROTECTED_SETTING, ProtectedSetting(int(ProtectedFlags.TRANSPARENCY))
    )
    _ink_layer(psd, ink, (0, 0, 0), named["lines"]).blend_mode = BlendMode.MULTIPLY


def _ink_layer(psd, ink: np.ndarray, colour: tuple[int, int, int], name: str):
    """One mask in one flat colour, cropped to what it covers."""
    rows = np.flatnonzero(ink.any(axis=1))
    cols = np.flatnonzero(ink.any(axis=0))
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    patch = ink[y0:y1, x0:x1]

    rgba = np.zeros((*patch.shape, 4), dtype=np.uint8)
    rgba[patch, :3] = colour
    rgba[patch, 3] = 255
    return psd.create_pixel_layer(
        Image.fromarray(rgba, mode="RGBA"), name=name, top=y0, left=x0
    )


def _set_preview(psd, page_size, panels, palette) -> None:
    """Fill the PSD's flattened preview from our own composite.

    `PSDImage.save` regenerates the preview by compositing every layer through
    psd-tools when the layer tree has changed. That is O(layers x page), and
    with one layer per colour it took 475 seconds on a 454-layer page. We
    already produce the identical composite in numpy for the UI.

    So: hand psd-tools the preview and clear the dirty flag. This reaches into
    `_record` and `_updated`, which is why `test_export_psd.py` checks the
    preview of a reopened file.
    """
    width, height = page_size
    rgba = flats_preview(page_size, panels, palette)
    rgb = np.full((height, width, 3), 255, dtype=np.uint8)
    painted = rgba[:, :, 3] > 0
    rgb[painted] = rgba[painted][:, :3]

    preview = Image.fromarray(rgb, mode="RGB")
    psd._record.image_data.set_data(
        [channel.tobytes() for channel in preview.split()], psd._record.header
    )
    psd._updated = False


def flats_preview(
    page_size: tuple[int, int],
    panels: list[PanelFlats],
    palette: dict[int, PaletteEntry],
) -> np.ndarray:
    """The same flats composited into one page-sized RGBA array, for the UI.

    Shares `write_psd`'s rules — palette lookup by id, nothing but flats — so
    what the artist sees on screen is what lands in the PSD.
    """
    width, height = page_size
    canvas = np.zeros((height, width, 4), dtype=np.uint8)

    for panel in panels:
        table = np.zeros((int(panel.label_map.max()) + 1, 4), dtype=np.uint8)
        for label, entry_id in panel.assignments.items():
            entry = palette.get(entry_id)
            if entry is None or not 0 < label < table.shape[0]:
                continue
            table[label] = (*entry.rgb, 255)

        rows = min(panel.label_map.shape[0], height - panel.y)
        cols = min(panel.label_map.shape[1], width - panel.x)
        if rows <= 0 or cols <= 0:
            continue
        labels = panel.label_map[:rows, :cols]

        painted = labels != UNASSIGNED
        patch = table[labels]
        window = canvas[panel.y : panel.y + rows, panel.x : panel.x + cols]

        window[painted] = patch[painted]

    return canvas
