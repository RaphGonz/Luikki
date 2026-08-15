"""Project lifecycle routes.

PROJ-01 (create/open/list a project) and PROJ-05 (durable, portable project
state — nothing here writes to the wrong database or loses an edit on a
refresh). Registered as an empty stub by plan 01-06; filled by plan 01-07.

Every path a client supplies (``POST /open``'s ``path``, and the recents
list's own entries) goes through :func:`_resolve_project_path` before this
process opens a database at it — RESEARCH.md § Security Domain V12: never
trust a filesystem path string from the browser without checking it first.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from ...model import Project, Store
from .. import appconfig
from ..deps import get_current_project_path, get_project, set_current_project
from ..schemas import ProjectCreateRequest, ProjectOpenRequest, ProjectResponse

router = APIRouter()

# Error copy, worded per 01-UI-SPEC.md's Copywriting Contract: the specific
# failure plus the next action, never a bare "Something went wrong".
NOT_A_PROJECT_DETAIL = (
    "That folder isn't a ComicColor project — pick a folder containing"
    " project.db, or create a new project."
)
PROJECT_EXISTS_DETAIL = (
    "A project already exists in that folder — open it instead, or pick a"
    " different name."
)


def _resolve_project_path(raw: str) -> Path:
    """Validate a client-supplied path before anything opens it.

    RESEARCH.md § Security Domain V12: this backend never opens an
    arbitrary path a client hands over without checking it first. Expands
    ``~``, resolves symlinks and ``..`` segments via ``Path.resolve()``,
    then requires the result to already be a directory containing
    ``project.db`` (:func:`appconfig.is_project_folder`) — this function
    never creates anything, and never follows the caller's string into a
    write of its own.
    """
    path = Path(raw).expanduser().resolve()
    if not appconfig.is_project_folder(path):
        raise HTTPException(status_code=400, detail=NOT_A_PROJECT_DETAIL)
    return path


def _to_response(project: Project, path: Path) -> ProjectResponse:
    """Shared shape for every route that hands back a whole project.

    Always includes the folder path — 01-UI-SPEC.md §8 shows the project
    name in the top toolbar, and the picker needs the path to highlight the
    matching recent row.
    """
    return ProjectResponse(
        id=project.id,
        name=project.name,
        path=str(path),
        palette_revision=project.palette_revision,
    )


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreateRequest, request: Request) -> ProjectResponse:
    """Lay out a new project folder (D-04) and open it.

    Builds its own ``Store`` explicitly rather than depending on
    ``Depends(get_store)``: that dependency resolves the project that is
    *already* open on ``app.state.current_project_path``, and at create
    time there is not one yet — do not "simplify" this into the dependency.

    The parent directory is created as a side effect of
    ``appconfig.create_project_folder`` laying out the new project's own
    subdirectories (it creates every missing directory on its path), so
    this route never needs a directory-creation call of its own.
    """
    parent = (
        Path(body.parent_dir).expanduser().resolve()
        if body.parent_dir
        else appconfig.DEFAULT_WORKSPACE
    )
    try:
        folder = appconfig.create_project_folder(parent, body.name)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=PROJECT_EXISTS_DETAIL) from exc

    with Store(folder / appconfig.PROJECT_DB_NAME) as store:
        project = store.add_project(Project(name=body.name))
        store.checkpoint()

    set_current_project(request.app, folder)
    appconfig.record_recent(folder, body.name)
    return _to_response(project, folder)


@router.post("/open", response_model=ProjectResponse)
def open_project(body: ProjectOpenRequest, request: Request) -> ProjectResponse:
    """Open an existing project by validated path (PROJ-01)."""
    folder = _resolve_project_path(body.path)
    with Store(folder / appconfig.PROJECT_DB_NAME) as store:
        project = store.the_project()
    if project is None:
        raise HTTPException(status_code=400, detail=NOT_A_PROJECT_DETAIL)

    set_current_project(request.app, folder)
    appconfig.record_recent(folder, project.name)
    return _to_response(project, folder)


@router.get("/current", response_model=ProjectResponse)
def current_project(
    project: Project = Depends(get_project),
    path: Path = Depends(get_current_project_path),
) -> ProjectResponse:
    """The currently open project, including its folder path.

    Depends on ``get_project`` so a request made before any project is
    open gets the same shared 409 every other project-scoped route uses,
    rather than a route-local special case.
    """
    return _to_response(project, path)
