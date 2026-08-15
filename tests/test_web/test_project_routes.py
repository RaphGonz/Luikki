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


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-07")
def test_requests_without_an_open_project_return_409():
    """RESEARCH.md Pitfall 2: ``current_project_path`` is process-global.
    A project-scoped request made before any project is opened returns
    409, never a silent guess or a 500."""
    ...


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
