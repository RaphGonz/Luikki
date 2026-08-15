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
    """A TestClient with a project already open.

    ``TestClient`` is httpx-backed (RESEARCH.md Validation Architecture)
    — no real uvicorn process runs. The ``with`` block drives FastAPI's
    lifespan. ``app.state.current_project_path`` is process-global
    (RESEARCH.md Pitfall 2), which is exactly what this fixture sets up
    per test via a fresh app instance.
    """
    from fastapi.testclient import TestClient

    from comiccolor.web.app import create_app

    app = create_app()
    app.state.current_project_path = project_dir
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
