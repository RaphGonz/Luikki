"""The project lifecycle contract, as tests.

D-04's folder-per-project layout is what makes "copy the folder" a real
portability promise; PROJ-01 and PROJ-05 are what that promise is for —
create, reopen, and never lose an edit to a refresh or an unclean close.
RESEARCH.md Pitfall 1 (WAL checkpoint on close) and Pitfall 2
(``current_project_path`` is process-global, so "no project open" must
be a real, tested 4xx) are both named here because both are easy to get
right by accident in dev and wrong under the conditions D-04 actually
promises. Implemented by plan 01-07, against the routes plan 01-07 wrote
in ``src/comiccolor/web/routers/project.py``.
"""

import shutil
from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from comiccolor.model import PaletteEntry, Page, PipelineStage, Store, Volume
from comiccolor.web import appconfig
from comiccolor.web.app import create_app
from comiccolor.web.deps import NO_PROJECT_DETAIL, get_project
from comiccolor.web.routers.project import NOT_A_PROJECT_DETAIL, PROJECT_EXISTS_DETAIL


@pytest.fixture(autouse=True)
def isolated_recents(tmp_path, monkeypatch):
    """Never let a test read or write the real ``~/.comiccolor/recent.json``.

    ``appconfig``'s recents functions reference ``CONFIG_DIR``/
    ``RECENTS_PATH`` as module globals, so patching them here on the
    ``appconfig`` module object redirects every caller — including the
    routes under test — to a throwaway file for the duration of one test.
    """
    config_dir = tmp_path / "_comiccolor_config"
    monkeypatch.setattr(appconfig, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(appconfig, "RECENTS_PATH", config_dir / "recent.json")


def test_create_project_makes_folder_layout(blank_client, tmp_path):
    """PROJ-01, D-04: creating a project produces a folder containing
    ``project.db``, ``pages/``, ``references/pending/`` and
    ``label_maps/`` — the layout every other route assumes exists."""
    response = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(tmp_path)}
    )
    assert response.status_code == 201
    project_dir = Path(response.json()["path"])
    names = {p.name for p in project_dir.iterdir()}
    assert {"project.db", "pages", "references", "label_maps"} <= names
    assert (project_dir / "references" / "pending").is_dir()


def test_reopen_after_close_keeps_pages_and_palette(blank_client, tmp_path):
    """PROJ-01, PROJ-05: closing the app and reopening the project later
    finds its pages, palette and prior edits intact."""
    created = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(tmp_path)}
    ).json()
    project_dir = Path(created["path"])
    project_id = created["id"]

    with Store(project_dir / appconfig.PROJECT_DB_NAME) as store:
        store.add_palette_entry(
            PaletteEntry(project_id=project_id, rgb=(200, 50, 50), label="hair/base")
        )
        volume = store.add_volume(Volume(project_id=project_id, name="Chapter 1"))
        store.add_page(
            Page(
                volume_id=volume.id,
                source_path=str(project_dir / "pages" / "0001.png"),
                index=0,
                width=100,
                height=100,
            )
        )

    assert blank_client.post("/api/projects/close").status_code == 204

    reopened = blank_client.post(
        "/api/projects/open", json={"path": str(project_dir)}
    )
    assert reopened.status_code == 200
    assert reopened.json()["palette_revision"] == 1

    with Store(project_dir / appconfig.PROJECT_DB_NAME) as store:
        entries = store.palette_for_project(project_id)
        assert len(entries) == 1
        assert entries[0].label == "hair/base"

        volumes = store.volumes_for_project(project_id)
        assert len(volumes) == 1
        pages = store.pages_for_volume(volumes[0].id)
        assert len(pages) == 1
        assert pages[0].stage == PipelineStage.PANELS


