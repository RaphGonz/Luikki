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

import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from ..colour.extract import extract_palette
from ..colour.proposer import (
    ColourProposer,
    DistinctColourProposer,
    PanelRequest,
    ReferenceImage,
)
from ..colour.references import Reference, ReferenceStore
from ..colour.segments import Segment, build_segments
from ..colour.snap import SNAP_MAX_DELTA, assign_zones, nearest_entry
from ..export.psd import PanelFlats, flats_preview, write_psd
from ..extract.base import LineExtractor
from ..extract.manga_line import MangaLineExtractor
from ..model.entities import PaletteEntry
from ..model.masks import UNASSIGNED
from ..segmentation.bubbles import BubbleDetector, detect_bubbles
from ..segmentation.panels import segment_panels
from ..segmentation.preprocess import binarise_lines, load_line_art
from ..segmentation.protected import rasterize_protected_for_panel
from ..segmentation.segmenter import LineFillerSegmenter
from ..segmentation.trappedball import expand_under_lines


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
        self.reset()
        self._rebuild_reference_palette()

    # -- state -----------------------------------------------------------

    def reset(self) -> None:
        self.source: Path | None = None
        self.original_name: str = ""
        self.width = 0
        self.height = 0
        self.grey: np.ndarray | None = None
        self.line_mask: np.ndarray | None = None
        # Extractor output, computed lazily by `structural_mask`.
        self._structural: np.ndarray | None = None
        self.panels: list[PanelState] = []
        self.protected: list[list[tuple[int, int]]] = []
        # Palette in two halves. The reference half is derived — delete a
        # character sheet and its colours go with it — while the created half
        # is what `generate_flats` invented for zones that matched nothing.
        # One list would mean a reference deletion silently dropped the other
        # kind, or that rebuilding after a deletion could not be done at all.
        self._reference_palette: list[PaletteEntry] = []
        self._created_palette: list[PaletteEntry] = []
        self._next_entry_id = 1
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
            # The palette belongs to the book, not the page, so dropping in
            # the next page must not throw it away. The references themselves
            # need no carrying: they are on disk.
            reference_palette = self._reference_palette
            created_palette = self._created_palette
            next_id = self._next_entry_id
            self.reset()
            self._reference_palette = reference_palette
            self._created_palette = created_palette
            self._next_entry_id = next_id

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
                # Flats must meet underneath the ink, or every line leaves a
                # white seam in the export (§10, anti-aliased line art).
                # This one takes the *raw* ink, not the structural lines: the
                # layer the artist drops on top is their real ink, so that is
                # what the flats have to reach under — including the solid
                # blacks the extractor turned into contours.
                panel.label_map = expand_under_lines(
                    labels, self.line_mask[window], protected=blocked
                )
                panel.assignments = {}
                panel.flagged = set()

            self._zones_done = True
            self._flats_done = False
            return self.panels

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
        self._require_page()
        if self._structural is None:
            lines = self.extractor.extract(self.grey).lines
            self._structural = binarise_lines(lines)
        return self._structural

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
        """
        crop = self.grey[
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

    def add_reference(
        self, path: str | Path, original_name: str = "", kind: str = "sheet"
    ) -> list[PaletteEntry]:
        """One upload, two jobs: palette colours out, Cobra reference in.

        The barebone app has no separate swatch and character-sheet inputs
        (features 18 and 19 collapse to one) — the same image is where the
        colours come from and what the model is shown.

        `kind` is `page`, `panel` or `sheet`. It changes nothing here; it is
        recorded because the proposal-time fitting step needs it and only the
        artist knows it.
        """
        with self.lock:
            self.reference_store.add(path, label=original_name or Path(path).name, kind=kind)
            return self._rebuild_reference_palette()

    def remove_reference(self, reference_id: int) -> bool:
        """Delete a reference and the colours it contributed.

        Colours `generate_flats` invented for unmatched zones are kept: they
        were never this reference's to give. The flats themselves are stale
        either way, since the palette zones snapped to has changed (rule 4).
        """
        with self.lock:
            if not self.reference_store.remove(reference_id):
                return False
            self._rebuild_reference_palette()
            self._flats_done = False
            return True

    def _rebuild_reference_palette(self) -> list[PaletteEntry]:
        """Re-extract the palette from every stored reference, in id order.

        Rebuilding rather than patching is what makes deletion honest: there
        is no record of which entry came from which image, and inventing one
        would be a second source of truth. `extract_palette` is median cut,
        so the same files in the same order give the same colours every time
        — including across a restart, which is why the palette does not need
        persisting separately.
        """
        self._reference_palette = []
        self._next_entry_id = 1
        for reference in self.reference_store:
            image = Image.fromarray(self.reference_store.image(reference.id))
            for colour in extract_palette(image, sheet_mode=True):
                self._reference_palette.append(
                    PaletteEntry(
                        project_id=0,
                        rgb=colour.rgb,
                        label=f"colour {self._next_entry_id}",
                        id=self._next_entry_id,
                    )
                )
                self._next_entry_id += 1

        # Created entries are renumbered above them, so ids stay unique after
        # a rebuild shortens or lengthens the reference half.
        for entry in self._created_palette:
            entry.id = self._next_entry_id
            self._next_entry_id += 1
        return list(self._reference_palette)

    @property
    def palette(self) -> list[PaletteEntry]:
        """What zones snap to: reference colours first, then invented ones."""
        return [*self._reference_palette, *self._created_palette]

    @property
    def references(self) -> list[np.ndarray]:
        return self.reference_store.images()

    @property
    def reference_names(self) -> list[str]:
        return [r.label for r in self.reference_store]

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
        if entry is None or not self._reference_palette:
            return None, float("inf")
        return nearest_entry(entry.rgb, self._reference_palette)

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
            reference_ids = {e.id for e in self._reference_palette}
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
                        "source": "reference" if e.id in reference_ids else "proposed",
                    }
                    for e in self.palette
                ],
                "references": [
                    {"id": r.id, "label": r.label, "kind": r.kind, "added": r.added}
                    for r in self.reference_store
                ],
                # Which geometry the artist may still correct. Detection
                # proposes it, they settle it, and once the zones are cut from
                # it the shape is no longer a proposal — it is what the flats
                # were built on, and moving it silently would leave the zones
                # describing a page that no longer exists.
                "editable": {
                    "panels": bool(self.panels) and not self._zones_done,
                    "bubbles": self._bubbles_done and not self._zones_done,
                },
                # Step 6 is per-segment and never "done" — what the sidebar
                # reports is how much of the page the artist has resolved.
                "segments": {
                    "count": len(self.segments),
                    "snapped": sum(1 for s in self.segments if s.snapped),
                    "snappable": bool(self._reference_palette),
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
