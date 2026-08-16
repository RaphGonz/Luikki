"""Shared fixtures for the web route test package.

Every fixture that touches ``comiccolor.web`` imports it inside the
fixture body, not at module level, so this file (and every test module
that depends on it) collects cleanly before ``comiccolor.web`` exists
(Wave 0). Plan 01-06 is what makes these fixtures real against a working
``create_app``; until then, any test that actually uses ``client`` or
``blank_client`` stays skip-marked.
"""

import pytest


@pytest.fixture
def project_dir(tmp_path):
    """A project's folder-per-project layout (D-04), without a project.db.

    Route tests build on this rather than each inventing its own
    directory layout: ``pages/``, ``references/pending/`` and
    ``label_maps/`` are the subdirectories ``create_project`` is
    expected to lay out.
    """
    path = tmp_path / "Kaito"
    (path / "pages").mkdir(parents=True)
    (path / "references" / "pending").mkdir(parents=True)
    (path / "label_maps").mkdir(parents=True)
    return path


@pytest.fixture
def client(project_dir):
    """A TestClient with a real project already open.

    ``TestClient`` is httpx-backed (RESEARCH.md Validation Architecture)
    — no real uvicorn process runs. The ``with`` block drives FastAPI's
    lifespan. A ``Store`` is created at ``project_dir/project.db`` with a
    ``Project`` row first (a request against a folder with no project row
    should behave identically to one against no folder at all — both are
    "no project", per ``get_project``), then ``set_current_project`` is the
    only way ``app.state.current_project_path`` is ever written
    (RESEARCH.md Pitfall 2).
    """
    from fastapi.testclient import TestClient

    from comiccolor.model import Project, Store
    from comiccolor.web.app import create_app
    from comiccolor.web.appconfig import PROJECT_DB_NAME
    from comiccolor.web.deps import set_current_project

    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.add_project(Project(name=project_dir.name))

    app = create_app()
    set_current_project(app, project_dir)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def blank_client():
    """Same app, no project opened.

    Backs ``test_requests_without_an_open_project_return_409`` — every
    project-scoped route must refuse to guess which project a request
    means (RESEARCH.md Pitfall 2).
    """
    from fastapi.testclient import TestClient

    from comiccolor.web.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    # NOTE: app.state.current_project_path is simply never set here — no
    # call to clear_current_project is needed, since each test gets a fresh
    # app instance (see get_current_project_path's getattr default).


@pytest.fixture
def make_png():
    """Factory fixture: ``(width, height, colours) -> PNG bytes``.

    Builds a flat-chip grid in memory with Pillow — one colour per chip,
    tiling the requested dimensions as evenly as possible — for use as
    multipart upload payloads. No file touches disk.
    """

    def _make(width: int, height: int, colours: list[tuple[int, int, int]]) -> bytes:
        import io
        import math

        from PIL import Image, ImageDraw

        cols = math.ceil(math.sqrt(len(colours)))
        rows = math.ceil(len(colours) / cols)
        chip_w = width / cols
        chip_h = height / rows

        image = Image.new("RGB", (width, height), colours[0])
        draw = ImageDraw.Draw(image)
        for i, colour in enumerate(colours):
            row, col = divmod(i, cols)
            x0, y0 = round(col * chip_w), round(row * chip_h)
            x1, y1 = round((col + 1) * chip_w), round((row + 1) * chip_h)
            draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=colour)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    return _make


@pytest.fixture
def page_in_project(client, make_png):
    """A single persisted page inside the currently open project.

    Composes ``client`` (project already open, per its own docstring) and
    ``make_png`` (an in-memory PNG factory) so a route test needing "some
    page that exists" gets one in a single fixture call instead of each
    test reinventing the volume-then-upload dance. Yields the accepted
    page dict as returned by ``POST /api/pages/`` (``id``, ``volume_id``,
    ``width``, ``height``, ``stage``, ...).
    """
    volume = client.post("/api/volumes/", json={"name": "Chapter 1"}).json()
    png_bytes = make_png(64, 64, [(9, 9, 9)])
    response = client.post(
        f"/api/pages/?volume_id={volume['id']}",
        files=[("files", ("page.png", png_bytes, "image/png"))],
    )
    yield response.json()["accepted"][0]
