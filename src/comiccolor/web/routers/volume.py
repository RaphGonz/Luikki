"""Volume routes.

PROJ-02 (organise a project's pages into volumes) and D-03's deliberately
minimal artist-visible volumes: create, list, rename, delete — nothing else.
CONTEXT.md is explicit that D-03 added volumes after the cost was named, and
that the UI stays minimal; this module's route count should never grow past
those four verbs, however tempting a richer volume-management surface might
seem later.

Deleting a volume relies on the schema's own ``ON DELETE CASCADE`` to remove
its pages — no manual cascade loop belongs in this module. Page image files
already on disk are deliberately left in place (T-01-DISK, accepted):
orphaned bytes are recoverable, a page an artist wanted back is not, and no
v1 requirement asks for disk reclamation.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...model import Project, Store, Volume
from ..deps import get_project, get_store
from ..schemas import VolumeCreateRequest, VolumeRenameRequest, VolumeResponse

router = APIRouter()

VOLUME_NOT_FOUND_DETAIL = "That volume no longer exists — refresh and try again."


def _volume_response(volume: Volume, store: Store) -> VolumeResponse:
    """The one place a ``Volume`` becomes a ``VolumeResponse``.

    ``page_count`` is precomputed here from ``pages_for_volume`` so the
    sidebar tree can render every volume's count in one ``GET /`` round
    trip instead of the browser fanning out an N+1 request per volume.
    """
    return VolumeResponse(
        id=volume.id,
        project_id=volume.project_id,
        name=volume.name,
        page_count=len(store.pages_for_volume(volume.id)),
    )


def get_owned_volume(volume_id: int, project: Project, store: Store) -> Volume:
    """The volume, or a 404 if it does not belong to the current project.

    T-01-IDOR (accept): there is exactly one artist and one open project, so
    this check is about correctness (a stale id from a closed project) not
    cross-tenant access control.

    Public rather than underscore-prefixed because ``page.py`` calls it too:
    an upload names its target volume by raw id, and that id needs the same
    check the volume routes give it. A second implementation over there
    would be a second thing to keep in step.
    """
    for volume in store.volumes_for_project(project.id):
        if volume.id == volume_id:
            return volume
    raise HTTPException(status_code=404, detail=VOLUME_NOT_FOUND_DETAIL)


@router.get("/")
def list_volumes(
    project: Project = Depends(get_project), store: Store = Depends(get_store)
) -> list[VolumeResponse]:
    volumes = store.volumes_for_project(project.id)
    return [_volume_response(v, store) for v in volumes]


@router.post("/", status_code=201)
def create_volume(
    body: VolumeCreateRequest,
    project: Project = Depends(get_project),
    store: Store = Depends(get_store),
) -> VolumeResponse:
    """The schema's ``UNIQUE (project_id, name)`` makes a repeated name
    structurally impossible; a caught ``sqlite3.IntegrityError`` becomes a
    409 naming the conflict, per the UI-SPEC error shape."""
    try:
        volume = store.add_volume(Volume(project_id=project.id, name=body.name))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f'A volume named "{body.name}" already exists in this project.',
        ) from exc
    return _volume_response(volume, store)


@router.patch("/{volume_id}")
def rename_volume(
    volume_id: int,
    body: VolumeRenameRequest,
    project: Project = Depends(get_project),
    store: Store = Depends(get_store),
) -> VolumeResponse:
    volume = get_owned_volume(volume_id, project, store)
    store.rename_volume(volume.id, body.name)
    volume.name = body.name
    return _volume_response(volume, store)


@router.delete("/{volume_id}", status_code=204)
def delete_volume(
    volume_id: int,
    project: Project = Depends(get_project),
    store: Store = Depends(get_store),
) -> None:
    """204. ``ON DELETE CASCADE`` already removes the volume's pages —
    nothing here re-implements that. Page image files on disk are left in
    place (T-01-DISK, accepted)."""
    get_owned_volume(volume_id, project, store)
    store.delete_volume(volume_id)
