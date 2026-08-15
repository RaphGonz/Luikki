"""``POST /api/projects`` must not write outside ``parent_dir`` (CR-02).

``name`` is the only client string this app turns into a directory name.
``_resolve_project_path`` guards ``POST /open`` carefully, but that guard
works by requiring the path to *already* be a project folder — it cannot
apply to the create route, which is the one route that writes. Before the
fix, every case below returned 201 and laid out a project folder outside
``parent_dir``.

WR-19's non-empty-directory adoption is tested here too, because it is the
same failure surface: it is what let the traversal reproduction land
inside an existing ``secret/`` rather than being refused.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from comiccolor.web import appconfig
from comiccolor.web.routers.project import (
    FOLDER_NOT_EMPTY_DETAIL,
    UNSAFE_NAME_DETAIL,
)


@pytest.fixture(autouse=True)
def isolated_recents(tmp_path, monkeypatch):
    """Never let a test read or write the real ``~/.comiccolor/recent.json``."""
    config_dir = tmp_path / "_comiccolor_config"
    monkeypatch.setattr(appconfig, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(appconfig, "RECENTS_PATH", config_dir / "recent.json")


@pytest.fixture
def workspace(tmp_path):
    """A parent folder with a sibling the traversal cases try to reach."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


TRAVERSAL_NAMES = [
    "../secret/pwned",
    "..\\secret\\pwned",
    "..",
    ".",
    "sub/nested",
    "sub\\nested",
    ".hidden",
]


@pytest.mark.parametrize("name", TRAVERSAL_NAMES)
def test_traversing_project_name_is_refused(blank_client, workspace, tmp_path, name):
    """A name that isn't a single folder name is a 4xx, and writes nothing.

    Both layers are acceptable outcomes here — 422 from ``ProjectName``'s
    pattern, 400 from ``create_project_folder``'s containment assertion —
    so the assertion is on the class of response, not the exact code. What
    is not negotiable is the second half: nothing appears outside
    ``parent_dir``.
    """
    before = sorted(p.name for p in tmp_path.iterdir())

    response = blank_client.post(
        "/api/projects", json={"name": name, "parent_dir": str(workspace)}
    )

    assert 400 <= response.status_code < 500, response.text
    assert not (tmp_path / "secret").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert list(workspace.iterdir()) == []


def test_absolute_project_name_cannot_discard_parent_dir(
    blank_client, workspace, tmp_path
):
    """``pathlib``'s ``/`` lets an absolute right-hand side drop the left.

    Reproduced before the fix as a 201 that created the project at the
    absolute path and ignored ``parent_dir`` entirely.
    """
    escape = tmp_path / "abs_escape"

    response = blank_client.post(
        "/api/projects", json={"name": str(escape), "parent_dir": str(workspace)}
    )

    assert 400 <= response.status_code < 500, response.text
    assert not escape.exists()
    assert list(workspace.iterdir()) == []


def test_ordinary_names_still_create_normally(blank_client, workspace):
    """The guard must not cost the artist an ordinary project name."""
    for name in ["Kaito", "Kaito vol. 2", "Moebius — Arzach", "l'Incal (1981)"]:
        response = blank_client.post(
            "/api/projects", json={"name": name, "parent_dir": str(workspace)}
        )
        assert response.status_code == 201, f"{name}: {response.text}"
        assert Path(response.json()["path"]) == workspace / name


def test_existing_non_empty_folder_is_not_adopted(blank_client, workspace):
    """WR-19: a stranger directory is not silently turned into a project.

    Before the fix the only guard was "does ``project.db`` exist", so any
    directory with other content in it was adopted and had ``pages/``,
    ``references/pending/`` and ``label_maps/`` created inside.
    """
    occupied = workspace / "Kaito"
    occupied.mkdir()
    (occupied / "notes.txt").write_text("the artist's own file", encoding="utf-8")

    response = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(workspace)}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == FOLDER_NOT_EMPTY_DETAIL
    assert sorted(p.name for p in occupied.iterdir()) == ["notes.txt"]


def test_existing_empty_folder_is_usable(blank_client, workspace):
    """An empty directory is not content — creating into it is fine.

    Worth pinning: the artist making the folder first in Explorer and then
    naming it in the app is an ordinary way to work, and refusing it would
    be a regression dressed up as a security fix.
    """
    (workspace / "Kaito").mkdir()

    response = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(workspace)}
    )

    assert response.status_code == 201
    assert (workspace / "Kaito" / appconfig.PROJECT_DB_NAME).is_file()


def test_create_project_folder_refuses_traversal_directly(tmp_path):
    """The containment assertion holds without the schema layer above it.

    ``create_project_folder`` is a plain function any future caller can
    reach without going through ``ProjectName``, so it carries its own
    guard rather than trusting its one current caller.
    """
    parent = tmp_path / "workspace"
    parent.mkdir()

    with pytest.raises(appconfig.UnsafeProjectNameError):
        appconfig.create_project_folder(parent, "../secret/pwned")

    assert not (tmp_path / "secret").exists()
    assert UNSAFE_NAME_DETAIL  # the route's copy for this case exists


# ---- WR-02: the recents index must never break the entry screen ---------


CORRUPT_RECENTS = [
    pytest.param('[{"name": "K", "path": "/x", "opened_at": "t", "extra": 1}]',
                 id="entry-with-an-unknown-key"),
    pytest.param("5", id="top-level-not-a-list"),
    pytest.param('{"name": "K"}', id="top-level-an-object"),
    pytest.param('[null, 3, "text"]', id="non-dict-entries"),
    pytest.param('[{"name": 1, "path": 2, "opened_at": 3}]', id="non-string-values"),
    pytest.param("not json at all", id="not-json"),
    pytest.param("", id="empty-file"),
]


@pytest.mark.parametrize("content", CORRUPT_RECENTS)
def test_corrupt_recents_never_breaks_the_entry_screen(blank_client, content):
    """WR-02: ``GET /api/projects/recent`` degrades to ``[]``, never 500.

    This is the first request the project picker makes, and the app has no
    in-app way to repair the file — a 500 here is a dead entry screen. The
    ``**item`` construction used to raise ``TypeError`` on any entry with
    an extra key, and iterating a non-list top level raised too; neither is
    a ``json.JSONDecodeError``, so neither was caught.
    """
    appconfig.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    appconfig.RECENTS_PATH.write_text(content, encoding="utf-8")

    response = blank_client.get("/api/projects/recent")

    assert response.status_code == 200
    assert response.json() == []


def test_a_forward_compatible_entry_is_still_read(blank_client, workspace):
    """An unknown key is ignored, not fatal — the entry still loads.

    Building from named keys rather than ``**item`` is what buys this: a
    ``recent.json`` written by a later version stays readable by this one.
    """
    created = blank_client.post(
        "/api/projects", json={"name": "Kaito", "parent_dir": str(workspace)}
    ).json()

    import json

    raw = json.loads(appconfig.RECENTS_PATH.read_text(encoding="utf-8"))
    raw[0]["colour_profile"] = "a field this version has never heard of"
    appconfig.RECENTS_PATH.write_text(json.dumps(raw), encoding="utf-8")

    response = blank_client.get("/api/projects/recent")

    assert response.status_code == 200
    assert [r["path"] for r in response.json()] == [created["path"]]
