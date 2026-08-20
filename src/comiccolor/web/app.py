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
from .session import Session, StepError

_STATIC = Path(__file__).parent / "static"

def _build_proposer():
    """`COMICCOLOR_PROPOSER=cobra` swaps the model in without a code edit.

    Anything else — including unset — is the deterministic distinct-colour
    proposer, which needs no GPU and no weights. Read at call time, not import
    time, so `comiccolor serve --proposer cobra` works whatever the import
    order turns out to be.
    """
    if os.environ.get("COMICCOLOR_PROPOSER", "distinct") != "cobra":
        from ..colour.proposer import DistinctColourProposer

        return DistinctColourProposer()

    from ..colour.cobra import CobraProposer

    return CobraProposer()


def _build_extractor():
    """`COMICCOLOR_EXTRACTOR=raw` turns the line extractor off.

    The default is MangaLineExtraction, which is what §2.2's A/B chose: raw ink
    hands trapped-ball every stroke edge and every spot black as a zone. `raw`
    exists for the case where the artist's ink layer really is already a clean
    line image, and for tests that must not load 172 MB of weights.
    """
    if os.environ.get("COMICCOLOR_EXTRACTOR", "manga") == "raw":
        from ..extract.passthrough import PassthroughExtractor

        return PassthroughExtractor()
    return None  # Session picks MangaLineExtraction on the best device.


def create_app(
    workdir: str | Path | None = None,
    proposer=None,
    extractor=None,
) -> FastAPI:
    app = FastAPI(title="ComicColor")
    workdir = Path(workdir) if workdir else Path(tempfile.gettempdir()) / "comiccolor"
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

    @app.post("/api/reset")
    def reset():
        session.reset()
        return session.state()

    # -- 1. upload -------------------------------------------------------

    @app.post("/api/page")
    def upload_page(file: UploadFile):
        target = session.workdir / f"page{Path(file.filename or 'page.png').suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        try:
            session.load_page(target, original_name=file.filename or target.name)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(400, f"could not read that image: {exc}") from exc
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

    # -- 4. zones --------------------------------------------------------

    @app.post("/api/zones")
    def segment_zones():
        session.segment_zones()
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
            session.add_reference(staged, original_name=name, kind=kind)
        except UnknownKind as exc:
            raise HTTPException(422, str(exc)) from exc
        except EmptyImageError as exc:
            raise HTTPException(422, f"no colours in that image: {exc}") from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(422, f"could not read that image: {exc}") from exc
        finally:
            # The store keeps its own copy, so the upload never lingers.
            staged.unlink(missing_ok=True)
        return session.state()

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

    # -- 6. export -------------------------------------------------------

    @app.post("/api/export")
    def export():
        path = session.export_psd()
        return FileResponse(
            path, media_type="image/vnd.adobe.photoshop", filename=path.name
        )

    app.mount("/", StaticFiles(directory=_STATIC, html=True), name="static")
    return app


app = create_app()
