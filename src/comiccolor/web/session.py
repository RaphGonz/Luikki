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
from ..colour.snap import SNAP_MAX_DELTA, assign_zones
from ..export.psd import PanelFlats, flats_preview, write_psd
from ..extract.base import LineExtractor
from ..extract.manga_line import MangaLineExtractor
from ..model.entities import PaletteEntry
from ..model.masks import UNASSIGNED
from ..segmentation.bubbles import BubbleDetector, detect_bubbles
from ..segmentation.panels import box_to_polygon, segment_panels
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
            boxes = segment_panels(self.line_mask)
            self.panels = [
                PanelState(
                    order=order,
                    x=box.x,
                    y=box.y,
                    width=box.width,
                    height=box.height,
                    polygon=box_to_polygon(box),
                )
                for order, box in enumerate(boxes)
            ]
            self._invalidate_from_panels()
            return self.panels

    # -- 3. detect bubbles -----------------------------------------------

    def detect_bubbles(self) -> list[list[tuple[int, int]]]:
        with self.lock:
            self._require_page()
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

            # With no palette uploaded there is nothing to snap to, so every
            # zone's mode becomes its own entry (see snap.assign_zones).
            # Decided once, before the loop: entries created for panel 1 are
            # not a palette to snap panel 2 against.
            threshold = SNAP_MAX_DELTA if self.palette else None

            assigned = 0
            flagged = 0
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
                panel.flagged = {a.label for a in assignments if a.flagged}
                assigned += len(assignments)
                flagged += len(panel.flagged)

            self._flats_done = True
            return {"assigned": assigned, "flagged": flagged, "colours": len(self.palette)}

    # -- 6. export -------------------------------------------------------

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
        self._zones_done = False
        self._flats_done = False

    def state(self) -> dict:
        with self.lock:
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
                "palette": [
                    {"id": e.id, "rgb": list(e.rgb), "label": e.label} for e in self.palette
                ],
                "references": [
                    {"id": r.id, "label": r.label, "kind": r.kind, "added": r.added}
                    for r in self.reference_store
                ],
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