def test_requests_without_an_open_project_return_409():
    """RESEARCH.md Pitfall 2: ``current_project_path`` is process-global.
    A project-scoped request made before any project is opened returns
    409, never a silent guess or a 500.

    Filled by plan 01-06, ahead of every other stub in this package
    (which stay filled by 01-07..01-10): the dependency chain
    (``get_current_project_path`` -> ``get_store`` -> ``get_project``) is
    this plan's own deliverable, and every later router shares it, so it
    needs one real, passing proof before any router body exists. No
    router has a route yet (they are empty stubs until 01-07..01-10), so
    this registers one throwaway probe endpoint directly on the app
    instance — never on a shared router module — depending on
    ``get_project`` the same way every real future route will, and
    asserts against ``/api/palette`` (RESEARCH.md Pitfall 2's own named
    example route)."""
    app = create_app()

    @app.get("/api/palette")
    def _probe_requires_a_project(project=Depends(get_project)):
        return {"id": project.id}

    with TestClient(app) as blank_client:
        response = blank_client.get("/api/palette")

    assert response.status_code == 409
    assert response.json()["detail"] == NO_PROJECT_DETAIL


def test_open_rejects_a_path_without_a_project_db(blank_client, tmp_path):
    """Security Domain V12: the backend only ever opens a path that
    resolves to a real directory containing ``project.db``; anything
    else is a structured 4xx, never an attempt to create one implicitly."""
    plain_dir = tmp_path / "not-a-project"
    plain_dir.mkdir()

    response = blank_client.post("/api/projects/open", json={"path": str(plain_dir)})

    assert response.status_code == 400
    assert response.json()["detail"] == NOT_A_PROJECT_DETAIL
    assert not (plain_dir / appconfig.PROJECT_DB_NAME).exists()


def test_recent_list_skips_folders_that_disappeared(blank_client, tmp_path):
    """D-04: the recent-projects list is a convenience index only. A
    folder that has moved or vanished silently drops out of it and never
    becomes authoritative."""
    kaito = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(tmp_path)}
    ).json()
    blank_client.post("/api/projects/close")

    moebius = blank_client.post(
        "/api/projects", json={"name": "Moebius", "parent_dir": str(tmp_path)}
    ).json()
    blank_client.post("/api/projects/close")

    shutil.rmtree(kaito["path"])

    response = blank_client.get("/api/projects/recent")

    assert response.status_code == 200
    assert [r["name"] for r in response.json()] == [moebius["name"]]


def test_close_checkpoints_the_wal(blank_client, tmp_path):
    """RESEARCH.md Pitfall 1, resolved Open Question 1: closing a
    project checkpoints the WAL, so copying, zipping or handing over the
    folder afterwards yields a complete database."""
    created = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(tmp_path)}
    ).json()
    project_dir = Path(created["path"])
    project_id = created["id"]

    with Store(project_dir / appconfig.PROJECT_DB_NAME) as store:
        store.add_palette_entry(
            PaletteEntry(project_id=project_id, rgb=(10, 20, 30), label="sky/base")
        )

    assert blank_client.post("/api/projects/close").status_code == 204

    wal_path = project_dir / f"{appconfig.PROJECT_DB_NAME}-wal"
    assert not wal_path.exists() or wal_path.stat().st_size == 0

    copy_dir = tmp_path / "Kaito-copy"
    shutil.copytree(project_dir, copy_dir)
    with Store(copy_dir / appconfig.PROJECT_DB_NAME) as store:
        entries = store.palette_for_project(project_id)
        assert len(entries) == 1
        assert entries[0].label == "sky/base"


def test_creating_into_an_occupied_folder_is_a_409(blank_client, tmp_path):
    """D-04: a create can never clobber an artist's existing project —
    the ``PROJECT_EXISTS_DETAIL`` path."""
    first = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(tmp_path)}
    )
    assert first.status_code == 201
    blank_client.post("/api/projects/close")

    second = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(tmp_path)}
    )

    assert second.status_code == 409
    assert second.json()["detail"] == PROJECT_EXISTS_DETAIL


def test_no_save_endpoint_exists(blank_client):
    """PROJ-05, 01-UI-SPEC.md §7: every edit is durable the moment it is
    made, with no Save button anywhere in the contract. Pinned as a test
    so one never appears later by accident."""
    paths = [p for p in blank_client.app.openapi()["paths"]]

    assert not any("save" in p.lower() or "commit" in p.lower() for p in paths)
