"""Cross-cutting guards that belong to no single router.

WR-04 (upload limits enforced before the allocation they exist to
prevent), WR-09 (cross-origin writes), and WR-16's ``COMICCOLOR_PROJECT``
handoff, which only exists because uvicorn's reloader re-imports the app in
a fresh process and so cannot be handed an app object.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from comiccolor.web import uploads
from comiccolor.web.app import FOREIGN_ORIGIN_DETAIL


def _png(width=8, height=8, colour=(9, 9, 9)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, "PNG")
    return buf.getvalue()


def _make_volume(client, name="Chapter 1") -> int:
    return client.post("/api/volumes/", json={"name": name}).json()["id"]


# ---- WR-04: the size cap must precede the allocation --------------------


def test_read_capped_refuses_before_materialising_the_whole_payload(monkeypatch):
    """The cap is applied per chunk, not to a fully-read ``bytes``.

    Every router used to call ``file.file.read()`` — an unbounded read —
    and only then had ``decode_image`` compare the length, so the limit
    never prevented the allocation. This drives the reader with a small
    limit and a stream that would be far larger if read whole.
    """
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 1024)
    monkeypatch.setattr(uploads, "READ_CHUNK_BYTES", 128)

    stream = io.BytesIO(b"x" * 10_000)

    with pytest.raises(Exception) as excinfo:
        uploads.read_capped(stream)

    assert getattr(excinfo.value, "status_code", None) == 400
    # Stopped early: it never consumed the whole stream.
    assert stream.tell() <= 1024 + 128


def test_read_capped_accepts_a_payload_exactly_at_the_limit(monkeypatch):
    """The boundary is inclusive — the limit is a limit, not a limit minus one."""
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 1024)
    monkeypatch.setattr(uploads, "READ_CHUNK_BYTES", 128)

    assert uploads.read_capped(io.BytesIO(b"x" * 1024)) == b"x" * 1024


def test_oversized_upload_is_a_rejection_not_a_crash(client, monkeypatch):
    """End to end: an oversized page is one ``RejectedUpload``, not a 500."""
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 256)
    volume_id = _make_volume(client)

    response = client.post(
        f"/api/pages/?volume_id={volume_id}",
        files=[("files", ("big.png", _png(200, 200), "image/png"))],
    )

    assert response.status_code == 400
    assert response.json()["rejected"][0]["filename"] == "big.png"


def test_oversized_dimensions_are_refused_before_rasterising(monkeypatch):
    """WR-04: the dimension guard runs against the header, not the pixels.

    ``decode_image`` used to call ``image.load()`` — a full decode — before
    comparing ``image.size`` against ``MAX_DIMENSION``, so a
    decompression-bomb-shaped file was fully rasterised before the guard
    that exists to stop it ever ran. Lowering the limit and watching
    ``load`` never be reached is the only way to observe the ordering.
    """
    monkeypatch.setattr(uploads, "MAX_DIMENSION", 16)

    # Built before the spy is installed — Image.save() calls load() itself,
    # and counting that would make this test pass for the wrong reason.
    data = _png(64, 64)

    loaded: list[str] = []
    real_load = Image.Image.load

    def spy(self):
        loaded.append("load")
        return real_load(self)

    monkeypatch.setattr(Image.Image, "load", spy)

    with pytest.raises(Exception) as excinfo:
        uploads.decode_image(data)

    assert getattr(excinfo.value, "status_code", None) == 400
    assert loaded == [], "the image was rasterised before the dimension check"


def test_ordinary_images_still_decode(monkeypatch):
    """The reordering must not cost a legitimate upload."""
    image = uploads.decode_image(_png(8, 8, (1, 2, 3)))
    assert image.size == (8, 8)
    assert image.getpixel((0, 0)) == (1, 2, 3)


# ---- WR-09: cross-origin writes -----------------------------------------


def test_a_cross_origin_write_is_refused(client):
    """WR-09: multipart is a CORS-simple content type, so nothing else stops it.

    Any page the artist is browsing while `comiccolor serve` runs could
    silently POST a form here and write files and rows into the open
    project. JSON bodies are incidentally protected by the preflight;
    multipart is not.
    """
    volume_id = _make_volume(client)

    response = client.post(
        f"/api/pages/?volume_id={volume_id}",
        files=[("files", ("page.png", _png(), "image/png"))],
        headers={"Origin": "http://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == FOREIGN_ORIGIN_DETAIL
    assert client.get(f"/api/pages/?volume_id={volume_id}").json() == []


def test_the_native_folder_dialog_cannot_be_triggered_cross_origin(client):
    """``POST /projects/browse`` pops a dialog on the artist's desktop."""
    response = client.post(
        "/api/projects/browse", headers={"Origin": "http://evil.example"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "origin",
    ["http://127.0.0.1:8000", "http://localhost:8000", "http://localhost:5173"],
)
def test_the_apps_own_origins_are_allowed(client, origin):
    """Loopback and the vite dev server must keep working."""
    response = client.post(
        "/api/volumes/", json={"name": f"Volume {origin}"}, headers={"Origin": origin}
    )
    assert response.status_code == 201


def test_a_request_with_no_origin_header_is_allowed(client):
    """curl, the test suite, and same-origin GETs send no Origin at all."""
    assert client.post("/api/volumes/", json={"name": "Chapter 1"}).status_code == 201


def test_reads_are_never_blocked_by_the_origin_check(client):
    """A GET is not a state change; blocking it would break image tags."""
    response = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200


# ---- WR-16: the reload handoff ------------------------------------------


def test_startup_project_environment_variable_opens_a_project(project_dir, monkeypatch):
    """WR-16: `serve --reload` can only pass the project through the env.

    uvicorn's reloader re-imports the app in a fresh process, so the
    project cannot be set on an app object the parent built. Passing an app
    instance with ``reload=True`` made uvicorn log a warning and disable
    reload entirely — the flag was advertised in ``--help`` and did nothing.
    """
    from comiccolor.model import Project, Store
    from comiccolor.web.app import create_app
    from comiccolor.web.appconfig import PROJECT_DB_NAME

    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.add_project(Project(name=project_dir.name))

    monkeypatch.setenv("COMICCOLOR_PROJECT", str(project_dir))

    from fastapi.testclient import TestClient

    with TestClient(create_app()) as test_client:
        response = test_client.get("/api/projects/current")

    assert response.status_code == 200
    assert response.json()["name"] == project_dir.name


def test_no_startup_project_means_no_project_open(monkeypatch):
    """An empty or absent value is the normal case, not an error."""
    from fastapi.testclient import TestClient

    from comiccolor.web.app import create_app

    monkeypatch.setenv("COMICCOLOR_PROJECT", "")

    with TestClient(create_app()) as test_client:
        assert test_client.get("/api/projects/current").status_code == 409
