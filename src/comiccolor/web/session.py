"""One page, five buttons, in memory.

This is the barebone version of the app (`SPEC.md`): no projects, no volumes,
no page list, no reopening. One page is in flight at a time, its state lives
in this object, and uploading another one replaces it. The SQLite store in
`comiccolor.model` is the persistent version of the same shape and is
deliberately not used here — persistence is not what the barebone app is for,
and half-wiring it would cost more than adding it later.

What *is* carried over from the store's design, because it is non-negotiable
(rule 1): a zone holds a `palette_entry_id` and there is nowhere in this module
for a zone to hold an RGB value. Colour is resolved through the palette at
render and export time, both of which go through `export.psd`.

Rule 2 — nothing runs by itself. Every method here is one button. Rule 4 —
re-running a step replaces its output, so each step clears what depended on it.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

from ..colour.extract import EmptyImageError, extract_palette
from ..colour.proposer import (
    ColourProposer,
    DistinctColourProposer,
    PanelRequest,
    ReferenceImage,
)
from ..colour.references import PALETTE_KIND, Reference, ReferenceStore
from ..colour.segments import Segment, build_segments
from ..colour.snap import SNAP_MAX_DELTA, assign_zones, nearest_entry
from ..export.psd import PanelFlats, flats_preview, write_psd
from ..extract.base import LineExtractor
from ..extract.manga_line import MangaLineExtractor
from ..model.entities import PaletteEntry
from ..model.masks import UNASSIGNED, region_stats
from ..segmentation.bubbles import BubbleDetector, detect_bubbles
from ..segmentation.panels import segment_panels
from ..segmentation.preprocess import binarise_lines, load_line_art
from ..segmentation.protected import rasterize_protected_for_panel
from ..segmentation.segmenter import LineFillerSegmenter
from ..segmentation.trappedball import expand_under_lines, inked_zones


@dataclass
class PanelState:
    order: int
    x: int
    y: int
    width: int
    height: int
    polygon: list[tuple[int, int]]
    # None until Segment zones has run. Panel-local frame, not page frame.
    label_map: np.ndarray | None = None
    # zone label -> palette entry id. Empty until Generate flats has run.
    assignments: dict[int, int] = field(default_factory=dict)
    flagged: set[int] = field(default_factory=set)

    @property
    def zone_count(self) -> int:
        if self.label_map is None:
            return 0
        present = np.unique(self.label_map)
        return int((present != UNASSIGNED).sum())


# What `CobraProposer.resolution` defaults to, on the long side. A reference
# panel is measured against this because the real target is per-query and
# unknown at upload time (`_split_into_panels`).
_NOMINAL_TARGET = 1024
# How far a reference may be blown up to reach that frame before it is more
# smear than drawing. 2.0 is where `reports/10-retrieval` measured the fall,
# on one page — treat it as calibrated, not derived.
_MAX_UPSCALE = 2.0


def _overshoot(points: np.ndarray, margin: int) -> np.ndarray:
    """Extend a stroke past both ends, along the direction it was going."""

    def past(here, before):
        step = here - before
        length = float(np.hypot(*step))
        if length < 1:
            return here
        return (here + step / length * margin).astype(np.int32)

    return np.vstack(
        [past(points[0], points[1]), points, past(points[-1], points[-2])]
    )


def _rgb(value) -> tuple[int, int, int]:
    """Three channels, 0-255, from whatever the wire or the store sent."""
    channels = tuple(int(part) for part in value)
    if len(channels) != 3 or any(not 0 <= part <= 255 for part in channels):
        raise StepError(f"{value!r} is not an r,g,b colour.")
    return channels


class StepError(RuntimeError):
    """A button was pressed before the step it depends on had run."""


def _best_device() -> str:
    """CUDA when there is a card, CPU otherwise.

    The extractor is a small conv net and runs on either; the difference is
    minutes versus seconds on a full-resolution page. Nothing else in the
    barebone app needs a GPU, so this must degrade rather than refuse.
    """
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class Session:
    """The whole application state. One instance per process."""

    def __init__(
        self,
        workdir: str | Path,
        proposer: ColourProposer | None = None,
        extractor: LineExtractor | None = None,
    ):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.proposer: ColourProposer = proposer or DistinctColourProposer()
        self.extractor: LineExtractor = extractor or MangaLineExtractor(
            device=_best_device()
        )
        # Serialises the buttons. Segmentation takes seconds and the artist
        # will double-click; two passes mutating the same panel list is the
        # one race worth spending a lock on.
        self.lock = threading.RLock()
        # Loaded on the first press of Detect bubbles rather than here: it is
        # 161 MB off disk, and a page with no balloons never needs it.
        self.bubble_detector: BubbleDetector | None = None
        # Built before `reset`, and deliberately not touched by it: the
        # reference pool belongs to the book, not to the page in flight.
        self.reference_store = ReferenceStore(self.workdir / "references")
        # reference id -> the colours found in it, cached; and
        # (reference id, rgb) -> the palette entry the artist made from it.
        self._candidates: dict[int, list[tuple[int, int, int]]] = {}
        self._taken: dict[tuple[int, tuple[int, int, int]], int] = {}
        self._load_palette()
        self.reset()

    # -- state -----------------------------------------------------------

    def reset(self) -> None:
        self.source: Path | None = None
        self.original_name: str = ""
        self.width = 0
        self.height = 0
        self.grey: np.ndarray | None = None
        self.line_mask: np.ndarray | None = None
        # Extractor output, computed lazily by `structural_lines`. The
        # greyscale is kept as well as the mask because the two consumers want
        # different things from it: trapped-ball wants a boolean ink map, the
        # proposer wants the soft line image the model was trained on.
        self._structural_lines: np.ndarray | None = None
        self._structural: np.ndarray | None = None
        self.panels: list[PanelState] = []
        self.protected: list[list[tuple[int, int]]] = []
        # The palette itself is not reset: it belongs to the book, like the
        # references, and outlives both the page and the process. What is
        # page-scoped is the private entry `generate_flats` gives every zone
        # that no colour was chosen for — those go with the page they describe.
        self._created_palette: list[PaletteEntry] = []
        # Tracked apart from `self.protected` because a page with no bubbles
        # on it is a legitimate outcome of pressing the button, not a step
        # that never ran.
        # One per zone, built by `generate_flats`. The artist's unit of work
        # from here on: everything after flats is per-segment.
        self.segments: list[Segment] = []
        # (panel, label) -> the private entry `generate_flats` gave that
        # segment, so `unsnap_segment` can put back what the proposer said.
        self._auto_entry: dict[tuple[int, int], int] = {}
        self._bubbles_done = False
        self._zones_done = False
        self._flats_done = False

    def _require_page(self) -> None:
        if self.line_mask is None:
            raise StepError("Upload a page first.")

    # -- 1. upload -------------------------------------------------------

    def load_page(self, path: str | Path, original_name: str = "") -> None:
        """Replaces everything. A new page is a new session."""
        with self.lock:
            line_mask, grey = load_line_art(path)
            self.reset()
            self.source = Path(path)
            self.original_name = original_name or Path(path).name
            self.line_mask = line_mask
            self.grey = grey
            self.height, self.width = line_mask.shape

    # -- 2. detect panels ------------------------------------------------

    def detect_panels(self) -> list[PanelState]:
        with self.lock:
            self._require_page()
            found = segment_panels(self.line_mask)
            self.panels = [
                PanelState(
                    order=order,
                    x=panel.x,
                    y=panel.y,
                    width=panel.width,
                    height=panel.height,
                    polygon=panel.polygon,
                )
                for order, panel in enumerate(found)
            ]
            self._invalidate_from_panels()
            return self.panels

    # -- 3. detect bubbles -----------------------------------------------

    def detect_bubbles(self) -> list[list[tuple[int, int]]]:
        with self.lock:
            self._require_page()
            # The steps run in one order and only one order. Bubbles do not
            # need the panels to be *found* — the detector reads the whole
            # page — but they need them to be *settled*: a balloon the artist
            # traces belongs to a page whose panels are already the ones they
            # meant, and re-running panel detection after tracing balloons is
            # how an artist loses work they cannot get back.
            if not self.panels:
                raise StepError("Detect panels first — the steps run in order.")
            if self.bubble_detector is None:
                self.bubble_detector = BubbleDetector()
            polygons = detect_bubbles(
                self.grey, self.line_mask, detector=self.bubble_detector
            )
            self.protected = [p for p in polygons if len(p) >= 3]
            # Protection feeds segmentation, so zones computed before it are
            # stale (rule 4).
            self._invalidate_from_panels()
            self._bubbles_done = True
            return self.protected

    # -- 2b/3b. the artist's corrections ---------------------------------
    #
    # Detection proposes geometry; these accept the artist's version of it.
    # Every one of them replaces a whole polygon rather than describing an
    # edit: dragging a corner, inserting one on an edge and deleting one are
    # the same call, which keeps the interaction on the client where the
    # pointer is and leaves the server holding only what is true of the
    # result.

    def _clean_polygon(self, polygon, noun: str) -> list[tuple[int, int]]:
        """A polygon the rest of the pipeline can rasterise, or an error.

        Clamped to the page because a corner dragged past the edge is a
        corner the artist meant to put at the edge, not a mistake to refuse.
        """
        cleaned: list[tuple[int, int]] = []
        for point in polygon:
            x = max(0, min(self.width - 1, int(point[0])))
            y = max(0, min(self.height - 1, int(point[1])))
            if not cleaned or cleaned[-1] != (x, y):
                cleaned.append((x, y))
        if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
            cleaned.pop()
        if len(cleaned) < 3:
            raise StepError(f"A {noun} needs at least three corners.")
        return cleaned

    def _require_panel_stage(self) -> None:
        self._require_page()
        if not self.panels:
            raise StepError("Detect panels first — there is nothing to correct yet.")
        if self._zones_done:
            raise StepError(
                "The zones are already cut from these panels. "
                "Press Detect panels to reopen the geometry."
            )

    def _require_bubble_stage(self) -> None:
        self._require_page()
        if not self._bubbles_done:
            raise StepError("Detect bubbles first — there is nothing to correct yet.")
        if self._zones_done:
            raise StepError(
                "The zones are already cut around these bubbles. "
                "Press Detect bubbles to reopen the geometry."
            )

    def _reorder_panels(self) -> None:
        """Renumber panels into reading order after the artist changed them.

        Through `panels._reading_order`, not a sort of its own: the number
        drawn in a panel's corner is the order the export groups run in, and
        a hand-drawn panel that reads second must not export fifth because it
        happened to be added last.
        """
        from ..segmentation.panels import Panel, PanelBox, PanelParams, _reading_order

        carriers = [
            Panel(
                polygon=panel.polygon,
                box=PanelBox(panel.x, panel.y, panel.width, panel.height),
            )
            for panel in self.panels
        ]
        by_carrier = {id(carrier): panel for carrier, panel in zip(carriers, self.panels)}
        ordered = _reading_order(carriers, PanelParams().reading)
        self.panels = [by_carrier[id(carrier)] for carrier in ordered]
        for order, panel in enumerate(self.panels):
            panel.order = order

    def _panel_for(self, order: int) -> PanelState:
        for panel in self.panels:
            if panel.order == order:
                return panel
        raise StepError(f"No panel {order + 1}.")

    def set_panel_polygon(self, order: int, polygon) -> PanelState:
        with self.lock:
            self._require_panel_stage()
            panel = self._panel_for(order)
            panel.polygon = self._clean_polygon(polygon, "panel")
            self._fit_box(panel)
            self._reorder_panels()
            self._invalidate_from_panels()
            return panel

    def add_panel(self, polygon) -> PanelState:
        with self.lock:
            self._require_panel_stage()
            panel = PanelState(
                order=len(self.panels),
                x=0,
                y=0,
                width=0,
                height=0,
                polygon=self._clean_polygon(polygon, "panel"),
            )
            self._fit_box(panel)
            self.panels.append(panel)
            self._reorder_panels()
            self._invalidate_from_panels()
            return panel

    def delete_panel(self, order: int) -> None:
        with self.lock:
            self._require_panel_stage()
            panel = self._panel_for(order)
            if len(self.panels) == 1:
                raise StepError(
                    "That is the last panel. A page with no panels has nothing "
                    "to segment — draw its replacement first."
                )
            self.panels.remove(panel)
            self._reorder_panels()
            self._invalidate_from_panels()

    @staticmethod
    def _fit_box(panel: PanelState) -> None:
        """The crop box follows the outline. `panels.Panel` keeps both for the
        same reason: the polygon says which pixels are the panel's, the box
        says where to cut the page."""
        xs = [x for x, _ in panel.polygon]
        ys = [y for _, y in panel.polygon]
        panel.x, panel.y = min(xs), min(ys)
        panel.width = max(xs) - panel.x + 1
        panel.height = max(ys) - panel.y + 1

    def set_bubble(self, index: int, polygon) -> list[tuple[int, int]]:
        with self.lock:
            self._require_bubble_stage()
            self._require_bubble_index(index)
            self.protected[index] = self._clean_polygon(polygon, "bubble")
            self._invalidate_from_panels()
            return self.protected[index]

    def add_bubble(self, polygon) -> int:
        with self.lock:
            self._require_bubble_stage()
            self.protected.append(self._clean_polygon(polygon, "bubble"))
            self._invalidate_from_panels()
            return len(self.protected) - 1

    def delete_bubble(self, index: int) -> None:
        with self.lock:
            self._require_bubble_stage()
            self._require_bubble_index(index)
            del self.protected[index]
            self._invalidate_from_panels()

    def _require_bubble_index(self, index: int) -> None:
        if not 0 <= index < len(self.protected):
            raise StepError(f"No bubble {index}.")

    # -- 4. segment zones ------------------------------------------------

    def segment_zones(self) -> list[PanelState]:
        with self.lock:
            self._require_page()
            if not self.panels:
                raise StepError("Detect panels first — zones are segmented per panel.")

            structural = self.structural_mask()
            segmenter = LineFillerSegmenter()
            for panel in self.panels:
                window = (
                    slice(panel.y, panel.y + panel.height),
                    slice(panel.x, panel.x + panel.width),
                )
                blocked = self._blocked_for(panel)
                labels = segmenter.segment(structural[window], protected=blocked)
                raw = self.line_mask[window]
                # Which zones are the artist's own spot black, measured here
                # and punched below. Measured on the labels the segmenter
                # returned, because after expansion every sliver that grew
                # under a stroke looks black too.
                doomed = inked_zones(labels, raw)
                # Flats must meet underneath the ink, or every line leaves a
                # white seam in the export (§10, anti-aliased line art). This
                # one takes the *raw* ink, not the structural lines: the layer
                # the artist drops on top is their real ink, so that is what
                # the flats have to reach under.
                expanded = expand_under_lines(labels, raw, protected=blocked)
                # Now the hole. Left in place through expansion the spot black
                # was a wall the neighbours stopped against; taken out before
                # it, they would have flooded it and met in its middle, which
                # draws zones straight across the stroke separating them.
                expanded[doomed[expanded]] = UNASSIGNED
                panel.label_map = expanded
                panel.assignments = {}
                panel.flagged = set()

            self._zones_done = True
            self._flats_done = False
            return self.panels

    # -- 4b. the artist's corrections to the zones -----------------------
    #
    # Trapped-ball cuts a panel into zones from the ink it can see, and the
    # ink is not always closed. So it leaks a garment into the background
    # through a gap, and it splits what the eye reads as one thing — a pair of
    # trousers, a glass, a pair of shoes — into forty scraps that would each
    # need colouring by hand.
    #
    # Merge and cut are the two corrections that follow, and they are the last
    # thing the artist does before the colours arrive. **They are permanent.**
    # There is no unmerge and no history: keeping one would mean carrying the
    # segmenter's original map beside the artist's, and every later stage
    # would have to say which of the two it meant. The stage boundary is the
    # protection instead — this is step 4's work, it happens before a single
    # colour is proposed, and pressing Segment zones again starts the page
    # over.

    def _require_zone_stage(self) -> None:
        self._require_page()
        if not self._zones_done:
            raise StepError("Segment zones first — there are no zones to correct yet.")
        if self._flats_done:
            raise StepError(
                "The flats are coloured from these zones. Press Segment zones to "
                "cut the page again — every merge and cut goes with it."
            )

    def zone_at(self, x: int, y: int) -> tuple[int, int] | None:
        """The (panel, label) under a page-space point, or None.

        Read off the label map, like `segment_at`, and for the same reason:
        bounds overlap for interlocking zones and a press has to resolve to
        the zone the artist actually pointed at. Unlike `segment_at` this one
        works before `generate_flats` has invented a single segment.
        """
        with self.lock:
            for panel in self.panels:
                if panel.label_map is None:
                    continue
                local_x, local_y = x - panel.x, y - panel.y
                if not (0 <= local_x < panel.width and 0 <= local_y < panel.height):
                    continue
                label = int(panel.label_map[local_y, local_x])
                if label == UNASSIGNED:
                    continue
                return panel.order, label
            return None

    def zones_along(self, points) -> list[tuple[int, int]]:
        """Every zone a stroke passes over, in the order it met them.

        The sweep. A pair of trousers is forty scraps and forty presses is not
        an interface, so holding the button and moving picks up everything
        under the pointer — but only what is *under* it, which is why two
        zones on opposite sides of the page still take two presses and drag
        nothing in between.

        Sampled every pixel between the points the browser sent: at a page
        zoomed to fit, one screen pixel is three page pixels, and a small zone
        between two samples would be skipped.
        """
        with self.lock:
            found: list[tuple[int, int]] = []
            seen: set[tuple[int, int]] = set()
            for (x0, y0), (x1, y1) in zip(points, points[1:] or points):
                steps = max(abs(int(x1) - int(x0)), abs(int(y1) - int(y0)), 1)
                for step in range(steps + 1):
                    x = int(x0 + (int(x1) - int(x0)) * step / steps)
                    y = int(y0 + (int(y1) - int(y0)) * step / steps)
                    zone = self.zone_at(x, y)
                    if zone is not None and zone not in seen:
                        seen.add(zone)
                        found.append(zone)
            return found

    def zone_bounds(self, panel_order: int) -> dict[int, tuple[int, int, int, int]]:
        """Page-space bounds of every zone in a panel, in one pass.

        The browser needs a box per zone to place the highlight it draws, and
        a sweep hands it forty zones at a time — one vectorised pass beats
        forty mask scans.
        """
        with self.lock:
            panel = self._panel_for(panel_order)
            if panel.label_map is None:
                return {}
            return {
                int(label): (
                    int(x) + panel.x,
                    int(y) + panel.y,
                    int(x) + int(width) - 1 + panel.x,
                    int(y) + int(height) - 1 + panel.y,
                )
                for label, (_, (x, y, width, height)) in region_stats(
                    panel.label_map
                ).items()
            }

    def merge_zones(self, panel_order: int, labels) -> dict:
        """Make several zones one zone. One address, one colour, one click.

        The largest keeps its label, so the zone's anchor stays in the body of
        the trousers rather than in a 300px scrap.

        Zones need not touch: the panes of a glass and a shirt split by an arm
        are one thing to colour and one thing here. A zone is a set of pixels,
        not a blob. What they must share is a panel — labels are panel-local,
        and the same shirt in the next panel is the palette's job.
        """
        with self.lock:
            self._require_zone_stage()
            panel = self._panel_for(panel_order)
            if panel.label_map is None:
                raise StepError(f"Panel {panel_order + 1} has no zones.")

            wanted = {int(label) for label in labels}
            present = {
                label: int(area)
                for label, area in zip(*np.unique(panel.label_map, return_counts=True))
                if int(label) in wanted and int(label) != UNASSIGNED
            }
            if len(present) < 2:
                raise StepError("Select at least two zones of one panel to merge.")

            survivor = max(present, key=lambda label: present[label])
            others = [label for label in present if label != survivor]
            panel.label_map[np.isin(panel.label_map, others)] = survivor
            return {
                "panel": panel_order,
                "label": int(survivor),
                "merged": len(present),
                "area": int(sum(present.values())),
            }

    def cut_zone(self, panel_order: int, label: int, stroke, width: int = 3) -> dict:
        """Split one zone along a stroke — the line the ink was missing.

        The cause of a leaked zone is an open contour, so the correction is
        the contour: the artist draws across the gap and the zone parts along
        it. Nothing is thrown away — the stroke's own pixels go to whichever
        piece they are nearest, so the page keeps every pixel it had.
        """
        with self.lock:
            self._require_zone_stage()
            panel = self._panel_for(panel_order)
            if panel.label_map is None:
                raise StepError(f"Panel {panel_order + 1} has no zones.")

            mask = panel.label_map == int(label)
            if not mask.any():
                raise StepError(f"No zone {label} in panel {panel_order + 1}.")

            points = np.array(
                [[int(x) - panel.x, int(y) - panel.y] for x, y in stroke], np.int32
            )
            if len(points) < 2:
                raise StepError("Draw the cut across the zone, from one side to the other.")

            # Both ends run on past where the hand stopped. A stroke has to
            # leave the zone on both sides to separate it, and stopping a few
            # pixels short is the commonest way a cut fails — while the
            # overshoot itself can do no harm, since the wall is only ever
            # applied inside this zone's own mask.
            points = _overshoot(points, max(mask.shape) // 20 + 10)

            wall = np.zeros(mask.shape, np.uint8)
            cv2.polylines(wall, [points.reshape(-1, 1, 2)], False, 1, max(1, width))
            remaining = mask & (wall == 0)

            count, pieces = cv2.connectedComponents(
                remaining.astype(np.uint8), connectivity=8
            )
            if count - 1 < 2:
                raise StepError(
                    "That stroke does not separate the zone — draw it right across, "
                    "from one edge of the zone to the other."
                )

            next_label = int(panel.label_map.max()) + 1
            made = [int(label)]
            for piece in range(2, count):
                panel.label_map[pieces == piece] = next_label
                made.append(next_label)
                next_label += 1

            # The stroke's own pixels: give each to the nearest piece, so a cut
            # never leaves a seam of unassigned pixels for the flats to fringe
            # around.
            seam = mask & (wall != 0)
            if seam.any():
                _, (rows, cols) = ndimage.distance_transform_edt(
                    ~remaining, return_indices=True
                )
                panel.label_map[seam] = panel.label_map[rows[seam], cols[seam]]

            return {"panel": panel_order, "labels": made, "pieces": len(made)}

    def zone_mask_rgba(self, panel_order: int, label: int) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """One zone as a tinted overlay, cropped to its own bounds.

        Cropped because selecting forty zones must not mean forty full-page
        PNGs: each of these is a few kilobytes and the browser composites them
        at the bounds this returns with it.
        """
        with self.lock:
            panel = self._panel_for(panel_order)
            if panel.label_map is None:
                raise StepError(f"Panel {panel_order + 1} has no zones.")
            mask = panel.label_map == int(label)
            rows, cols = np.nonzero(mask)
            if not len(rows):
                raise StepError(f"No zone {label} in panel {panel_order + 1}.")

            top, bottom = int(rows.min()), int(rows.max())
            left, right = int(cols.min()), int(cols.max())
            window = mask[top : bottom + 1, left : right + 1]
            rgba = np.zeros((*window.shape, 4), dtype=np.uint8)
            # A wash plus a hard edge. The wash alone disappears against a
            # zone map that is already saturated colour, and "which zones are
            # selected" is the one question this image exists to answer.
            rgba[window] = (255, 255, 255, 90)
            inside = cv2.erode(
                window.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2
            ).astype(bool)
            rgba[window & ~inside] = (255, 255, 255, 255)
            return rgba, (
                left + panel.x,
                top + panel.y,
                right + panel.x,
                bottom + panel.y,
            )

    def structural_mask(self) -> np.ndarray:
        """The line mask zones are segmented from. §7's swappable extractor.

        Not the same array as `self.line_mask`, and the difference is the
        whole point. Raw ink hands trapped-ball every stroke it can see, so a
        thick brush line becomes a zone bounded by its own two edges and a
        solid black fill becomes a zone in its own right — the page ends up
        segmented into ink as well as into art. MangaLineExtraction returns
        *structural* lines: strokes collapse toward their centre and spot
        blacks come back as their contours, which is why §2.2 measured
        teddy's ink fraction dropping 0.173 → 0.058 with the structure it
        matters for preserved.

        Panel and bubble detection deliberately keep the raw mask.
        `segment_panels` needs solid blacks to stay solid, or the gutter
        network leaks straight through them; `detect_bubbles` shows the model
        the page as the artist drew it, and traces the balloon outline off the
        raw ink, which is the line the artist will drop back on top.

        Computed once per page and cached: it is seconds on a GPU, minutes on
        a CPU, and it does not change until a new page is loaded.
        """
        if self._structural is None:
            self._structural = binarise_lines(self.structural_lines())
        return self._structural

    def structural_lines(self) -> np.ndarray:
        """The extractor's own output, greyscale, before any threshold.

        `structural_mask` binarises this for trapped-ball; the proposer wants
        it as it comes. Cobra's `app.py` conditions its DiT on the soft output
        of its own line model, never on the artist's file, so handing it the
        raw scan puts heavy brush, spot black and hatching into a network that
        saw none of them in training. §7 already calls the soft-to-binary
        threshold a parameter of the pipeline rather than a detail — this is
        the consumer for which the threshold is simply wrong.

        Shares the cache with `structural_mask`: one extractor pass per page.
        """
        self._require_page()
        if self._structural_lines is None:
            self._structural_lines = self.extractor.extract(self.grey).lines
        return self._structural_lines

    def reference_images(self) -> list[ReferenceImage]:
        """The book's references, with the kind the artist gave each one.

        `kind` travels with the pixels because the proposer decides how to fit
        a reference to a panel, and the right answer differs between one
        composed page and a montage of separate character drawings.
        """
        return [
            ReferenceImage(
                pixels=self.reference_store.image(reference.id),
                kind=reference.kind,
                label=reference.label,
            )
            for reference in self.reference_store
            if reference.kind != PALETTE_KIND
        ]

    def _line_art_for(self, panel: PanelState) -> np.ndarray:
        """The panel crop, masked to the panel's own polygon.

        The crop is a bounding box, and a bounding box is only the panel for a
        rectangle. For an L-shaped or a round panel it also contains whatever
        the neighbouring panel put in the corner, and the proposer would be
        reasoning about — and retrieving references for — a scene that is
        partly not this panel. Everything outside the polygon becomes paper
        white here, which for a rectangular panel is a no-op.

        What is *painted* outside the polygon has never mattered: zones there
        come back UNASSIGNED from `_blocked_for` and are never coloured. What
        the model sees is the part that did.

        The crop comes from `structural_lines`, not from `self.grey`. The
        proposer and trapped-ball then read the same drawing, which is what
        makes a zone boundary and the colour proposed inside it agree.
        """
        lines = self.structural_lines()
        crop = lines[
            panel.y : panel.y + panel.height, panel.x : panel.x + panel.width
        ]
        inside = rasterize_protected_for_panel(
            [panel.polygon], panel.x, panel.y, panel.width, panel.height
        )
        masked = np.where(inside, crop, 255).astype(np.uint8)
        return np.repeat(masked[:, :, None], 3, axis=2)

    def _blocked_for(self, panel: PanelState) -> np.ndarray:
        """Protected areas plus everything outside the panel polygon.

        Both come back unlabelled, which is the whole of what "protected"
        means: never coloured.
        """
        protected = rasterize_protected_for_panel(
            self.protected, panel.x, panel.y, panel.width, panel.height
        )
        inside = rasterize_protected_for_panel(
            [panel.polygon], panel.x, panel.y, panel.width, panel.height
        )
        return protected | ~inside

    # -- palette / references --------------------------------------------
    #
    # A reference and the palette are two different things, and conflating
    # them was costing the artist both. A reference is an image: it is what
    # Cobra is shown, and it is where candidate colours are *found*. The
    # palette is the artist's list: it is what zones snap to, and nothing
    # reaches it without being chosen.
    #
    # The palette used to be re-derived from the references on every change,
    # which made two things impossible at once — keeping a colour whose
    # reference had been deleted, and editing a colour at all, since the next
    # rebuild would put it back. So the palette is now held, not derived, and
    # ids are handed out once and never renumbered: a zone stores an id, and
    # an id that means a different colour tomorrow is worse than no id at all.

    def add_reference(
        self, path: str | Path, original_name: str = "", kind: str = "sheet"
    ) -> list[Reference]:
        """Store a drawing and read its colours out. Neither joins the palette.

        `kind` is `page`, `panel` or `sheet`. It is recorded because the
        proposal-time fitting step needs it and only the artist knows it.

        A character sheet is a drawing that happens to contain colours, so
        which of them the book actually uses is a judgement — the extraction
        offers, the artist chooses. That is the whole difference from
        `add_palette`, where choosing has already happened.

        A finished *page* is stored whole **and** as the panels it is made of:
        see `_split_into_panels`.
        """
        if kind == PALETTE_KIND:
            raise StepError("A palette image goes in through Add palette.")
        with self.lock:
            label = original_name or Path(path).name
            stored = [self.reference_store.add(path, label=label, kind=kind)]
            if kind == "page":
                stored += self._split_into_panels(path, label)
            return stored

    def _split_into_panels(self, path: str | Path, label: str) -> list[Reference]:
        """The panels of a finished page, stored *alongside* the page itself.

        The page is kept whether or not this returns anything. A panel dropped
        below the guard is not just unused, its colours leave the pool
        entirely — four of `laurine_colo`'s six go — and those colours are
        still in the page. Scored in `reports/10-retrieval`, page-plus-panels
        matches the best arm exactly, so keeping both costs nothing.

        Cobra retrieves patches: it cuts the reference into tiles, ranks them
        against the panel being coloured, and reads the colour out of whichever
        ones match. Most patches of a whole page are backgrounds and props, so
        the tile covering a face can retrieve something that is not a face —
        measured, and the reason a tight crop of one coloured face reproduced a
        character's skin where a whole finished page of the same character in
        the same colour world produced a cold blue one.

        Splitting on the way in is that finding made automatic: each panel is
        one composition, and its tiles come from one scene.

        Panels are cropped to their boxes and not masked to their polygons. A
        diagonal panel's crop catches a sliver of its neighbour, which is drawn
        colour; masking it out would put white in the patches the retrieval
        ranks, and a reference exists to supply colour (`cobra._tiles`).

        A page whose panels cannot be found — one that bleeds, one drawn
        without frames — comes back empty, and the caller stores the page
        whole. Half a split is worse than none.

        A panel too small for the proposer's frame is dropped, and if fewer
        than two survive the page is kept whole. Nothing reaches the model at
        its own size: `cobra._tiles` resizes every reference to the target
        bucket, so a 490 px panel against a 1024 px frame arrives blown up
        twice over. Measured in `reports/10-retrieval`, that smear outranks the
        sharp tile that actually holds the character — the face falls from rank
        1 to rank 22 of 80 — because line-art-against-colour similarity is
        decided on low frequencies, which is exactly what upscaling invents.
        Restoring the guard puts it back at rank 1.

        The target is not known here: it follows the aspect of whichever panel
        is being coloured, and that panel does not exist at upload time. The
        nominal long side below is `CobraProposer.resolution`'s default, and
        the buckets sit close enough together for the approximation to hold.
        """
        try:
            line_mask, _ = load_line_art(path)
            found = segment_panels(line_mask)
        except (OSError, ValueError):
            return []
        found = [
            panel
            for panel in found
            if max(panel.width, panel.height) >= _NOMINAL_TARGET / _MAX_UPSCALE
        ]
        if len(found) < 2:
            return []

        stored: list[Reference] = []
        with Image.open(path) as opened:
            page = opened.convert("RGB")
            for order, panel in enumerate(found):
                crop = page.crop(
                    (panel.x, panel.y, panel.x + panel.width, panel.y + panel.height)
                )
                staged = self.workdir / f"_panel{order + 1}_{Path(str(path)).name}"
                staged = staged.with_suffix(".png")
                crop.save(staged)
                try:
                    stored.append(
                        self.reference_store.add(
                            staged,
                            label=f"{label} — panel {order + 1}",
                            kind="panel",
                        )
                    )
                finally:
                    staged.unlink(missing_ok=True)
        return stored

    def add_palette(self, path: str | Path, original_name: str = "") -> list[PaletteEntry]:
        """Store a palette image and take every colour in it.

        Same extraction as a character sheet's, without the choosing: a
        palette *is* the artist's decision about which colours this book uses,
        already made, in the file. Asking them to confirm each swatch of a
        strip they made on purpose is asking them to do the same work twice.

        It is not shown to the proposer. See `references.PALETTE_KIND`.
        """
        with self.lock:
            reference = self.reference_store.add(
                path, label=original_name or Path(path).name, kind=PALETTE_KIND
            )
            return [
                self.include_candidate(reference.id, rgb)
                for rgb in self.candidates(reference.id)
            ]

    def remove_reference(self, reference_id: int) -> bool:
        """Delete an image, and the colours it is answerable for.

        A palette image *is* its colours, so they go with it. A character
        sheet is not: the artist picked those colours out of a drawing one at
        a time, and deleting the drawing must not silently repaint every zone
        snapped to them — that is a page-wide change made by a click that said
        nothing about colour.

        Only a reference invalidates the flats, and for a different reason
        again: the proposal came from an image that is no longer there
        (rule 4). A palette image was never shown to the proposer.
        """
        with self.lock:
            reference = self.reference_store.get(reference_id)
            if reference is None or not self.reference_store.remove(reference_id):
                return False
            self._candidates.pop(reference_id, None)

            if reference.kind == PALETTE_KIND:
                for (owner, _), entry_id in list(self._taken.items()):
                    if owner == reference_id:
                        self.delete_palette_entry(entry_id)
            else:
                self._flats_done = False
            return True

    def palette_images(self) -> list[Reference]:
        return [r for r in self.reference_store if r.kind == PALETTE_KIND]

    def candidates(self, reference_id: int) -> list[tuple[int, int, int]]:
        """The colours found in one reference, in extraction order.

        Cached because `extract_palette` is a median cut over a full-size
        image and `state()` is called after every button. Deterministic, so
        the cache can never disagree with a re-extraction — it only skips it.
        """
        with self.lock:
            if reference_id not in self._candidates:
                image = Image.fromarray(self.reference_store.image(reference_id))
                try:
                    found = extract_palette(image, sheet_mode=True)
                except EmptyImageError:
                    # A panel of solid black, or one of bare paper. It offers
                    # nothing, which is an answer — not a reason for the whole
                    # sidebar to fail to load.
                    found = []
                self._candidates[reference_id] = [colour.rgb for colour in found]
            return self._candidates[reference_id]

    def include_candidate(self, reference_id: int, rgb) -> PaletteEntry:
        """Put one of a reference's colours into the palette."""
        with self.lock:
            wanted = _rgb(rgb)
            if wanted not in self.candidates(reference_id):
                raise StepError("That colour is not one of this reference's.")
            existing = self._taken.get((reference_id, wanted))
            if existing is not None:
                return self._entry(existing)

            # Named after the image it came from: "colour 397" tells the
            # artist nothing, and the id it is named after is an accident of
            # how many zones the last page happened to have.
            reference = self.reference_store.get(reference_id)
            position = self.candidates(reference_id).index(wanted) + 1
            entry = PaletteEntry(
                project_id=0,
                rgb=wanted,
                label=f"{reference.label if reference else 'colour'} {position}",
                id=self._next_entry_id,
            )
            self._next_entry_id += 1
            self._palette.append(entry)
            self._taken[(reference_id, wanted)] = int(entry.id or 0)
            self._save_palette()
            return entry

    def set_palette_colour(self, entry_id: int, rgb) -> PaletteEntry:
        """Change what one palette entry *is*.

        Every zone holding this id changes with it, everywhere on the page, in
        one row — which is the whole reason regions store `palette_entry_id`
        and never an RGB (rule 1). Nothing is invalidated and nothing is
        re-segmented: the flats raster and the PSD are both resolved through
        the palette at the moment they are asked for.
        """
        with self.lock:
            entry = self._entry(entry_id)
            entry.rgb = _rgb(rgb)
            entry.revision += 1
            self._save_palette()
            return entry

    def delete_palette_entry(self, entry_id: int) -> None:
        """Take a colour out of the palette, and off every zone using it.

        A zone cannot point at an entry that is gone, so the segments snapped
        to it go back to the colour the model proposed for them. That is the
        same thing `unsnap_segment` does, done for the artist rather than to
        them.
        """
        with self.lock:
            entry = self._entry(entry_id)
            self._palette.remove(entry)
            for key, taken in list(self._taken.items()):
                if taken == entry_id:
                    del self._taken[key]

            for segment in self.segments:
                if segment.palette_entry_id != entry_id:
                    continue
                original = self._auto_entry.get(segment.key)
                if original is None:
                    continue
                segment.palette_entry_id = original
                segment.snapped = False
                self.panels[segment.panel].assignments[segment.label] = original
            self._save_palette()

    def _entry(self, entry_id: int) -> PaletteEntry:
        for entry in self._palette:
            if entry.id == entry_id:
                return entry
        raise StepError(f"No palette entry {entry_id}.")

    # The palette outlives the page and the process, exactly as the reference
    # pool does: it belongs to the book. Without this a restart would empty a
    # palette the artist had built while leaving the references that fed it
    # sitting on disk, which looks like a bug and is one.
    @property
    def _palette_path(self) -> Path:
        return self.workdir / "palette.json"

    def _save_palette(self) -> None:
        self._palette_path.write_text(
            json.dumps(
                {
                    "next_id": self._next_entry_id,
                    "entries": [
                        {"id": e.id, "rgb": list(e.rgb), "label": e.label,
                         "revision": e.revision}
                        for e in self._palette
                    ],
                    # Which reference each colour was taken from, so the chips
                    # under it can show what is already in.
                    "taken": [
                        {"reference": ref, "rgb": list(rgb), "entry": entry}
                        for (ref, rgb), entry in self._taken.items()
                    ],
                },
                indent=1,
            ),
            encoding="utf-8",
        )

    def _load_palette(self) -> None:
        self._palette = []
        self._taken = {}
        self._next_entry_id = 1
        if not self._palette_path.exists():
            return
        try:
            stored = json.loads(self._palette_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # A corrupt palette is an empty one, not a dead app.
        self._palette = [
            PaletteEntry(
                project_id=0,
                rgb=_rgb(entry["rgb"]),
                label=entry.get("label", ""),
                id=int(entry["id"]),
                revision=int(entry.get("revision", 0)),
            )
            for entry in stored.get("entries", [])
        ]
        self._taken = {
            (int(row["reference"]), _rgb(row["rgb"])): int(row["entry"])
            for row in stored.get("taken", [])
        }
        self._next_entry_id = int(stored.get("next_id", 1))

    @property
    def palette(self) -> list[PaletteEntry]:
        """What zones snap to, then the private entries flats invented."""
        return [*self._palette, *self._created_palette]

    @property
    def references(self) -> list[np.ndarray]:
        return self.reference_store.images()

    @property
    def reference_names(self) -> list[str]:
        return [reference.label for reference in self.reference_store]

    @property
    def palette_by_id(self) -> dict[int, PaletteEntry]:
        return {int(entry.id): entry for entry in self.palette if entry.id is not None}

    # -- 5. generate flats -----------------------------------------------

    def generate_flats(self) -> dict[str, int]:
        with self.lock:
            self._require_page()
            if not self._zones_done:
                raise StepError("Segment zones first — there is nothing to colour yet.")

            # `threshold=None` unconditionally: **flats never snap**. Every
            # zone's modal colour becomes its own entry and stays that way
            # until the artist says otherwise, one segment at a time.
            #
            # Snapping used to happen here, in the same pass, which left it
            # the one stage of the pipeline with no boundary the artist could
            # inspect or disagree with — and it is the stage that quietly
            # folded every neutral zone into a sheet's ink black. Splitting it
            # out is what makes "every place the machine got it wrong is one
            # click to fix" true of colour and not only of geometry.
            threshold = None

            assigned = 0
            for panel in self.panels:
                if panel.label_map is None:
                    continue
                request = PanelRequest(
                    line_art=self._line_art_for(panel),
                    label_map=panel.label_map,
                    references=self.reference_images(),
                )
                proposal = self.proposer.propose(request)

                assignments, created = assign_zones(
                    proposal,
                    panel.label_map,
                    self.palette,
                    threshold=threshold,
                    next_id=self._next_entry_id,
                    label_prefix=f"p{panel.order + 1}",
                )
                self._created_palette.extend(created)
                self._next_entry_id += len(created)

                panel.assignments = {a.label: a.palette_entry_id for a in assignments}
                panel.flagged = set()
                assigned += len(assignments)

            self.segments = []
            for panel in self.panels:
                if panel.label_map is None:
                    continue
                self.segments.extend(
                    build_segments(
                        panel.order, panel.label_map, panel.assignments, (panel.x, panel.y)
                    )
                )
            self._auto_entry = {
                segment.key: segment.palette_entry_id for segment in self.segments
            }

            self._flats_done = True
            return {
                "assigned": assigned,
                "segments": len(self.segments),
                "colours": len(self.palette),
                "snapped": 0,
            }

    # -- 6. snap ---------------------------------------------------------

    def _require_flats(self) -> None:
        if not self._flats_done:
            raise StepError("Generate flats first — there are no segments to snap yet.")

    def segment(self, panel: int, label: int) -> Segment | None:
        for candidate in self.segments:
            if candidate.key == (panel, label):
                return candidate
        return None

    def segment_at(self, x: int, y: int) -> Segment | None:
        """The segment under a page-space point, or None.

        Read off the label map rather than off segment bounds: bounds overlap
        for interlocking zones, and a click has to resolve to the zone the
        artist actually pointed at.
        """
        with self.lock:
            for panel in self.panels:
                if panel.label_map is None:
                    continue
                local_x, local_y = x - panel.x, y - panel.y
                if not (0 <= local_x < panel.width and 0 <= local_y < panel.height):
                    continue
                label = int(panel.label_map[local_y, local_x])
                if label == UNASSIGNED:
                    continue
                return self.segment(panel.order, label)
            return None

    def snap_suggestion(self, segment: Segment) -> tuple[PaletteEntry | None, float]:
        """Nearest *reference* colour to what the proposer suggested, and its distance.

        Measured against the reference half only. The created half holds the
        segments' own private entries, so including it would offer every
        segment itself at distance zero.

        This suggests and never acts. The distance comes back with it so the
        artist can see the number the old automatic snap decided on silently.
        """
        entry = self.palette_by_id.get(segment.palette_entry_id)
        if entry is None or not self._palette:
            return None, float("inf")
        return nearest_entry(entry.rgb, self._palette)

    def snap_segment(self, panel: int, label: int, entry_id: int | None = None) -> Segment:
        """Point one segment at a palette entry. A single-row change.

        `entry_id` of None takes the suggestion whatever its distance: the
        artist asked for this one, and `SNAP_MAX_DELTA` orders their attention
        rather than vetoing their instruction.
        """
        with self.lock:
            self._require_flats()
            segment = self.segment(panel, label)
            if segment is None:
                raise StepError(f"No segment {label} in panel {panel + 1}.")

            if entry_id is None:
                entry, _ = self.snap_suggestion(segment)
                if entry is None:
                    raise StepError(
                        "No reference colours to snap to — upload a character sheet."
                    )
                entry_id = int(entry.id or 0)
            elif entry_id not in self.palette_by_id:
                raise StepError(f"No palette entry {entry_id}.")

            segment.palette_entry_id = entry_id
            segment.snapped = entry_id != self._auto_entry.get(segment.key)
            self.panels[panel].assignments[label] = entry_id
            return segment

    def unsnap_segment(self, panel: int, label: int) -> Segment:
        """Put back what the proposer said. A snap the artist cannot undo is a
        decision taken away from them, which is the thing this step exists to
        stop."""
        with self.lock:
            self._require_flats()
            segment = self.segment(panel, label)
            if segment is None:
                raise StepError(f"No segment {label} in panel {panel + 1}.")
            original = self._auto_entry.get(segment.key)
            if original is None:
                raise StepError(f"Segment {label} has no original colour recorded.")
            segment.palette_entry_id = original
            segment.snapped = False
            self.panels[panel].assignments[label] = original
            return segment

    def snap_all(self, threshold: float | None = SNAP_MAX_DELTA) -> dict[str, int]:
        """Snap every segment whose suggestion falls within `threshold`.

        The bulk shortcut, for a page whose references are good enough that the
        artist would have agreed with the machine anyway. It goes through the
        same per-segment call, so it can never do something clicking could not,
        and every segment it touches stays individually reversible.

        `threshold=None` snaps every segment to its nearest reference colour
        whatever the distance. That is the artist overriding the guard
        deliberately, and it is the one call that repaints a page wholesale.
        """
        with self.lock:
            self._require_flats()
            snapped = skipped = 0
            for segment in self.segments:
                entry, distance = self.snap_suggestion(segment)
                if entry is None or (threshold is not None and distance > threshold):
                    skipped += 1
                    continue
                self.snap_segment(segment.panel, segment.label, int(entry.id or 0))
                snapped += 1
            return {
                "snapped": snapped,
                "skipped": skipped,
                "segments": len(self.segments),
            }

    # -- 7. export -------------------------------------------------------

    def _panel_flats(self) -> list[PanelFlats]:
        return [
            PanelFlats(
                order=panel.order,
                x=panel.x,
                y=panel.y,
                label_map=panel.label_map,
                assignments=panel.assignments,
            )
            for panel in self.panels
            if panel.label_map is not None
        ]

    def export_psd(self, path: str | Path | None = None) -> Path:
        with self.lock:
            if not self._flats_done:
                raise StepError("Generate flats first — there is nothing to export.")
            target = Path(path) if path else self.workdir / f"{Path(self.original_name).stem}_flats.psd"
            return write_psd(
                target, (self.width, self.height), self._panel_flats(), self.palette_by_id
            )

    def flats_rgba(self) -> np.ndarray:
        with self.lock:
            return flats_preview(
                (self.width, self.height), self._panel_flats(), self.palette_by_id
            )

    def unsnapped_mask(self) -> np.ndarray:
        """Every segment the artist has not resolved, as a page-space mask.

        Step 6's remaining workload, made visible: everything the machine
        declined to decide. The same array backs the browser overlay and
        `comiccolor flatten --steps`, so what the artist sees on screen and
        what the run writes to disk cannot drift apart.
        """
        with self.lock:
            canvas = np.zeros((self.height, self.width), dtype=bool)
            for segment in self.segments:
                if segment.snapped:
                    continue
                panel = self.panels[segment.panel]
                if panel.label_map is None:
                    continue
                mask = panel.label_map == segment.label
                rows = min(mask.shape[0], self.height - panel.y)
                cols = min(mask.shape[1], self.width - panel.x)
                window = canvas[panel.y : panel.y + rows, panel.x : panel.x + cols]
                np.logical_or(window, mask[:rows, :cols], out=window)
            return canvas

    def zones_rgba(self) -> np.ndarray:
        """Zone map as a preview, one arbitrary colour per zone.

        Deliberately not the proposal raster and deliberately not the flats:
        this shows where the boundaries fell, which is the only question
        "Segment zones" answers.
        """
        from ..colour.proposer import distinct_colour

        canvas = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        for panel in self.panels:
            if panel.label_map is None:
                continue
            labels = panel.label_map
            table = np.zeros((int(labels.max()) + 1, 4), dtype=np.uint8)
            present = np.unique(labels)
            for index, label in enumerate(present[present != UNASSIGNED]):
                table[label] = (*distinct_colour(index), 255)
            rows = min(labels.shape[0], self.height - panel.y)
            cols = min(labels.shape[1], self.width - panel.x)
            patch = table[labels[:rows, :cols]]
            window = canvas[panel.y : panel.y + rows, panel.x : panel.x + cols]
            painted = labels[:rows, :cols] != UNASSIGNED
            window[painted] = patch[painted]
        return canvas

    # -- bookkeeping -----------------------------------------------------

    def _invalidate_from_panels(self) -> None:
        for panel in self.panels:
            panel.label_map = None
            panel.assignments = {}
            panel.flagged = set()
        self.segments = []
        self._auto_entry = {}
        self._zones_done = False
        self._flats_done = False

    def state(self) -> dict:
        with self.lock:
            chosen = {e.id for e in self._palette}
            return {
                "page": None
                if self.line_mask is None
                else {
                    "name": self.original_name,
                    "width": self.width,
                    "height": self.height,
                },
                "panels": [
                    {"order": p.order, "polygon": p.polygon, "zones": p.zone_count}
                    for p in self.panels
                ],
                "protected": self.protected,
                # `source` splits the palette the way the artist thinks about
                # it: the colours a reference brought in are the ones worth
                # showing as swatches and worth snapping *to*. The proposed
                # half is one private entry per segment — after a real page
                # that is hundreds of them, and offering a segment its own
                # colour to snap to is offering it nothing.
                "palette": [
                    {
                        "id": e.id,
                        "rgb": list(e.rgb),
                        "label": e.label,
                        "source": "palette" if e.id in chosen else "proposed",
                    }
                    for e in self.palette
                ],
                # Each reference carries the colours found in it and, for
                # each, the palette entry the artist made from it — or null.
                # That pair is the whole of the chips under the thumbnail:
                # what this image offers, and what has been taken.
                "references": [
                    {
                        "id": r.id,
                        "label": r.label,
                        "kind": r.kind,
                        "added": r.added,
                        "candidates": [
                            {"rgb": list(rgb), "entry_id": self._taken.get((r.id, rgb))}
                            for rgb in self.candidates(r.id)
                        ],
                    }
                    for r in self.reference_store
                    if r.kind != PALETTE_KIND
                ],
                # A palette image has no chips to click: every colour in it is
                # already in. What it shows is what it brought, and what
                # deleting it would take away again.
                "palettes": [
                    {
                        "id": r.id,
                        "label": r.label,
                        "added": r.added,
                        "colours": [list(rgb) for rgb in self.candidates(r.id)],
                    }
                    for r in self.palette_images()
                ],
                # Which geometry the artist may still correct. Detection
                # proposes it, they settle it, and once the zones are cut from
                # it the shape is no longer a proposal — it is what the flats
                # were built on, and moving it silently would leave the zones
                # describing a page that no longer exists.
                "editable": {
                    "panels": bool(self.panels) and not self._zones_done,
                    "bubbles": self._bubbles_done and not self._zones_done,
                    # Zones are corrected between the cut and the colour, and
                    # the corrections are permanent — there is no unmerge.
                    "zones": self._zones_done and not self._flats_done,
                },
                # Step 6 is per-segment and never "done" — what the sidebar
                # reports is how much of the page the artist has resolved.
                "segments": {
                    "count": len(self.segments),
                    "snapped": sum(1 for s in self.segments if s.snapped),
                    "snappable": bool(self._palette),
                    "threshold": SNAP_MAX_DELTA,
                },
                "proposer": self.proposer.name,
                "extractor": self.extractor.name,
                "done": {
                    "page": self.line_mask is not None,
                    "panels": bool(self.panels),
                    "bubbles": self._bubbles_done,
                    "zones": self._zones_done,
                    "flats": self._flats_done,
                },
            }
