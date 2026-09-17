"""§1.10 Layered export. PSD, one layer per colour — grouped by panel or not.

P4 settled the format: `.clip` is an undocumented SQLite container, and Clip
Studio imports PSD with groups intact, so one path serves both applications
and matches what studios already pass around.

Two rules from the spec are enforced here rather than trusted:

- **No line art in an export the artist did not ask for** (rule 7). The flats
  never carry ink: the artist keeps their own layer and drops it on top, and
  every layer written by `_write_by_panel` and `_write_by_colour` is colour.
  The one exception is `support_grey`, asked for by name at the press — see
  `_write_support` — because the thing a printer needs cannot be built without
  the ink, and building it by hand is what the colourist was doing instead.
- **Colour comes from the palette, by id** (rule 1). A layer is built from the
  set of zones sharing one `palette_entry_id`, and its RGB is looked up from
  the palette at write time. Change the entry, re-export, everything moves —
  no zone stores a colour.

`granularity` is the artist's choice of stack, and it is the second rule made
manipulable in Photoshop:

- `"colour"` — one layer per palette entry, over the whole page, no groups. The
  same colour in five panels is one layer, so "change the hair everywhere" is
  one selection rather than five.
- `"panel"` — one group per panel, one layer per colour inside it. For the
  colourist who works panel by panel.

Note the layer count is far smaller than the region count: many regions share
one colour, so §2.2's region counts are not layer counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from ..model.entities import PaletteEntry
from ..model.masks import UNASSIGNED

GRANULARITIES = ("colour", "panel")

# What the ink is tinted to for the supporting layer: 20 % grey, the value
# print colourists lay under a line to keep it from breaking up on paper.
SUPPORT_GREY = (204, 204, 204)

# Past this many layers the artist is exporting the model's guesses rather than
# their own palette — one private entry per segment is what makes the count
# run — and the fix is one button away (§1.7, snap). Warned at the press,
# never enforced: a studio that wants two hundred layers gets them.
EXPORT_LAYER_WARNING = 20


@dataclass
class PanelFlats:
    """One panel's zone map plus its resolved colours, ready to rasterise."""

    order: int

    x: int
    y: int
    label_map: np.ndarray

    assignments: dict[int, int] = field(default_factory=dict)


def _entry_mask(label_map: np.ndarray, labels: list[int]) -> np.ndarray:
    """Boolean mask covering every zone in `labels`."""
    lookup = np.zeros(int(label_map.max()) + 1, dtype=bool)
    for label in labels:
        if 0 < label < lookup.size:
            lookup[label] = True
    return lookup[label_map]


def _by_entry(panel: PanelFlats) -> dict[int, list[int]]:
    """The panel's labels, grouped by the palette entry they were given."""
    grouped: dict[int, list[int]] = {}
    for label, entry_id in panel.assignments.items():
        grouped.setdefault(entry_id, []).append(label)
    return grouped


def layer_count(
    panels: list[PanelFlats],
    palette: dict[int, PaletteEntry],
    granularity: str = "colour",
) -> int:
    """How many layers `write_psd` would write, without writing them.

    Counted on ids and never on rasters: the sidebar asks for this on every
    state poll, and the answer must not cost a page-sized array per entry.
    That it agrees with what lands in the file is what `test_export_psd`
    checks — an export warning quoting the wrong number is worse than none.
    """
    if granularity == "colour":
        return len(
            {
                entry_id
                for panel in panels
                for entry_id in panel.assignments.values()
                if entry_id in palette
            }
        )
    return sum(
        len({e for e in panel.assignments.values() if e in palette})
        for panel in panels
    )


