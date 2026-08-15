"""The project lifecycle contract, as tests.

D-04's folder-per-project layout is what makes "copy the folder" a real
portability promise; PROJ-01 and PROJ-05 are what that promise is for —
create, reopen, and never lose an edit to a refresh or an unclean close.
RESEARCH.md Pitfall 1 (WAL checkpoint on close) and Pitfall 2
(``current_project_path`` is process-global, so "no project open" must
be a real, tested 4xx) are both named here because both are easy to get
right by accident in dev and wrong under the conditions D-04 actually
promises. These stubs are Wave 0 scaffolding for plan 01-07.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-07")
def test_create_project_makes_folder_layout():
    """PROJ-01, D-04: creating a project produces a folder containing
    ``project.db``, ``pages/``, ``references/pending/`` and
    ``label_maps/`` — the layout every other route assumes exists."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-07")
def test_reopen_after_close_keeps_pages_and_palette():
    """PROJ-01, PROJ-05: closing the app and reopening the project later
    finds its pages, palette and prior edits intact."""
    ...


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
    from fastapi import Depends
    from fastapi.testclient import TestClient

    from comiccolor.web.app import create_app
    from comiccolor.web.deps import NO_PROJECT_DETAIL, get_project

    app = create_app()

    @app.get("/api/palette")
    def _probe_requires_a_project(project=Depends(get_project)):
        return {"id": project.id}

    with TestClient(app) as blank_client:
        response = blank_client.get("/api/palette")

    assert response.status_code == 409
    assert response.json()["detail"] == NO_PROJECT_DETAIL


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-07")
def test_open_rejects_a_path_without_a_project_db():
    """Security Domain V12: the backend only ever opens a path that
    resolves to a real directory containing ``project.db``; anything
    else is a structured 4xx, never an attempt to create one implicitly."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-07")
def test_recent_list_skips_folders_that_disappeared():
    """D-04: the recent-projects list is a convenience index only. A
    folder that has moved or vanished silently drops out of it and never
    becomes authoritative."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-07")
def test_close_checkpoints_the_wal():
    """RESEARCH.md Pitfall 1, resolved Open Question 1: closing a
    project checkpoints the WAL, so copying, zipping or handing over the
    folder afterwards yields a complete database."""
    ...
