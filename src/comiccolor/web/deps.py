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
long-lived connection shared across the threadpool is explicitly rejected
by RESEARCH.md § Alternatives Considered as a race-condition risk; a fresh
connection per request is what confines each ``Store`` to exactly one
owner.
Re-running the idempotent ``CREATE TABLE IF NOT EXISTS`` schema script per
request costs microseconds on a local file and is immaterial at one-artist
scale.

**Two rules a contributor adding a route must follow.** Both are about the
same thing — which thread the per-request sqlite connection is touched
from — and breaking either produces a failure the sequential ``TestClient``
suite cannot see, only real concurrent browser traffic can.

1. **Every route that depends on :func:`get_store` must be a plain ``def``,
   never ``async def``.** An ``async def`` handler runs on the event loop
   thread while ``get_store`` still resolves in the threadpool, so a
   blocking sqlite call would land on the loop and stall every other
   request. ``test_no_store_route_is_async`` walks ``app.routes`` and fails
   the build if a coroutine handler ever depends on ``get_store``, so this
   rule is enforced structurally rather than by review.

2. **The connection is opened with ``check_same_thread=False``** (see
   ``model/store.py.__init__``). This is load-bearing, not a shortcut:
   FastAPI runs a sync generator dependency's ``__enter__``, the endpoint,
   and its ``__exit__`` as three separate ``run_in_threadpool`` calls, and
   anyio makes no same-worker guarantee across them. Even with rule 1
   honoured, the connection legitimately *moves* between threadpool workers
   within one request. What the design guarantees is single *ownership*
   (one request at a time), not single-thread residency — so the
   object-level thread assertion is the one thing that must be relaxed.
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
    """One ``Store`` on its own connection, for the duration of one request.

    **Any route depending on this must be a plain ``def``, never
    ``async def``** — see this module's docstring for why, and for the
    ``check_same_thread=False`` half of the same contract.
    """
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
