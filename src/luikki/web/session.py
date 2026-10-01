"""One project, six buttons, one page open at a time.

The project is the working folder, and every page in it is saved as the
artist works (`project.py`): each method that changes something writes it
before returning. One page is open at a time and its state lives in this
object; adding or opening another leaves this one on disk as it was left. The
SQLite store in `luikki.model` is not used — a page is a handful of JSON and
image files, which is simpler to read and to debug.

What *is* carried over from the store's design, because it is non-negotiable
(rule 1): a zone holds a `palette_entry_id` and there is nowhere in this module
for a zone to hold an RGB value. Luikki proposes no colour (ROADMAP G): the
entries are the eight fake flats of `export.flat_colours`, given so that no two
touching zones share one, and resolved at render and export time.

Rule 2 — nothing runs by itself. Every method here is one button. Rule 4 —
re-running a step replaces its output, so each step clears what depended on it.
"""

from __future__ import annotations

import inspect
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage

from ..account import Account
from ..export.flat_colours import FLAT_PALETTE, assign_flat_colours
from ..export.psd import GRANULARITIES, PanelFlats, flats_preview, layer_count, write_psd
from ..extract.base import LineExtractor
from ..extract.passthrough import PassthroughExtractor
from ..model.entities import PaletteEntry
from ..model.masks import UNASSIGNED, check_coverage, region_stats
from ..segmentation.absorb import absorb_micro_zones
from ..segmentation.bubbles import BubbleDetector, detect_bubbles
from ..segmentation.leaks import LeakParams, split_open_borders
from ..segmentation.panels import segment_panels
from ..segmentation.planes import (
    CHARACTER,
    FAR,
    MIDDLE,
    NEAR,
    PLANES,
    DepthEstimator,
    panel_planes,
    planes_from,
)
from ..segmentation.preprocess import binarise_lines, load_line_art, thick_ink
from ..segmentation.protected import rasterize_protected_for_panel
from ..segmentation.segmenter import LineFillerSegmenter
from ..segmentation.trappedball import expand_under_lines, inked_zones
from . import project
from .progress import Cancelled, Progress

# Seconds per megapixel for each pass of Segment zones — what the progress bar
# sizes its steps by. Measured on `test_pages/antoine_page.png` (14.4 MP, CPU)
# on 2026-09-25, once `linefiller_fast` had taken LineFiller from minutes to
# seconds: the leak audit is now the largest of the segmentation passes, and
# extraction dwarfs them all on a CPU (about 18 s/MP, against about 1.2 on a
# GPU through DirectML). Every run folds what it measured back in (`_learn`).
_PASS_COST = {"extract": 18.0, "ball": 0.1, "merge": 0.3, "audit": 1.2, "expand": 0.23}


def _megapixels(panel: "PanelState") -> float:
    return panel.width * panel.height / 1e6


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
    # zone label -> palette entry id: one of the eight fake flats, given by
    # `_assign_colours` whenever the zones change. Never an RGB (rule 1).
    assignments: dict[int, int] = field(default_factory=dict)
    # zone label -> plane (`segmentation.planes`). Empty until Planes has run.
    planes: dict[int, int] = field(default_factory=dict)
    # The depth groups the planes were voted on (`planes.depth_groups`),
    # panel-local: a zone cut or merged later votes again on what is under it.
    depth_groups: np.ndarray | None = None
    # Pixels this panel left with no zone at all, once the two deliberate
    # exceptions — protected, and the artist's own spot black — are taken out.
    # An alarm, not a score, like the zone count: it should read 0, and it read
    # in the thousands in silence until the export showed white.
    orphans: int = 0

    @property
    def zone_count(self) -> int:
        if self.label_map is None:
            return 0
        present = np.unique(self.label_map)
        return int((present != UNASSIGNED).sum())


# How many merges and cuts the zones can take back. Each one holds one panel's
# label map, and a merge or a cut touches exactly one panel.
_UNDO_DEPTH = 20

# What the planes look like when nobody says otherwise (the command line): a
# tint over the page, never in the PSD. The app sends its own, from the
# `--plane-*` tokens of `app.css`.
PLANE_TINTS = {
    NEAR: (235, 90, 60),
    MIDDLE: (120, 200, 80),
    FAR: (60, 160, 230),
    CHARACTER: (200, 60, 200),
}


# How finely a curve is sampled, in page pixels between two samples. Half a
# pixel is below what the rasteriser can tell apart, so the flattened shape and
# the curve cover exactly the same pixels.
_CURVE_STEP = 0.5


