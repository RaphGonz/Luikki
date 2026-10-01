"""The six buttons, over HTTP.

One route per button and nothing else — rule 3: a route with no button is a
feature that does not exist, and the inverse is what this file exists to
prevent. Every endpoint below is reachable from `static/app.js`.

Endpoints are plain `def`, not `async def`, deliberately: segmentation and
generation are seconds of CPU or GPU work, and FastAPI runs sync handlers in a
threadpool instead of stalling the event loop with them.
"""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from pydantic import BaseModel

from .. import billing
from ..account import Account, AccountError

from .project import default_workdir
from .session import Session, StepError
from .update import Updater


class Shape(BaseModel):
    """A polygon in page space, as the artist left it on screen.

    A node is two numbers — a corner — or four, the last two being the tangent
    the artist pulled out of it. Only the browser and `flatten_polygon` read
    the handles; everything that rasterises a shape is given points.
    """

    polygon: list[tuple[int, int] | tuple[int, int, int, int]]


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


class Purchase(BaseModel):
    """One line of `cloud/billing.py`'s `LINES`."""

    line: str


class Zone(BaseModel):
    panel: int
    label: int


class Planes(BaseModel):
    """Zones the artist put on one plane (`segmentation.planes`)."""

    zones: list[Zone]
    plane: int


class Export(BaseModel):
    """The PSD's layer names, in the artist's language, by `LAYER_NAMES` key."""

    names: dict[str, str] = {}


class Email(BaseModel):
    """Where to send a sign-in code."""

    email: str


class Code(BaseModel):
    """The code that arrived, and the address it went to."""

    email: str
    code: str

_STATIC = Path(__file__).parent / "static"


