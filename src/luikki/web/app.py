"""The five buttons, over HTTP.

One route per button and nothing else — rule 3: a route with no button is a
feature that does not exist, and the inverse is what this file exists to
prevent. Every endpoint below is reachable from `static/app.js`.

Endpoints are plain `def`, not `async def`, deliberately: segmentation and
generation are seconds of CPU or GPU work, and FastAPI runs sync handlers in a
threadpool instead of stalling the event loop with them.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from ..colour.extract import EmptyImageError
from ..colour.references import UnknownKind
from ..colour.snap import SNAP_MAX_DELTA
from pydantic import BaseModel

from .session import Session, StepError


class Shape(BaseModel):
    """A polygon in page space, as the artist left it on screen."""

    polygon: list[tuple[int, int]]


class Stroke(BaseModel):
    """A path in page space — a sweep that selects, or a cut that separates."""

    points: list[tuple[int, int]]


class Merge(BaseModel):
    """The zones of one panel that are one thing."""

    panel: int
    labels: list[int]


class Cut(BaseModel):
    """One zone, and the line the ink was missing."""

    panel: int
    label: int
    stroke: list[tuple[int, int]]


class Colour(BaseModel):
    """One colour, as the picker left it."""

    rgb: tuple[int, int, int]


class Pick(BaseModel):
    """One of a reference's extracted colours, chosen for the palette."""

    reference_id: int
    rgb: tuple[int, int, int]

_STATIC = Path(__file__).parent / "static"


