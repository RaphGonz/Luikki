"""Per-request ``Store`` construction and current-project resolution.

RESEARCH.md § Architecture Patterns Pattern 1, used essentially verbatim.

**Process-global "currently open project" is a conscious choice, not an
oversight.** ``app.state.current_project_path`` is a single value shared by
every request in the process, not per-session or per-browser-tab. PROJECT.md
scopes v1 to one machine, one artist, testing supervised over video call — a
process-global is correct and sufficient for that. RESEARCH.md Pitfall 2 and
Assumptions Log A2 name the accepted residual risk explicitly: two browser
tabs pointed at two different projects would share this one value and could
write to the unintended project. Accepted for v1 (threat register T-01-TABS).

Nothing outside this module may assign ``app.state.current_project_path`` —
only :func:`set_current_project` and :func:`clear_current_project` do that.

Every route that touches the database gets a fresh ``Store`` on its own
connection for the duration of one request (:func:`get_store`). A single
long-lived connection shared across the threadpool with SQLite's thread
check disabled is explicitly rejected by RESEARCH.md § Alternatives
Considered as a race-condition risk; a fresh connection per request is what
reconciles ``Store``'s documented "one Store per thread" contract with
FastAPI running sync routes on a threadpool.
Re-running the idempotent ``CREATE TABLE IF NOT EXISTS`` schema script per
request costs microseconds on a local file and is immaterial at one-artist
scale.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request

from ..model import Project, Store
from .appconfig import PROJECT_DB_NAME

NO_PROJECT_DETAIL = "No project is currently open."


def get_current_project_path(request: Request) -> Path:
    path = getattr(request.app.state, "current_project_path", None)
    if path is None:
        raise HTTPException(status_code=409, detail=NO_PROJECT_DETAIL)
    return path


def get_store(project_path: Path = Depends(get_current_project_path)) -> Iterator[Store]:
    with Store(project_path / PROJECT_DB_NAME) as store:
        yield store


def get_project(store: Store = Depends(get_store)) -> Project:
    project = store.the_project()
    if project is None:
        raise HTTPException(status_code=409, detail=NO_PROJECT_DETAIL)
    return project


def set_current_project(app: FastAPI, path: Path) -> None:
    """The only place ``app.state.current_project_path`` is ever set."""
    app.state.current_project_path = path


def clear_current_project(app: FastAPI) -> None:
    """The only place ``app.state.current_project_path`` is ever cleared."""
    app.state.current_project_path = None