def flatten_polygon(polygon) -> list[tuple[int, int]]:
    """A polygon of straight edges, from one whose nodes may carry handles.

    A node is `(x, y)` — a corner — or `(x, y, hx, hy)`, where `(hx, hy)` is
    the tangent the artist pulled out of it. Nothing downstream of here knows
    what a Bézier is: `cv2.fillPoly` and `cv2.polylines` take points, so the
    curve is sampled into points *once*, here, at the moment of use. The nodes
    and their handles stay the stored truth, so the artist can grab a handle
    again after reopening the page — which is the whole reason they are kept.
    """
    nodes = [tuple(node) for node in polygon]
    if not any(len(node) > 2 for node in nodes):
        return [(int(node[0]), int(node[1])) for node in nodes]

    points: list[tuple[int, int]] = []
    for index, node in enumerate(nodes):
        after = nodes[(index + 1) % len(nodes)]
        x0, y0 = float(node[0]), float(node[1])
        x3, y3 = float(after[0]), float(after[1])
        # A handle points the way out of its node; the far end of the edge is
        # entered against its own, which is what makes the joint smooth.
        ox, oy = (float(node[2]), float(node[3])) if len(node) > 2 else (0.0, 0.0)
        ix, iy = (float(after[2]), float(after[3])) if len(after) > 2 else (0.0, 0.0)
        if not (ox or oy or ix or iy):
            points.append((int(round(x0)), int(round(y0))))
            continue
        x1, y1 = x0 + ox, y0 + oy
        x2, y2 = x3 - ix, y3 - iy
        # Sampled against the control polygon's length, which is never shorter
        # than the curve — so the step is at worst finer than asked for.
        span = (
            abs(x1 - x0) + abs(y1 - y0) + abs(x2 - x1) + abs(y2 - y1) + abs(x3 - x2) + abs(y3 - y2)
        )
        steps = max(2, min(400, int(span / _CURVE_STEP) + 1))
        for step in range(steps):
            t = step / steps
            u = 1.0 - t
            points.append(
                (
                    int(round(u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3)),
                    int(round(u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3)),
                )
            )
    return points


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


class StepError(RuntimeError):
    """What the artist asked for cannot be done now, named by a code.

    The code is a locale key without its `error.` prefix, and `params` fill
    its placeholders: the browser words the refusal in the artist's language.
    Codes are written out at the raise, so `tests/test_locales.py` can check
    that each one has its sentence.
    """

    def __init__(self, code: str, status: int = 409, **params):
        super().__init__(f"{code} {params}" if params else code)
        self.code = code
        self.status = status
        self.params = params