class _Fresh(StaticFiles):
    """`StaticFiles` that never lets the browser reuse a file without asking."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-store"
        return response

def _build_proposer():
    """`LUIKKI_PROPOSER=cobra` swaps the model in without a code edit.

    `remote` is the same model on a GPU elsewhere (`colour/remote.py`).
    Anything else — including unset — is the deterministic distinct-colour
    proposer, which needs no GPU and no weights. Read at call time, not import
    time, so `luikki serve --proposer cobra` works whatever the import
    order turns out to be.
    """
    choice = os.environ.get("LUIKKI_PROPOSER", "distinct")
    if choice == "remote":
        from ..colour.remote import RemoteProposer

        return RemoteProposer()
    if choice != "cobra":
        from ..colour.proposer import DistinctColourProposer

        return DistinctColourProposer()

    from ..colour.cobra import CobraProposer

    return CobraProposer()


def _build_extractor():
    """`LUIKKI_EXTRACTOR=raw` turns the line extractor off.

    The default is MangaLineExtraction, which is what §2.2's A/B chose: raw ink
    hands trapped-ball every stroke edge and every spot black as a zone. `raw`
    exists for the case where the artist's ink layer really is already a clean
    line image, and for tests that must not load 172 MB of weights.
    """
    if os.environ.get("LUIKKI_EXTRACTOR", "manga") == "raw":
        from ..extract.passthrough import PassthroughExtractor

        return PassthroughExtractor()
    return None  # Session picks MangaLineExtraction on the best device.


def create_app(
    workdir: str | Path | None = None,
    proposer=None,
    extractor=None,
) -> FastAPI:
    app = FastAPI(title="Luikki")
    workdir = Path(workdir) if workdir else Path(tempfile.gettempdir()) / "luikki"
    session = Session(
        workdir,
        proposer=proposer or _build_proposer(),
        extractor=extractor or _build_extractor(),
    )
    app.state.session = session

    def _png(rgba: np.ndarray) -> Response:
        buffer = io.BytesIO()
        Image.fromarray(rgba).save(buffer, format="PNG")
        return Response(buffer.getvalue(), media_type="image/png")

    @app.exception_handler(StepError)
    def _step_error(_request, exc: StepError):
        return JSONResponse({"error": str(exc)}, status_code=409)

    # -- state -----------------------------------------------------------

    @app.get("/api/state")
    def state():
        return session.state()

    @app.get("/api/progress")
    def progress():
        """How far the step in flight has got. Never waits for it: the step
        holds the session lock for its whole run, and this route answers
        while it does."""
        return session.progress.snapshot()

    # -- 1. pages --------------------------------------------------------

    @app.post("/api/page")
    def upload_page(file: UploadFile):
        """Adds a page to the project and opens it."""
        name = file.filename or "page.png"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(name).suffix, dir=session.workdir
        ) as handle:
            shutil.copyfileobj(file.file, handle)
            staged = Path(handle.name)
        try:
            session.load_page(staged, original_name=name)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(400, f"could not read that image: {exc}") from exc
        finally:
            # The page folder keeps its own copy.
            staged.unlink(missing_ok=True)
        return session.state()

    @app.post("/api/pages/{page_id}/open")
    def open_page(page_id: int):
        session.open_page(page_id)
        return session.state()

    @app.delete("/api/page")
    def delete_page():
        """Deletes the open page and opens the newest one left."""
        session.delete_page()
        return session.state()

    @app.get("/api/page.png")
    def page_png():
        if session.grey is None:
            raise HTTPException(404, "no page loaded")
        return _png(session.grey)

    # -- 2/3. detection --------------------------------------------------

    @app.post("/api/panels")
    def detect_panels():
        session.detect_panels()
        return session.state()

    @app.post("/api/bubbles")
    def detect_bubbles():
        session.detect_bubbles()
        return session.state()

    # -- 2b/3b. corrections to the detected geometry ---------------------
    #
    # Detection is a proposal, and these are how the artist disagrees with it.
    # Every route takes a whole polygon: dragging a corner, adding one on an
    # edge and deleting one all arrive here as "this is the shape now", which
    # is the only description that cannot get out of step with what is drawn
    # on the artist's screen.

    @app.put("/api/panel/{order}")
    def set_panel(order: int, shape: Shape):
        session.set_panel_polygon(order, shape.polygon)
        return session.state()

    @app.post("/api/panel")
    def add_panel(shape: Shape):
        session.add_panel(shape.polygon)
        return session.state()

    @app.delete("/api/panel/{order}")
    def delete_panel(order: int):
        session.delete_panel(order)
        return session.state()

    @app.put("/api/bubble/{index}")
    def set_bubble(index: int, shape: Shape):
        session.set_bubble(index, shape.polygon)
        return session.state()

    @app.post("/api/bubble")
    def add_bubble(shape: Shape):
        session.add_bubble(shape.polygon)
        return session.state()

    @app.delete("/api/bubble/{index}")
    def delete_bubble(index: int):
        session.delete_bubble(index)
        return session.state()

    # -- 4. zones --------------------------------------------------------

    @app.post("/api/zones")
    def segment_zones(gap: float | None = None):
        """`gap` is §1.3's gap allowance, kept for the rest of the book."""
        session.segment_zones(leak_gap=gap)
        return session.state()

    @app.get("/api/lines.png")
    def lines_png():
        """What the extractor handed segmentation.

        Not a proposal raster — this is a deterministic pre-processing step,
        and being able to see it is how you tell "the segmenter is wrong" from
        "the extractor ate the linework" (rule 3: every stage boundary is
        inspectable).
        """
        if session.grey is None:
            raise HTTPException(404, "no page loaded")
        if session._structural is None:
            raise HTTPException(404, "lines not extracted yet")
        return _png(np.where(session._structural, 0, 255).astype(np.uint8))

    @app.get("/api/zones.png")
    def zones_png():
        if not session.state()["done"]["zones"]:
            raise HTTPException(404, "zones not segmented")
        return _png(session.zones_rgba())

    # -- 4b. correcting the zones ----------------------------------------
    #
    # Trapped-ball leaks a garment into the background through a gap in the
    # ink, and splits a pair of trousers into forty scraps. These are the two
    # corrections, and they are permanent: they happen at step 4, before a
    # single colour is proposed.

    @app.get("/api/zone")
    def zone_at(x: int, y: int):
        """The zone under a page-space point — what a press resolves to."""
        found = session.zone_at(x, y)
        if found is None:
            raise HTTPException(404, "no zone at that point")
        panel, label = found
        _, bounds = session.zone_mask_rgba(panel, label)
        return {"panel": panel, "label": label, "bounds": list(bounds)}

    @app.post("/api/zones/along")
    def zones_along(stroke: Stroke):
        """Every zone a sweep passed over. One request for the whole gesture."""
        found = session.zones_along(stroke.points)
        # The bounds travel with the zones: the browser draws each highlight
        # at its own box, and asking for them one at a time would undo the
        # point of answering a whole sweep in one request.
        boxes = {panel: session.zone_bounds(panel) for panel, _ in found}
        return {
            "zones": [
                {"panel": panel, "label": label, "bounds": list(boxes[panel][label])}
                for panel, label in found
            ]
        }

    @app.get("/api/zone/{panel}/{label}.png")
    def zone_png(panel: int, label: int):
        """One zone as a tinted overlay, cropped to its bounds.

        The bounds come back in the headers rather than in a second request:
        the browser needs both to draw it, and a selection of forty zones is
        forty of these.
        """
        rgba, bounds = session.zone_mask_rgba(panel, label)
        response = _png(rgba)
        response.headers["x-bounds"] = ",".join(str(edge) for edge in bounds)
        return response

    @app.post("/api/zones/merge")
    def merge_zones(merge: Merge):
        result = session.merge_zones(merge.panel, merge.labels)
        return {**session.state(), "result": result}

    @app.post("/api/zones/cut")
    def cut_zone(cut: Cut):
        result = session.cut_zone(cut.panel, cut.label, cut.stroke)
        return {**session.state(), "result": result}

    # -- palette / references --------------------------------------------

    @app.post("/api/reference")
    def upload_reference(file: UploadFile, kind: str = Form("sheet")):
        name = file.filename or "reference.png"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(name).suffix, dir=session.workdir
        ) as handle:
            shutil.copyfileobj(file.file, handle)
            staged = Path(handle.name)
        try:
            stored = session.add_reference(staged, original_name=name, kind=kind)
        except UnknownKind as exc:
            raise HTTPException(422, str(exc)) from exc
        except EmptyImageError as exc:
            raise HTTPException(422, f"no colours in that image: {exc}") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(422, f"could not read that image: {exc}") from exc
        finally:
            # The store keeps its own copy, so the upload never lingers.
            staged.unlink(missing_ok=True)
        # A finished page arrives as one file and is stored as several
        # references — itself, plus the panels big enough to be worth cutting
        # out. The artist pressed one button, so the answer says what actually
        # happened to it.
        return {
            **session.state(),
            "result": {
                "added": len(stored),
                "kind": stored[0].kind,
                "panels": sum(1 for r in stored if r.kind == "panel"),
            },
        }

    @app.delete("/api/reference/{reference_id}")
    def delete_reference(reference_id: int):
        if not session.remove_reference(reference_id):
            raise HTTPException(404, f"no reference {reference_id}")
        return session.state()

    @app.get("/api/reference/{reference_id}.png")
    def reference_thumbnail(reference_id: int):
        try:
            thumbnail = session.reference_store.thumbnail(reference_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        buffer = io.BytesIO()
        thumbnail.save(buffer, format="PNG")
        return Response(buffer.getvalue(), media_type="image/png")

    @app.post("/api/palette/image")
    def upload_palette(file: UploadFile):
        """A palette image: every colour in it, straight into the palette.

        The other door. A character sheet is a drawing whose colours are a
        proposal; a palette is the decision already made, so there is nothing
        to confirm. It is never shown to the proposer.
        """
        name = file.filename or "palette.png"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(name).suffix, dir=session.workdir
        ) as handle:
            shutil.copyfileobj(file.file, handle)
            staged = Path(handle.name)
        try:
            session.add_palette(staged, original_name=name)
        except EmptyImageError as exc:
            raise HTTPException(422, f"no colours in that image: {exc}") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(422, f"could not read that image: {exc}") from exc
        finally:
            staged.unlink(missing_ok=True)
        return session.state()

    @app.post("/api/palette")
    def include_colour(pick: Pick):
        """Take one of a reference's colours into the palette."""
        entry = session.include_candidate(pick.reference_id, pick.rgb)
        return {**session.state(), "entry_id": entry.id}

    @app.put("/api/palette/{entry_id}")
    def recolour(entry_id: int, colour: Colour):
        """Change a palette colour — and with it every zone holding that id.

        No re-segmentation and no invalidation: the flats raster and the PSD
        both resolve through the palette when they are asked for, so one row
        changing is the whole repaint (rule 1).
        """
        session.set_palette_colour(entry_id, colour.rgb)
        return session.state()

    @app.delete("/api/palette/{entry_id}")
    def drop_colour(entry_id: int):
        session.delete_palette_entry(entry_id)
        return session.state()

    # -- 5. flats --------------------------------------------------------

    @app.post("/api/flats")
    def generate_flats():
        try:
            result = session.generate_flats()
        except RuntimeError as exc:
            if isinstance(exc, StepError):
                raise
            # CobraUnavailable and friends: the artist needs the sentence, not
            # a traceback.
            raise HTTPException(503, str(exc)) from exc
        return {**session.state(), "result": result}

    @app.get("/api/flats.png")
    def flats_png():
        if not session.state()["done"]["flats"]:
            raise HTTPException(404, "flats not generated")
        return _png(session.flats_rgba())

    # -- 6. snap ---------------------------------------------------------

    def _segment_payload(segment):
        entry, distance = session.snap_suggestion(segment)
        return {
            "panel": segment.panel,
            "label": segment.label,
            "palette_entry_id": segment.palette_entry_id,
            "area": segment.area,
            "bounds": list(segment.bounds),
            "anchor": list(segment.anchor),
            "snapped": segment.snapped,
            "suggestion": None
            if entry is None
            else {
                "palette_entry_id": entry.id,
                "rgb": list(entry.rgb),
                # The number the old automatic snap decided on without showing
                # anyone. Above SNAP_MAX_DELTA it is a warning, not a veto.
                "delta": round(distance, 2),
                "within_threshold": distance <= SNAP_MAX_DELTA,
            },
        }

    @app.get("/api/segments")
    def segments(unsnapped: bool = False, limit: int = 0):
        """Every segment, worst suggestion first.

        Sorted by descending area so the artist meets the background before a
        300px speck: the ordering is the whole ergonomics of clicking through
        a page one zone at a time.
        """
        chosen = [s for s in session.segments if not (unsnapped and s.snapped)]
        chosen.sort(key=lambda s: -s.area)
        if limit:
            chosen = chosen[:limit]
        return {"count": len(chosen), "segments": [_segment_payload(s) for s in chosen]}

    @app.get("/api/segment")
    def segment_at(x: int, y: int):
        """The segment under a page-space point — what a click resolves to."""
        found = session.segment_at(x, y)
        if found is None:
            raise HTTPException(404, "no segment at that point")
        return _segment_payload(found)

    @app.post("/api/segment/{panel}/{label}/snap")
    def snap_segment(panel: int, label: int, entry_id: int | None = None):
        """Snap one segment. `entry_id` omitted takes the suggestion."""
        segment = session.snap_segment(panel, label, entry_id)
        return _segment_payload(segment)

    @app.post("/api/segment/{panel}/{label}/unsnap")
    def unsnap_segment(panel: int, label: int):
        return _segment_payload(session.unsnap_segment(panel, label))

    @app.get("/api/unsnapped.png")
    def unsnapped_png():
        """What step 6 has left to do, as a mask over the page.

        Flats show what the page currently resolves to; this shows which of it
        is still the machine's guess. Without it "251 segments left as
        proposed" is a number with nowhere to point.
        """
        if not session.state()["done"]["flats"]:
            raise HTTPException(404, "flats not generated")
        mask = session.unsnapped_mask()
        rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
        rgba[mask] = (240, 163, 94, 110)
        return _png(rgba)

    @app.post("/api/snap-all")
    def snap_all(threshold: float | None = None):
        """The bulk shortcut. `threshold` of null ignores the guard entirely."""
        # Snap first, then read the state: inside one dict literal the state
        # is built before the call that changes it, and the sidebar ends up
        # reporting the page as it was a moment before the artist pressed.
        result = session.snap_all(threshold)
        return {**session.state(), "result": result}

    # -- 7. export -------------------------------------------------------

    @app.post("/api/export")
    def export(granularity: str | None = None):
        """`granularity` is "colour" (one layer per palette entry, whole page)
        or "panel" (one group per panel). Omitted, the session keeps the one it
        was last given — the choice is the artist's, not the request's."""
        path = session.export_psd(granularity=granularity)
        return FileResponse(
            path, media_type="image/vnd.adobe.photoshop", filename=path.name
        )

    # No-store, deliberately: the front end is three files edited in place on
    # the same machine that serves them, and a browser holding yesterday's
    # `app.js` after a restart looks exactly like a bug in the app. Revalidation
    # costs nothing over localhost.
    app.mount("/", _Fresh(directory=_STATIC, html=True), name="static")
    return app


app = create_app()
