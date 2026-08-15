"""The app factory: router registration, error mapping, and the SPA mount.

RESEARCH.md § Architecture Patterns Pattern 2, used essentially verbatim.
All six phase-1 routers are registered here — five as empty stubs (see each
router module's own docstring for which later plan fills it in) — plus
``GET /api/health`` (needs no open project, so the frontend and this test
suite can prove the app booted) and an app-level handler mapping
``EmptyImageError`` to a structured 400, so a degenerate character sheet
never surfaces as a crash.

The built SPA is mounted **only when ``frontend/dist/index.html`` exists**.
A fresh checkout and this test suite have no ``dist/`` yet, and an
unconditional mount would make ``create_app()`` raise at import time.
Mounted last: API routes are matched first, unconditionally, and can never
be shadowed by the SPA mount regardless of mount order (Pattern 2's own
documented design).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..colour.extract import EmptyImageError
from .routers import page, palette, pipeline, project, reference, volume

# src/comiccolor/web/app.py -> parents[3] is the repo root. A
# COMICCOLOR_FRONTEND_DIST environment override lets `comiccolor serve` work
# from any working directory.
_REPO_ROOT = Path(__file__).resolve().parents[3]

FOREIGN_ORIGIN_DETAIL = (
    "That request came from another site, so it was refused — use the"
    " ComicColor window itself."
)


def _allowed_origins() -> set[str]:
    """Origins a state-changing request may legitimately come from.

    Loopback on any port (the artist may run `serve` on a non-default one)
    plus the vite dev server. ``COMICCOLOR_EXTRA_ORIGINS`` is a
    comma-separated escape hatch for a setup this list doesn't anticipate.
    """
    hosts = ("127.0.0.1", "localhost", "[::1]")
    ports = ("8000", "5173")
    origins = {
        f"http://{host}:{port}" for host in hosts for port in ports
    }
    origins |= {f"http://{host}" for host in hosts}
    extra = os.environ.get("COMICCOLOR_EXTRA_ORIGINS", "")
    origins |= {o.strip() for o in extra.split(",") if o.strip()}
    return origins


def create_app() -> FastAPI:
    app = FastAPI(title="ComicColor")

    @app.middleware("http")
    async def _reject_foreign_origins(request: Request, call_next):
        """Refuse a state-changing request from an origin that isn't ours.

        The app has no authentication by design (PROJECT.md: one machine,
        one artist) and binds loopback, which protects it from the network
        but not from the artist's own browser. JSON endpoints are
        incidentally safe — an ``application/json`` body forces a CORS
        preflight a hostile page cannot satisfy — but
        ``multipart/form-data`` is a CORS-*simple* content type, so any page
        the artist happens to be visiting while `comiccolor serve` runs can
        silently POST a cross-origin form to ``/api/pages/``,
        ``/api/palette/swatch`` or ``/api/references/sheets`` and write
        files and rows into the open project. ``POST /api/projects/browse``
        is worse: it pops a native dialog on the artist's desktop.

        Only requests that actually carry an ``Origin`` are checked. A
        same-origin ``GET`` from the SPA, and every non-browser caller
        (curl, the test suite), send none — this closes the cross-origin
        write class without inventing an auth model the project has
        deliberately not got.
        """
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin is not None and origin not in _allowed_origins():
                return JSONResponse(
                    status_code=403,
                    content={"detail": FOREIGN_ORIGIN_DETAIL},
                )
        return await call_next(request)

    app.include_router(project.router, prefix="/api/projects", tags=["projects"])
    app.include_router(volume.router, prefix="/api/volumes", tags=["volumes"])
    app.include_router(page.router, prefix="/api/pages", tags=["pages"])
    app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
    app.include_router(palette.router, prefix="/api/palette", tags=["palette"])
    app.include_router(
        reference.router, prefix="/api/references", tags=["references"]
    )

    @app.exception_handler(EmptyImageError)
    def _empty_image_error_handler(
        request: Request, exc: EmptyImageError
    ) -> JSONResponse:
        # A degenerate all-ink or all-paper sheet is a routine artist-facing
        # failure, never a 500 (RESEARCH.md Pitfall 4).
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # `comiccolor serve --reload` cannot hand this process an app object —
    # uvicorn's reloader re-imports the app in a fresh process each time, so
    # the startup project travels through the environment instead. Empty or
    # absent means "no project open", which is the normal case.
    startup_project = os.environ.get("COMICCOLOR_PROJECT", "").strip()
    if startup_project:
        from .deps import set_current_project

        set_current_project(app, Path(startup_project))

    dist_dir = Path(
        os.environ.get("COMICCOLOR_FRONTEND_DIST", str(_REPO_ROOT / "frontend" / "dist"))
    )
    if (dist_dir / "index.html").exists():
        if hasattr(app, "frontend"):
            app.frontend("/", directory=dist_dir)
        else:
            # Fallback for a FastAPI build without app.frontend() (RESEARCH.md
            # § State of the Art documents this as the well-established prior
            # pattern). Not expected to trigger — 01-01-SUMMARY confirms
            # fastapi 0.141.1, which ships app.frontend() — but kept so a
            # dependency downgrade fails soft rather than raising on import.
            from fastapi.staticfiles import StaticFiles

            app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")

    return app