def write_psd(
    path: str | Path,
    page_size: tuple[int, int],
    panels: list[PanelFlats],
    palette: dict[int, PaletteEntry],
    granularity: str = "colour",
    line_mask: np.ndarray | None = None,
    support_grey: bool = False,
) -> Path:
    """Write the flats to `path`. Returns the path.

    `page_size` is `(width, height)` in page pixels. Under `"panel"` the panels
    are written in reading order, so the group stack matches the order the
    artist reads them; under `"colour"` there is nothing to order but the
    palette itself, and entries go out by id.

    `support_grey` adds the two ink layers a printer wants on top of the
    stack — see `_write_support`. It is the only thing that puts line art in
    an export, it is off unless asked for, and it needs `line_mask`.
    """
    from psd_tools import PSDImage

    if granularity not in GRANULARITIES:
        raise ValueError(
            f"unknown granularity {granularity!r}, expected one of {GRANULARITIES}"
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    width, height = page_size

    psd = PSDImage.new("RGB", (width, height), color=255)

    if granularity == "colour":
        _write_by_colour(psd, page_size, panels, palette)
    else:
        _write_by_panel(psd, panels, palette)

    if support_grey:
        if line_mask is None:
            raise ValueError("support_grey needs the line mask")
        _write_support(psd, line_mask)

    _set_preview(psd, page_size, panels, palette)
    psd.save(str(path))
    return path


def _layer(psd, mask: np.ndarray, entry: PaletteEntry, top: int = 0, left: int = 0):
    """One flat as a PSD pixel layer, cropped to what it actually covers."""
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    patch = mask[y0:y1, x0:x1]

    rgba = np.zeros((*patch.shape, 4), dtype=np.uint8)
    rgba[patch, :3] = entry.rgb
    rgba[patch, 3] = 255

    # The document is RGB, so psd-tools carries the layer's transparency as a
    # layer mask rather than a fourth channel. Photoshop and CSP honour it;
    # `layer.topil()` does not, which is why the tests read `composite()`.
    return psd.create_pixel_layer(
        Image.fromarray(rgba, mode="RGBA"),
        name=entry.label,
        top=top + y0,
        left=left + x0,
    )


def _write_support(psd, line_mask: np.ndarray) -> None:
    """The supporting grey, on top of the flats: the ink, twice.

    What print colourists build by hand. **Lines** is the artist's ink set to
    Multiply, so it darkens the flats instead of covering them. **Support
    grey** underneath is the same ink at 20 % grey with its transparency
    locked, which turns it into a stencil of the drawing: paint into it and
    the paint can only land on the line, which is how a line is kept from
    breaking up at print size.

    Written last, so both sit above every colour group.
    """
    from psd_tools.constants import BlendMode, ProtectedFlags, Tag
    from psd_tools.psd.tagged_blocks import ProtectedSetting

    ink = np.asarray(line_mask).astype(bool)
    if not ink.any():
        return

    grey = _ink_layer(psd, ink, SUPPORT_GREY, "Support grey")
    # The tagged block directly, not `Layer.lock`: that helper reads the block
    # back before it has written one, so the flag never reaches the file
    # (psd-tools 1.18). Checked by the test, which reopens what was saved.
    grey.tagged_blocks.set_data(
        Tag.PROTECTED_SETTING, ProtectedSetting(int(ProtectedFlags.TRANSPARENCY))
    )
    _ink_layer(psd, ink, (0, 0, 0), "Lines").blend_mode = BlendMode.MULTIPLY


def _ink_layer(psd, ink: np.ndarray, colour: tuple[int, int, int], name: str):
    """One layer of ink, one flat colour, cropped to the drawing."""
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


def _write_by_panel(psd, panels: list[PanelFlats], palette) -> None:
    """One group per panel, one layer per colour inside it."""
    for panel in sorted(panels, key=lambda p: p.order):
        by_entry = _by_entry(panel)

        layers = []
        for entry_id in sorted(by_entry):
            entry = palette.get(entry_id)
            if entry is None:
                continue

            mask = _entry_mask(panel.label_map, by_entry[entry_id])
            if not mask.any():
                continue

            layers.append(_layer(psd, mask, entry, top=panel.y, left=panel.x))

        if layers:
            psd.create_group(layer_list=layers, name=f"Panel {panel.order + 1}")


def _write_by_colour(psd, page_size, panels: list[PanelFlats], palette) -> None:
    """One layer per palette entry, over the whole page, no groups.

    A zone knows its colour by id and nothing else (rule 1), so a colour that
    appears in five panels is one thing and not five. This is that fact given
    a shape the artist can select: one layer, the whole page, every occurrence.
    """
    width, height = page_size

    spread: dict[int, list[tuple[PanelFlats, list[int]]]] = {}
    for panel in sorted(panels, key=lambda p: p.order):
        for entry_id, labels in _by_entry(panel).items():
            spread.setdefault(entry_id, []).append((panel, labels))

    for entry_id in sorted(spread):
        entry = palette.get(entry_id)
        if entry is None:
            continue

        mask = np.zeros((height, width), dtype=bool)
        for panel, labels in spread[entry_id]:
            patch = _entry_mask(panel.label_map, labels)
            rows = min(patch.shape[0], height - panel.y)
            cols = min(patch.shape[1], width - panel.x)
            if rows <= 0 or cols <= 0:
                continue
            window = mask[panel.y : panel.y + rows, panel.x : panel.x + cols]
            np.logical_or(window, patch[:rows, :cols], out=window)

        if not mask.any():
            continue
        _layer(psd, mask, entry)


def _set_preview(psd, page_size, panels, palette) -> None:
    """Fill the PSD's flattened preview from our own composite.

    `PSDImage.save` regenerates the preview by compositing every layer through
    psd-tools when the layer tree has changed. That is O(layers x page) and it
    dominates everything: measured on a 2048x2732 page with 454 layers, the
    save took 475 seconds while building the layers took under two. We already
    produce the identical composite in numpy for the UI, in milliseconds.

    So: hand psd-tools the preview and clear the dirty flag. This reaches into
    `_record` and `_updated`, which is why `test_export_psd.py` checks the
    preview of a reopened file — if a psd-tools upgrade moves either, the test
    fails loudly rather than the export silently going back to eight minutes.

    The preview does not depend on `granularity`: both stacks composite to the
    same page, which is exactly what makes the choice between them safe.
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
    what the artist sees on screen is what lands in the PSD, rather than a
    second renderer that can drift from it.
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
