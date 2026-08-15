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


def create_app() -> FastAPI:
    app = FastAPI(title="ComicColor")

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
