"""§1.10 Layered export. PSD, one group per panel, one layer per colour.

P4 settled the format: `.clip` is an undocumented SQLite container, and Clip
Studio imports PSD with groups intact, so one path serves both applications
and matches what studios already pass around.

Two rules from the spec are enforced here rather than trusted:

- **No line art in any export** (rule 7). The artist keeps their own ink layer
  and drops it on top; nothing in this module ever receives the line mask.
- **Colour comes from the palette, by id** (rule 1). A layer is built from the
  set of zones sharing one `palette_entry_id`, and its RGB is looked up from
  the palette at write time. Change the entry, re-export, everything moves —
  no zone stores a colour.

Note the layer count is far smaller than the region count: many regions share
one colour, so §2.2's region counts are not layer counts. ~10 colours over
~10 panels is ~100 layers, which studio files carry comfortably.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from ..model.entities import PaletteEntry
from ..model.masks import UNASSIGNED


@dataclass
class PanelFlats:
    """One panel's zone map plus its resolved colours, ready to rasterise."""

    order: int
    # Panel origin in page pixel coordinates. The label map is in the panel's
    # own frame; this is the only place the two frames are reconciled.
    x: int
    y: int
    label_map: np.ndarray
    # zone label -> palette entry id. Zones missing from this map are unpainted
    # (nothing proposed a colour for them) and emit no pixels.
    assignments: dict[int, int] = field(default_factory=dict)


def _entry_mask(label_map: np.ndarray, labels: list[int]) -> np.ndarray:
    """Boolean mask covering every zone in `labels`."""
    lookup = np.zeros(int(label_map.max()) + 1, dtype=bool)
    for label in labels:
        if 0 < label < lookup.size:
            lookup[label] = True
    return lookup[label_map]


def write_psd(
    path: str | Path,
    page_size: tuple[int, int],
    panels: list[PanelFlats],
    palette: dict[int, PaletteEntry],
) -> Path:
    """Write the flats to `path`. Returns the path.

    `page_size` is `(width, height)` in page pixels. Panels are written in
    reading order, so the group stack matches the order the artist reads them.
    """
    from psd_tools import PSDImage

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    width, height = page_size
    # White composite: the flats are a mid-stack layer set, and a black ground
    # under them reads as an error the first time anyone opens the file.
    psd = PSDImage.new("RGB", (width, height), color=255)

    for panel in sorted(panels, key=lambda p: p.order):
        by_entry: dict[int, list[int]] = {}
        for label, entry_id in panel.assignments.items():
            by_entry.setdefault(entry_id, []).append(label)

        layers = []
        for entry_id in sorted(by_entry):
            entry = palette.get(entry_id)
            if entry is None:
                continue

            mask = _entry_mask(panel.label_map, by_entry[entry_id])
            if not mask.any():
                continue

            # Crop to the colour's own bounds. A page-sized transparent layer
            # per colour is the difference between a 4 MB file and a 400 MB one.
            rows = np.flatnonzero(mask.any(axis=1))
            cols = np.flatnonzero(mask.any(axis=0))
            top, bottom = int(rows[0]), int(rows[-1]) + 1
            left, right = int(cols[0]), int(cols[-1]) + 1
            patch = mask[top:bottom, left:right]

            rgba = np.zeros((*patch.shape, 4), dtype=np.uint8)
            rgba[patch, :3] = entry.rgb
            rgba[patch, 3] = 255

            layers.append(
                psd.create_pixel_layer(
                    Image.fromarray(rgba, mode="RGBA"),
                    name=entry.label,
                    top=panel.y + top,
                    left=panel.x + left,
                )
            )

        if layers:
            psd.create_group(layer_list=layers, name=f"Panel {panel.order + 1}")

    _set_preview(psd, page_size, panels, palette)
    psd.save(str(path))
    return path


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

        # Clip to the page: a panel whose box runs off the edge must not throw
        # a shape mismatch in the renderer the artist is looking at.
        rows = min(panel.label_map.shape[0], height - panel.y)
        cols = min(panel.label_map.shape[1], width - panel.x)
        if rows <= 0 or cols <= 0:
            continue
        labels = panel.label_map[:rows, :cols]

        painted = labels != UNASSIGNED
        patch = table[labels]
        window = canvas[panel.y : panel.y + rows, panel.x : panel.x + cols]
        # Panels can overlap where the artist's polygons do; last one wins,
        # which matches the group stacking order in the PSD.
        window[painted] = patch[painted]

    return canvas