class Session:
    """The whole application state. One instance per process."""

    def __init__(
        self,
        workdir: str | Path,
        extractor: LineExtractor | None = None,
        account: Account | None = None,
        depth: DepthEstimator | None = None,
    ):
        self.workdir = Path(workdir)
        # Who is signed in on this machine, for the rail. None where nothing
        # signs in: the CLI, and most tests.
        self.account = account
        self.workdir.mkdir(parents=True, exist_ok=True)
        # The whole of the artist's ink is the line by default: the extractor
        # erases small dense detail — windows, pipes — it takes for hatching
        # (ROADMAP G5). It runs only on a page where the artist turns it on.
        self.raw_extractor: LineExtractor = PassthroughExtractor()
        # MangaLineExtraction, built on first use: it loads 172 MB of weights.
        self._line_extractor = extractor
        # Serialises the buttons. Segmentation takes seconds and the artist
        # will double-click; two passes mutating the same panel list is the
        # one race worth spending a lock on.
        self.lock = threading.RLock()
        # Read by `/api/progress` without that lock, while a step holds it.
        self.progress = Progress()
        # Machine-scoped rather than page-scoped: how long each pass takes here.
        self._pass_cost = dict(_PASS_COST)
        # Loaded on the first press of their step rather than here: each is
        # tens of megabytes off disk, and a page may never need it.
        self.bubble_detector: BubbleDetector | None = None
        self.depth_estimator = depth
        # How open a border may be before the leak audit calls it a passage
        # rather than a hole in a line (§1.3). Held on the session, not passed
        # and forgotten, because it is the one segmentation knob the artist
        # turns: they change it, press Segment zones again, and look. Book-
        # scoped — an artist's ink does not change per page — and so is how
        # they stack a PSD.
        self.leak_gap = LeakParams().max_open_share
        self.granularity = "plane"
        # The two ink layers a printer wants over the flats (`_write_support`).
        # Off unless asked for: it is the one thing that puts line art in an
        # export. Book-scoped, like the stack it sits on.
        self.support_grey = False
        self.reset()
        # page id -> name and stage, for the page list. Kept here rather than
        # read off disk by `state()`, which runs after every press.
        self._pages = project.summaries(self.workdir)
        current = project.load_project(self)
        if current in self._pages:
            try:
                project.open_page(self, current)
            except (OSError, ValueError):
                # A page that cannot be read opens nothing. It stays in the
                # list, and the app starts rather than dying on it.
                pass

    @property
    def line_extractor(self) -> LineExtractor:
        if self._line_extractor is None:
            from ..extract.manga_line import MangaLineExtractor

            self._line_extractor = MangaLineExtractor()
        return self._line_extractor

    @property
    def extractor(self) -> LineExtractor:
        """What the open page's zones are cut from: its ink, or extracted lines."""
        return self.line_extractor if self.extract_lines else self.raw_extractor

    @property
    def palette(self) -> list[PaletteEntry]:
        return FLAT_PALETTE

    @property
    def palette_by_id(self) -> dict[int, PaletteEntry]:
        return {int(entry.id): entry for entry in FLAT_PALETTE}

    # -- state -----------------------------------------------------------

    def reset(self) -> None:
        self.source: Path | None = None
        self.original_name: str = ""
        self.width = 0
        self.height = 0
        self.grey: np.ndarray | None = None
        self.line_mask: np.ndarray | None = None
        # Page-scoped: line extraction, on or off for this page (ROADMAP G5).
        self.extract_lines = False
        # Extractor output, computed lazily by `structural_lines`, and its
        # binarised mask, which is what trapped-ball reads.
        self._structural_lines: np.ndarray | None = None
        self._structural: np.ndarray | None = None
        self.panels: list[PanelState] = []
        self.protected: list[list[tuple[int, int]]] = []
        # Tracked apart from `self.protected` because a page with no bubbles
        # on it is a legitimate outcome of pressing the button, not a step
        # that never ran.
        self._bubbles_done = False
        self._zones_done = False
        self._planes_done = False
        # The page as it stood before each of the last merges, cuts and plane
        # changes, oldest first: per edit, (panel, its label map or None when
        # the zones did not move, its planes) for every panel it touched.
        self._undo: list[list[tuple[int, np.ndarray | None, dict[int, int]]]] = []
        # Which page of the project is open.
        self.page_id: int | None = None
        self.page_uid = ""

    def _require_page(self) -> None:
        if self.line_mask is None:
            raise StepError("upload_first")

    # -- 1. upload -------------------------------------------------------

    def load_page(self, path: str | Path, original_name: str = "") -> None:
        """Add a page to the project and open it.

        The page that was open stays in the project as it was left.
        """
        with self.lock:
            # Read before a folder exists for it: a file that is not an image
            # must not leave an empty page in the list.
            line_mask, grey = load_line_art(path)
            page_id, source = project.new_page(self.workdir, Path(path))
            self.reset()
            self.page_id = page_id
            self.page_uid = str(uuid.uuid4())
            self.source = source
            self.original_name = original_name or Path(path).name
            self.line_mask = line_mask
            self.grey = grey
            self.height, self.width = line_mask.shape
            self._save()

    def open_page(self, page_id: int) -> None:
        """Open another page of the project, exactly as it was left."""
        with self.lock:
            if page_id not in self._pages:
                raise StepError("page_missing", page=page_id)
            try:
                project.open_page(self, page_id)
            except (OSError, ValueError) as exc:
                raise StepError("page_unreadable", page=page_id, detail=str(exc)) from exc
            project.save_project(self)

    def delete_page(self) -> None:
        """Delete the open page, then open the newest one left.

        Only the page goes. The book settings and every other page
        stay, because they belong to the book.
        """
        with self.lock:
            self._require_page()
            project.delete_page(self.workdir, self.page_id)
            del self._pages[self.page_id]
            self.reset()
            for page_id in sorted(self._pages, reverse=True):
                try:
                    project.open_page(self, page_id)
                    break
                except (OSError, ValueError):
                    continue
            project.save_project(self)

    def _save(self, maps=()) -> None:
        """Write the open page and the project settings (SPEC 4).

        Called by every method that changes either, before it returns.
        `maps` names the panels whose zone maps changed, or "all".
        """
        if self.page_id is not None:
            record = project.save_page(self, maps)
            self._pages[self.page_id] = {"name": record["name"], "stage": project.stage(record)}
        project.save_project(self)

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
            self._save()
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
                raise StepError("panels_first")
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
            self._save()
            return self.protected

    def skip_bubbles(self) -> list[list[tuple[int, int]]]:
        """Say there are no balloons on this page, without looking for any.

        Professionals ink first and letter afterwards, so the page that
        reaches Luikki often has no balloon on it at all — the first tester's
        did not. Detection would answer the same empty list after loading 161
        megabytes of weights and reading the whole page; this says it in one
        call. The step still *ran*: `_bubbles_done` is what step 4 waits on,
        and an empty `protected` is a legitimate outcome of pressing either
        button.
        """
        with self.lock:
            self._require_page()
            if not self.panels:
                raise StepError("panels_first")
            self.protected = []
            self._invalidate_from_panels()
            self._bubbles_done = True
            self._save()
            return self.protected

    # -- 2b/3b. the artist's corrections ---------------------------------
    #
    # Detection proposes geometry; these accept the artist's version of it.
    # Every one of them replaces a whole polygon rather than describing an
    # edit: dragging a corner, inserting one on an edge and deleting one are
    # the same call, which keeps the interaction on the client where the
    # pointer is and leaves the server holding only what is true of the
    # result.

    def _clean_polygon(self, polygon) -> list[tuple[int, int]]:
        """A polygon the rest of the pipeline can rasterise, or an error.

        Clamped to the page because a corner dragged past the edge is a
        corner the artist meant to put at the edge, not a mistake to refuse.
        """
        cleaned: list[tuple[int, ...]] = []
        for point in polygon:
            x = max(0, min(self.width - 1, int(point[0])))
            y = max(0, min(self.height - 1, int(point[1])))
            # A node may carry the tangent the artist pulled out of it. It is
            # not clamped: a handle reaching off the page is how a curve
            # bulges against the edge, and it draws nothing by itself.
            node = (x, y, int(point[2]), int(point[3])) if len(point) > 2 else (x, y)
            if not cleaned or cleaned[-1][:2] != (x, y):
                cleaned.append(node)
        if len(cleaned) > 1 and cleaned[0][:2] == cleaned[-1][:2]:
            cleaned.pop()
        if len(cleaned) < 3:
            raise StepError("corners_too_few")
        return cleaned

    def _require_panel_stage(self) -> None:
        self._require_page()
        if not self.panels:
            raise StepError("panels_first")
        if self._zones_done:
            raise StepError("panels_closed")

    def _require_bubble_stage(self) -> None:
        self._require_page()
        if not self._bubbles_done:
            raise StepError("bubbles_first")
        if self._zones_done:
            raise StepError("bubbles_closed")

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
                polygon=flatten_polygon(panel.polygon),
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
        raise StepError("panel_missing", number=order + 1)

    def set_panel_polygon(self, order: int, polygon) -> PanelState:
        with self.lock:
            self._require_panel_stage()
            panel = self._panel_for(order)
            panel.polygon = self._clean_polygon(polygon)
            self._fit_box(panel)
            self._reorder_panels()
            self._invalidate_from_panels()
            self._save()
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
                polygon=self._clean_polygon(polygon),
            )
            self._fit_box(panel)
            self.panels.append(panel)
            self._reorder_panels()
            self._invalidate_from_panels()
            self._save()
            return panel

    def delete_panel(self, order: int) -> None:
        with self.lock:
            self._require_panel_stage()
            panel = self._panel_for(order)
            if len(self.panels) == 1:
                raise StepError("last_panel")
            self.panels.remove(panel)
            self._reorder_panels()
            self._invalidate_from_panels()
            self._save()

    @staticmethod
    def _fit_box(panel: PanelState) -> None:
        """The crop box follows the outline. `panels.Panel` keeps both for the
        same reason: the polygon says which pixels are the panel's, the box
        says where to cut the page."""
        drawn = flatten_polygon(panel.polygon)
        xs = [x for x, _ in drawn]
        ys = [y for _, y in drawn]
        panel.x, panel.y = min(xs), min(ys)
        panel.width = max(xs) - panel.x + 1
        panel.height = max(ys) - panel.y + 1

    def set_bubble(self, index: int, polygon) -> list[tuple[int, int]]:
        with self.lock:
            self._require_bubble_stage()
            self._require_bubble_index(index)
            self.protected[index] = self._clean_polygon(polygon)
            self._invalidate_from_panels()
            self._save()
            return self.protected[index]

    def add_bubble(self, polygon) -> int:
        with self.lock:
            self._require_bubble_stage()
            self.protected.append(self._clean_polygon(polygon))
            self._invalidate_from_panels()
            self._save()
            return len(self.protected) - 1

    def delete_bubble(self, index: int) -> None:
        with self.lock:
            self._require_bubble_stage()
            self._require_bubble_index(index)
            del self.protected[index]
            self._invalidate_from_panels()
            self._save()

    def _require_bubble_index(self, index: int) -> None:
        if not 0 <= index < len(self.protected):
            raise StepError("bubble_missing", number=index + 1)

    # -- 4. segment zones ------------------------------------------------

    def segment_zones(
        self, leak_gap: float | None = None, extract_lines: bool | None = None
    ) -> list[PanelState]:
        """Cut every panel into zones. ``leak_gap`` tunes the audit below;
        ``extract_lines`` says whether this page's zones are cut from its ink
        as drawn or from MangaLineExtraction's lines (ROADMAP G5).

        The default was measured on one artist's ink, and the whole point of
        §1.3 is that this threshold is style-sensitive — so it is a knob the
        artist turns rather than a constant they inherit. Setting it here keeps
        it for the rest of the book.
        """
        # Checked before anything else: a bad number is wrong whatever state
        # the page is in, and saying so beats reporting the step it blocked.
        if leak_gap is not None and not 0.0 <= leak_gap <= 1.0:
            raise StepError("gap_share")

        with self.lock:
            self._require_page()
            if not self.panels:
                raise StepError("panels_first")
            if leak_gap is not None:
                self.leak_gap = leak_gap
            if extract_lines is not None and extract_lines != self.extract_lines:
                self.extract_lines = extract_lines
                self._structural_lines = None
                self._structural = None

            segmenter = LineFillerSegmenter()
            # The bar's total is fixed before the first tick. Costs are copied
            # so what this run learns cannot move the total under it.
            cost = dict(self._pass_cost)
            ball_passes = len(segmenter.radii) + 1
            per_megapixel = (
                ball_passes * cost["ball"] + cost["merge"] + cost["audit"] + cost["expand"]
            )
            page_megapixels = self.width * self.height / 1e6
            extracting = self._structural_lines is None
            total = (page_megapixels * cost["extract"] if extracting else 0.0) + sum(
                _megapixels(panel) * per_megapixel for panel in self.panels
            )
            # pass -> [seconds, megapixels], what this run actually took.
            measured = {name: [0.0, 0.0] for name in cost}

            def spent(name: str, seconds: float, megapixels: float) -> None:
                measured[name][0] += seconds
                measured[name][1] += megapixels

            # Stop (`POST /api/cancel`) lands between two passes. Every map is
            # computed before any is written, so a stopped run leaves the page
            # exactly as it was before the press: its zones and its planes.
            try:
                with self.progress.run(total, cancellable=True) as progress:
                    if extracting:
                        progress.at("extract")
                        started = time.perf_counter()
                        structural = self.structural_mask(
                            progress=lambda done, count: progress.tick(
                                page_megapixels * cost["extract"] / count
                            )
                        )
                        spent("extract", time.perf_counter() - started, page_megapixels)
                    else:
                        structural = self.structural_mask()

                    results = []
                    for number, panel in enumerate(self.panels, start=1):
                        progress.at("segment", number, len(self.panels))
                        results.append(
                            self._segment_panel(
                                panel, segmenter, structural, cost, progress, spent
                            )
                        )
            except Cancelled:
                raise StepError("cancelled") from None

            for panel, (label_map, orphans) in zip(self.panels, results):
                panel.label_map = label_map
                panel.planes = {}
                panel.depth_groups = None
                panel.orphans = orphans

            self._learn(measured)
            self._assign_colours()
            self._undo = []
            self._zones_done = True
            self._planes_done = False
            self._save(maps="all")
            return self.panels

    def _segment_panel(
        self, panel: PanelState, segmenter, structural, cost, progress, spent
    ) -> tuple[np.ndarray, int]:
        """One panel through every pass of step 4: its label map and orphans.

        Writes nothing to `panel`, so a run stopped halfway leaves no panel
        half-cut.
        """
        megapixels = _megapixels(panel)
        window = (
            slice(panel.y, panel.y + panel.height),
            slice(panel.x, panel.x + panel.width),
        )
        blocked = self._blocked_for(panel)
        labels = segmenter.segment(
            structural[window],
            protected=blocked,
            # LineFiller's last pass is its merge; the others are balls.
            progress=lambda done, passes, megapixels=megapixels: progress.tick(
                megapixels * cost["merge" if done == passes else "ball"]
            ),
        )
        timing = segmenter.last_timing
        spent("ball", timing["ball_seconds"] / (len(segmenter.radii) + 1), megapixels)
        spent("merge", timing["merge_seconds"], megapixels)

        started = time.perf_counter()
        # The audit pass, §1.3. LineFiller merges hard enough to take a
        # zone straight through a hole in a line; this puts back the
        # splits whose border turns out to be a line rather than a
        # tunnel. It only ever divides what came back, never re-draws
        # it, so nothing downstream sees a zone move.
        labels = split_open_borders(
            labels,
            structural[window],
            protected=blocked,
            params=LeakParams(max_open_share=self.leak_gap),
        )
        raw = self.line_mask[window]
        # The crumbs, §1.4. Before expansion, or "80% of this border is
        # one neighbour" would be measured on shapes already fused
        # under the strokes. The panel's own area is the denominator:
        # a crumb is a share of the panel, never a count of pixels.
        labels = absorb_micro_zones(
            labels,
            structural[window],
            raw,
            panel.width * panel.height,
            protected=blocked,
        )
        # Which zones are the artist's own spot black, measured here
        # and punched below. Measured on the labels the segmenter
        # returned, because after expansion every sliver that grew
        # under a stroke looks black too.
        doomed = inked_zones(labels, raw)
        spent("audit", time.perf_counter() - started, megapixels)
        progress.tick(megapixels * cost["audit"])

        started = time.perf_counter()
        # Flats must meet underneath the ink, or every line leaves a
        # white seam in the export (§10, anti-aliased line art). This
        # one takes the *raw* ink, not the structural lines: the layer
        # the artist drops on top is their real ink, so that is what
        # the flats have to reach under.
        expanded = expand_under_lines(labels, raw, protected=blocked)
        # Frozen now, in pixels. `doomed` is indexed by label, and the
        # pass below moves labels: read through it afterwards and it
        # would point at somewhere else entirely.
        spot_black = doomed[expanded]
        # The rest of the residue. Zones are cut on the *structural*
        # lines but expansion above only reaches under *real* ink, so
        # every pixel the extractor called line and the artist's ink
        # does not cover was left with no zone at all — no segment to
        # click, no colour, transparent in every PSD layer, white on
        # the flattened page. Nothing covers those pixels, so they get
        # the nearest label.
        expanded = expand_under_lines(
            expanded, ~spot_black, protected=blocked
        )
        # Now the hole. Left in place through expansion the spot black
        # was a wall the neighbours stopped against; taken out before
        # it, they would have flooded it and met in its middle, which
        # draws zones straight across the stroke separating them.
        expanded[spot_black] = UNASSIGNED
        # §3's exhaustiveness invariant, with the two exceptions as the
        # excluded set. Reported, never enforced: a panel that fails it still
        # colours, and the number is what says so.
        orphans = int(
            check_coverage(expanded, spot_black, protected=blocked)["uncovered_pixels"]
        )
        spent("expand", time.perf_counter() - started, megapixels)
        progress.tick(megapixels * cost["expand"])
        return expanded, orphans

    def _learn(self, measured: dict[str, list[float]]) -> None:
        """Fold what a run took into the pass costs, half old and half new.

        So the next bar's steps are sized for this machine — a GPU makes
        extraction nearly free — without one odd page deciding them alone.
        """
        for name, (seconds, megapixels) in measured.items():
            if megapixels > 0:
                self._pass_cost[name] = (
                    0.5 * self._pass_cost[name] + 0.5 * seconds / megapixels
                )

    # -- 4b. the artist's corrections to the zones -----------------------
    #
    # Trapped-ball cuts a panel into zones from the ink it can see, and the
    # ink is not always closed. So it leaks a garment into the background
    # through a gap, and it splits what the eye reads as one thing — a pair of
    # trousers, a glass, a pair of shoes — into forty scraps.
    #
    # Merge and cut are the two corrections that follow. They stay open over
    # the planes: a merged zone keeps the plane of the zone that survives, and
    # every piece of a cut keeps the plane of the zone it came from.
    #
    # They are **undoable**. The first tester lost a forty-piece merge to one
    # cut and had to rebuild it by hand, so `_undo` keeps the last few label
    # maps and `undo_zones` puts one back. A snapshot is a state this panel was
    # in, not a second opinion about what the page is, and nothing downstream
    # ever reads one. Pressing Segment zones again still starts the page over,
    # and empties the stack.

    def _require_zone_stage(self) -> None:
        self._require_page()
        if not self._zones_done:
            raise StepError("zones_first")

    def zone_at(self, x: int, y: int) -> tuple[int, int] | None:
        """The (panel, label) under a page-space point, or None.

        Read off the label map: bounds overlap for interlocking zones, and a
        press has to resolve to the zone the artist actually pointed at.
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


    def _remember_zones(self, panel: PanelState) -> None:
        """Keep this panel's zones as they are, so the next edit can be undone.

        Called by the mutators once they know they will write — a refused merge
        or a cut that separates nothing must not push a state nothing changed.
        The planes travel with the zones; the colours do not, since they are
        given again after every edit.
        """
        assert panel.label_map is not None
        self._undo.append([(panel.order, panel.label_map.copy(), dict(panel.planes))])
        del self._undo[:-_UNDO_DEPTH]

    def _assign_colours(self) -> None:
        """Give every zone of the page one of the eight fake flats.

        Again after every change to the zones: a merge can put two zones of
        one colour side by side, and the guarantee — two touching zones never
        alike — is over the whole page, not over the panel that moved.
        """
        cut = [panel for panel in self.panels if panel.label_map is not None]
        colours = assign_flat_colours(
            (self.width, self.height), [(panel.x, panel.y, panel.label_map) for panel in cut]
        )
        for panel, assignments in zip(cut, colours):
            panel.assignments = assignments

    def undo_zones(self) -> dict:
        """Put back the page as it was before the last merge, cut or plane change."""
        with self.lock:
            self._require_zone_stage()
            if not self._undo:
                raise StepError("nothing_to_undo")
            moved = []
            for order, label_map, planes in self._undo.pop():
                panel = self._panel_for(order)
                panel.planes = planes
                if label_map is not None:
                    panel.label_map = label_map
                    moved.append(order)
            if moved:
                self._assign_colours()
            self._save(maps=moved)
            return {"panel": order, "left": len(self._undo)}

    def merge_zones(self, panel_order: int, labels) -> dict:
        """Make several zones one zone. One address, one colour, one click.

        The largest keeps its label, so the zone's anchor stays in the body of
        the trousers rather than in a 300px scrap.

        Zones need not touch: the panes of a glass and a shirt split by an arm
        are one thing to colour and one thing here. A zone is a set of pixels,
        not a blob. What they must share is a panel — labels are panel-local,
        and the same shirt in the next panel is another zone.
        """
        with self.lock:
            self._require_zone_stage()
            panel = self._panel_for(panel_order)
            if panel.label_map is None:
                raise StepError("panel_no_zones", panel=panel_order + 1)

            wanted = {int(label) for label in labels}
            present = {
                label: int(area)
                for label, area in zip(*np.unique(panel.label_map, return_counts=True))
                if int(label) in wanted and int(label) != UNASSIGNED
            }
            if len(present) < 2:
                raise StepError("merge_too_few")

            survivor = max(present, key=lambda label: present[label])
            others = [label for label in present if label != survivor]
            self._remember_zones(panel)
            panel.label_map[np.isin(panel.label_map, others)] = survivor
            # The merged zone votes again on the depth under all of it, unless
            # the artist called it a character, which no depth says.
            kept = panel.planes.get(survivor)
            for label in others:
                panel.planes.pop(label, None)
            if kept != CHARACTER:
                self._revote(panel, [survivor])
            self._assign_colours()
            self._save(maps=[panel.order])
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
                raise StepError("panel_no_zones", panel=panel_order + 1)

            mask = panel.label_map == int(label)
            if not mask.any():
                raise StepError("zone_missing", zone=int(label), panel=panel_order + 1)

            points = np.array(
                [[int(x) - panel.x, int(y) - panel.y] for x, y in stroke], np.int32
            )
            if len(points) < 2:
                raise StepError("cut_too_short")

            # Both ends run on past where the hand stopped. A stroke has to
            # leave the zone on both sides to separate it, and stopping a few
            # pixels short is the commonest way a cut fails — while the
            # overshoot itself can do no harm, since the wall is only ever
            # applied inside this zone's own mask.
            points = _overshoot(points, max(mask.shape) // 20 + 10)

            wall = np.zeros(mask.shape, np.uint8)
            cv2.polylines(wall, [points.reshape(-1, 1, 2)], False, 1, max(1, width))
            remaining = mask & (wall == 0)

            # **A cut divides only what the stroke crossed.** A zone the artist
            # merged is several disconnected pieces already, so reading the cut
            # off the pieces that remain handed every one of them a label of
            # its own and undid the merge — the first tester lost a forty-piece
            # garment to one stroke. What the stroke crossed is knowable: the
            # pieces before the wall, against the pieces after it. A piece that
            # came through whole keeps the zone's label, whatever else happened
            # elsewhere on the page.
            _, whole = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
            count, pieces = cv2.connectedComponents(
                remaining.astype(np.uint8), connectivity=8
            )

            # Which piece each surviving fragment came from, and how big it is,
            # in two passes rather than one mask per fragment.
            fragments = pieces[remaining]
            came_from = np.zeros(count, np.int32)
            came_from[fragments] = whole[remaining]
            areas = np.bincount(fragments, minlength=count)

            broken: dict[int, list[int]] = {}
            for fragment in range(1, count):
                broken.setdefault(int(came_from[fragment]), []).append(fragment)
            broken = {
                piece: parts for piece, parts in broken.items() if len(parts) > 1
            }
            if not broken:
                raise StepError("cut_no_split")

            self._remember_zones(panel)

            # In each piece the stroke broke, the largest part keeps the label,
            # for the reason the largest zone survives a merge: the anchor
            # stays in the body of the trousers rather than in a scrap.
            next_label = int(panel.label_map.max()) + 1
            made = [int(label)]
            for parts in broken.values():
                for fragment in sorted(parts, key=lambda part: -areas[part])[1:]:
                    panel.label_map[pieces == fragment] = next_label
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

            # Every piece votes again on the depth under it: the plane belongs
            # to the pixels, not to the zone they came from. A character stays
            # one: only the artist says so, and no depth does.
            parent = int(label)
            if panel.planes.get(parent) == CHARACTER:
                for piece in made[1:]:
                    panel.planes[piece] = CHARACTER
            else:
                self._revote(panel, made)
            self._assign_colours()
            self._save(maps=[panel.order])
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
                raise StepError("panel_no_zones", panel=panel_order + 1)
            mask = panel.label_map == int(label)
            rows, cols = np.nonzero(mask)
            if not len(rows):
                raise StepError("zone_missing", zone=int(label), panel=panel_order + 1)

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

    def structural_mask(
        self, progress: Callable[[int, int], None] | None = None
    ) -> np.ndarray:
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
            # Plus the thick strokes the extractor hollows out (`thick_ink`).
            self._structural = binarise_lines(self.structural_lines(progress)) | thick_ink(
                self.line_mask
            )
        return self._structural

    def structural_lines(
        self, progress: Callable[[int, int], None] | None = None
    ) -> np.ndarray:
        """The extractor's own output, greyscale, before any threshold.

        `structural_mask` binarises it for trapped-ball; the page keeps it as
        it comes (`project.save_page`), so reopening skips the extractor.

        Shares the cache with `structural_mask`: one extractor pass per page.
        """
        self._require_page()
        if self._structural_lines is None:
            # An extractor written before the progress bar takes no
            # `progress`. It still works; the bar just learns nothing from it.
            takes_progress = "progress" in inspect.signature(self.extractor.extract).parameters
            if progress is not None and takes_progress:
                result = self.extractor.extract(self.grey, progress=progress)
            else:
                result = self.extractor.extract(self.grey)
            self._structural_lines = result.lines
        return self._structural_lines

    def _blocked_for(self, panel: PanelState) -> np.ndarray:
        """Protected areas plus everything outside the panel polygon.

        Both come back unlabelled, which is the whole of what "protected"
        means: never coloured.
        """
        protected = rasterize_protected_for_panel(
            [flatten_polygon(polygon) for polygon in self.protected],
            panel.x,
            panel.y,
            panel.width,
            panel.height,
        )
        inside = rasterize_protected_for_panel(
            [flatten_polygon(panel.polygon)], panel.x, panel.y, panel.width, panel.height
        )
        return protected | ~inside

    # -- 5. planes (may be skipped) --------------------------------------
    #
    # Depth is read panel by panel and votes: each zone takes the plane that
    # dominates under it, so the boundaries stay the ink's (§G2). The artist
    # then moves zones between planes, and is the only one who says
    # "character".

    def detect_planes(self) -> dict[str, int]:
        with self.lock:
            self._require_zone_stage()
            if self.depth_estimator is None:
                self.depth_estimator = DepthEstimator()
            reading = [panel for panel in self.panels if panel.label_map is not None]
            # Every panel is read before any is written, so a stopped run
            # leaves the page as it was before the press.
            found: list[dict[int, int]] = []
            try:
                with self.progress.run(len(reading), cancellable=True) as progress:
                    for number, panel in enumerate(reading, start=1):
                        progress.at("depth", number, len(reading))
                        window = (
                            slice(panel.y, panel.y + panel.height),
                            slice(panel.x, panel.x + panel.width),
                        )
                        inside = rasterize_protected_for_panel(
                            [flatten_polygon(panel.polygon)],
                            panel.x,
                            panel.y,
                            panel.width,
                            panel.height,
                        )
                        found.append(
                            panel_planes(
                                self.depth_estimator,
                                self.grey[window],
                                panel.label_map,
                                inside,
                            )
                        )
                        progress.tick(1)
            except Cancelled:
                raise StepError("cancelled") from None

            for panel, (planes, groups) in zip(reading, found):
                panel.planes = planes
                panel.depth_groups = groups
            self._planes_done = True
            # A snapshot from before the planes holds none: undoing across this
            # press would put back zones with no plane to show.
            self._undo = []
            self._save(maps="all")
            return self.plane_counts()

    def set_planes(self, zones, plane: int) -> dict[str, int]:
        """Put zones on one plane: the artist's correction, or "character"."""
        with self.lock:
            self._require_zone_stage()
            if not self._planes_done:
                raise StepError("planes_first")
            if plane not in PLANES:
                raise StepError("plane_unknown", plane=plane)
            for order, label in zones:
                if int(label) not in self._panel_for(int(order)).assignments:
                    raise StepError("zone_missing", zone=int(label), panel=int(order) + 1)
            touched = sorted({int(order) for order, _ in zones})
            self._undo.append(
                [(order, None, dict(self._panel_for(order).planes)) for order in touched]
            )
            del self._undo[:-_UNDO_DEPTH]
            for order, label in zones:
                self._panel_for(int(order)).planes[int(label)] = plane
            self._save()
            return self.plane_counts()

    def _revote(self, panel: PanelState, labels) -> None:
        """These zones' planes, voted again on the depth kept for the panel.

        Before the planes exist there is nothing to vote on; a page saved
        before the depth was kept has none either, and its zones keep the
        plane they had.
        """
        if not self._planes_done or panel.depth_groups is None or panel.label_map is None:
            return
        voted = planes_from(panel.label_map, panel.depth_groups)
        for label in labels:
            if int(label) in voted:
                panel.planes[int(label)] = voted[int(label)]

    def plane_counts(self) -> dict[str, int]:
        counts = {str(plane): 0 for plane in PLANES}
        for panel in self.panels:
            for plane in panel.planes.values():
                counts[str(plane)] += 1
        return counts

    def plane_of(self, panel_order: int, label: int) -> int | None:
        return self._panel_for(panel_order).planes.get(int(label))

    # -- 6. export -------------------------------------------------------

    def _panel_flats(self) -> list[PanelFlats]:
        return [
            PanelFlats(
                order=panel.order,
                x=panel.x,
                y=panel.y,
                label_map=panel.label_map,
                assignments=panel.assignments,
                planes=panel.planes if self._planes_done else None,
            )
            for panel in self.panels
            if panel.label_map is not None
        ]

    def _balloon_masks(self) -> list[np.ndarray]:
        masks = []
        for polygon in self.protected:
            mask = np.zeros((self.height, self.width), np.uint8)
            cv2.fillPoly(mask, [np.array(flatten_polygon(polygon), np.int32)], 1)
            masks.append(mask.astype(bool))
        return masks

    def export_psd(
        self,
        path: str | Path | None = None,
        granularity: str | None = None,
        support_grey: bool | None = None,
        names: dict[str, str] | None = None,
    ) -> Path:
        with self.lock:
            self._require_zone_stage()
            if granularity is not None:
                if granularity not in GRANULARITIES:
                    raise StepError("granularity_unknown", value=granularity)
                self.granularity = granularity
                project.save_project(self)
            if support_grey is not None and support_grey != self.support_grey:
                self.support_grey = support_grey
                project.save_project(self)
            target = Path(path) if path else self.workdir / f"{Path(self.original_name).stem}_flats.psd"
            return write_psd(
                target,
                (self.width, self.height),
                self._panel_flats(),
                self.palette_by_id,
                self.granularity,
                line_mask=self.line_mask if self.support_grey else None,
                support_grey=self.support_grey,
                balloons=self._balloon_masks(),
                names=names,
            )

    def flats_rgba(self) -> np.ndarray:
        """The fake flats as they land in the PSD. Also what step 4 shows: the
        zone map, in the colours the export will carry."""
        with self.lock:
            return flats_preview(
                (self.width, self.height), self._panel_flats(), self.palette_by_id
            )

    def zones_rgba(self) -> np.ndarray:
        return self.flats_rgba()

    def planes_rgba(self, tints: dict[int, tuple[int, int, int]] | None = None) -> np.ndarray:
        """The planes first, the zones inside them (tester 3 was frightened by
        every zone at once): one tint per plane, and each zone's edge drawn a
        shade darker within it."""
        tints = tints or PLANE_TINTS
        with self.lock:
            canvas = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            for panel in self.panels:
                labels = panel.label_map
                if labels is None:
                    continue
                table = np.zeros((int(labels.max()) + 1, 4), dtype=np.uint8)
                for label, plane in panel.planes.items():
                    if 0 < label < table.shape[0]:
                        table[label] = (*tints[plane], 255)
                rows = min(labels.shape[0], self.height - panel.y)
                cols = min(labels.shape[1], self.width - panel.x)
                cropped = labels[:rows, :cols]
                patch = table[cropped]
                edge = np.zeros(cropped.shape, bool)
                edge[:, 1:] |= cropped[:, 1:] != cropped[:, :-1]
                edge[1:, :] |= cropped[1:, :] != cropped[:-1, :]
                patch[edge & (cropped != UNASSIGNED), :3] //= 2
                window = canvas[panel.y : panel.y + rows, panel.x : panel.x + cols]
                painted = patch[:, :, 3] > 0
                window[painted] = patch[painted]
            return canvas

    # -- bookkeeping -----------------------------------------------------

    def _invalidate_from_panels(self) -> None:
        for panel in self.panels:
            panel.label_map = None
            panel.assignments = {}
            panel.planes = {}
            panel.depth_groups = None
        self._undo = []
        self._zones_done = False
        self._planes_done = False

    def state(self) -> dict:
        with self.lock:
            flats = self._panel_flats()
            return {
                "account": {"email": self.account.email if self.account else None},
                "page_id": self.page_id,
                # Every page of the project, oldest first: the page list.
                "pages": [
                    {"id": page_id, **summary} for page_id, summary in sorted(self._pages.items())
                ],
                "page": None
                if self.line_mask is None
                else {
                    "name": self.original_name,
                    "width": self.width,
                    "height": self.height,
                },
                "panels": [
                    {
                        "order": p.order,
                        "polygon": p.polygon,
                        "zones": p.zone_count,
                        "orphans": p.orphans,
                    }
                    for p in self.panels
                ],
                "protected": self.protected,
                # Which geometry the artist may still correct. Detection
                # proposes it, they settle it, and once the zones are cut from
                # it the shape is no longer a proposal.
                "editable": {
                    "panels": bool(self.panels) and not self._zones_done,
                    "bubbles": self._bubbles_done and not self._zones_done,
                    "zones": self._zones_done,
                    "planes": self._planes_done,
                },
                # zones per plane, keyed by plane.
                "planes": {"counts": self.plane_counts()},
                "extract_lines": self.extract_lines,
                "leak_gap": self.leak_gap,
                # How many merges and cuts can still be taken back.
                "undo": len(self._undo),
                "export": {
                    "granularity": self.granularity,
                    "support_grey": self.support_grey,
                    "layers": {
                        name: layer_count(flats, self.palette_by_id, name, len(self.protected))
                        for name in GRANULARITIES
                    },
                },
                "done": {
                    "page": self.line_mask is not None,
                    "panels": bool(self.panels),
                    "bubbles": self._bubbles_done,
                    "zones": self._zones_done,
                    "planes": self._planes_done,
                },
            }