class _Fresh(StaticFiles):
    """`StaticFiles` that never lets the browser reuse a file without asking."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-store"
        return response

def create_app(
    workdir: str | Path | None = None,
    extractor=None,
    account: Account | None = None,
    updater: Updater | None = None,
    depth=None,
) -> FastAPI:
    app = FastAPI(title="Luikki")
    workdir = Path(workdir) if workdir else default_workdir()
    account = account or Account()
    session = Session(workdir, extractor=extractor, account=account, depth=depth)
    app.state.session = session
    updater = updater or Updater()
    app.state.updater = updater

    def _png(rgba: np.ndarray) -> Response:
        buffer = io.BytesIO()
        Image.fromarray(rgba).save(buffer, format="PNG")
        return Response(buffer.getvalue(), media_type="image/png")

    @app.exception_handler(StepError)
    def _step_error(_request, exc: StepError):
        return JSONResponse({"code": exc.code, "params": exc.params}, status_code=exc.status)

    @app.exception_handler(AccountError)
    def _account_error(_request, exc: AccountError):
        return JSONResponse({"code": exc.code, "params": exc.params}, status_code=exc.status)

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

    @app.post("/api/cancel")
    def cancel():
        """Stop the step in flight, between two of its passes. Without the
        lock, like the progress: the step holds it. The step itself answers
        with `cancelled`, and leaves the page as it was before the press."""
        return {"stopping": session.progress.cancel()}

    # -- updates ---------------------------------------------------------
    #
    # Here and not in the browser: the installer is downloaded, checked and
    # started by this process, which is the one it replaces.

    @app.get("/api/update")
    def update_check():
        return updater.check()

    @app.post("/api/update")
    def update_install():
        updater.install(session.progress)
        return {}

    # -- the account -----------------------------------------------------
    #
    # Signing in runs here and not in the browser: the session belongs in the
    # system's password store, which only this process can reach.

    @app.post("/api/account/code")
    def send_code(body: Email):
        session.account.send_code(body.email)
        return session.state()

    @app.post("/api/account")
    def sign_in(body: Code):
        session.account.verify(body.email, body.code)
        return session.state()

    @app.delete("/api/account")
    def sign_out():
        session.account.sign_out()
        return session.state()

    # Stripe's pages open in the system browser, asked for from here: this
    # process holds the session they are asked for with.

    @app.post("/api/account/buy")
    def buy(body: Purchase):
        billing.buy(session.account, body.line)
        return {}

    @app.post("/api/account/manage")
    def manage_subscription():
        billing.manage(session.account)
        return {}

    @app.get("/api/account/status")
    def licence():
        """The licence, as `my_status` tells it (ROADMAP G4). Taken without
        the session lock: it asks Supabase, and answers while a step runs.
        `licence` is null when signed out or when the server does not answer
        — unknown, never a refusal."""
        account = session.account
        found = None
        if account is not None and account.email:
            try:
                found = account.status()
            except AccountError:
                found = None
        licence = None
        if found:
            licence = {
                # `studio` and `tester` from before G4 stay valid, as does a
                # paid year (`luikki`, whatever line bought it).
                "active": found.get("plan") is not None,
                "plan": found.get("plan"),
                "until": found.get("colours_until"),
                "customer": bool(found.get("customer")),
            }
        return {"signed_in": bool(account is not None and account.email), "licence": licence}

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
            raise StepError("image_unreadable", status=422, detail=str(exc)) from exc
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

    @app.post("/api/bubbles/skip")
    def skip_bubbles():
        session.skip_bubbles()
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
    def segment_zones(gap: float | None = None, extract: bool | None = None):
        """`gap` is §1.3's gap allowance, kept for the rest of the book;
        `extract` turns line extraction on for this page (ROADMAP G5)."""
        session.segment_zones(leak_gap=gap, extract_lines=extract)
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
        if session._structural is None or not session.extract_lines:
            raise HTTPException(404, "lines not extracted on this page")
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
    # corrections; Ctrl+Z takes the last few back.

    @app.get("/api/zone")
    def zone_at(x: int, y: int):
        """The zone under a page-space point — what a press resolves to."""
        found = session.zone_at(x, y)
        if found is None:
            raise HTTPException(404, "no zone at that point")
        panel, label = found
        _, bounds = session.zone_mask_rgba(panel, label)
        return {
            "panel": panel,
            "label": label,
            "bounds": list(bounds),
            "plane": session.plane_of(panel, label),
        }

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
                {
                    "panel": panel,
                    "label": label,
                    "bounds": list(boxes[panel][label]),
                    "plane": session.plane_of(panel, label),
                }
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

    @app.post("/api/zones/undo")
    def undo_zones():
        result = session.undo_zones()
        return {**session.state(), "result": result}

    # -- 5. planes -------------------------------------------------------

    @app.post("/api/planes")
    def detect_planes():
        session.detect_planes()
        return session.state()

    @app.put("/api/planes")
    def set_planes(body: Planes):
        """Zones the artist moved to a plane, or called characters."""
        session.set_planes([(zone.panel, zone.label) for zone in body.zones], body.plane)
        return session.state()

    @app.get("/api/planes.png")
    def planes_png(tints: str | None = None):
        """`tints` is four hex colours, by plane, from the tokens of
        `app.css`: the interface owns its colours, the server only paints."""
        if not session.state()["done"]["planes"]:
            raise HTTPException(404, "planes not found yet")
        chosen = None
        if tints:
            try:
                chosen = {
                    plane: tuple(int(tint[i : i + 2], 16) for i in (0, 2, 4))
                    for plane, tint in enumerate(tints.split(","))
                }
            except ValueError:
                raise HTTPException(422, "tints are four hex colours") from None
            if len(chosen) != 4:
                raise HTTPException(422, "tints are four hex colours")
        return _png(session.planes_rgba(chosen))

    # -- 6. export -------------------------------------------------------

    @app.post("/api/export")
    def export(
        granularity: str | None = None,
        support_grey: bool | None = None,
        body: Export | None = None,
    ):
        """`granularity` is "plane" (one layer per plane) or "colour" (one
        group per plane, one layer per colour inside it). `support_grey` adds
        the printer's two ink layers over the flats. Omitted, either keeps
        what the session was last given — the choice is the artist's, not the
        request's."""
        path = session.export_psd(
            granularity=granularity,
            support_grey=support_grey,
            names=body.names if body else None,
        )
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
