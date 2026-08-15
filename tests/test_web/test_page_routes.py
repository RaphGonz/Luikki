"""The page upload and stage-visibility contract, as tests.

PROJ-02 is "upload pages, add more over time, list preserved" — nothing
already on disk is disturbed by a later batch. PROJ-04 is "see each
page's stage; open any page," which is D-07 (a page is ``panels`` the
instant import completes) and D-11 (the stage chain is a registry an
artist can be shown, not a hardcoded frontend list) made visible over
HTTP. RESEARCH.md Pitfall 3 (server-generated filenames — never trust
``UploadFile.filename`` as a path component) and Pitfall 4 (malformed
uploads get a structured 4xx, never a bare 500) are both named here
because both are upload-handling mistakes this phase's threat model
specifically calls out.
"""

import io

from PIL import Image

from comiccolor.web.uploads import UPLOAD_ERROR_DETAIL


def _upload_png(client, volume_id, filename, width=8, height=8, colour=(9, 9, 9)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, "PNG")
    return client.post(
        f"/api/pages/?volume_id={volume_id}",
        files=[("files", (filename, buf.getvalue(), "image/png"))],
    )


def _make_volume(client, name="Chapter 1"):
    return client.post("/api/volumes/", json={"name": name}).json()["id"]


def test_upload_stores_a_server_generated_filename(client, project_dir):
    """PROJ-02, RESEARCH.md Pitfall 3 (T-01-PATH): every uploaded page lands
    on disk under a server-generated filename; the artist's own filename is
    kept for display only, never as a path component."""
    volume_id = _make_volume(client)

    response = _upload_png(client, volume_id, "../../evil.png")

    assert response.status_code == 201
    body = response.json()
    accepted = body["accepted"][0]
    assert accepted["original_name"] == "evil.png"

    pages_dir = project_dir / "pages"
    written = list(pages_dir.iterdir())
    assert len(written) == 1
    assert written[0].name != "evil.png"
    assert written[0].suffix == ".png"
    # UUID hex (32 lowercase hex chars) plus the extension, no path segments.
    stem = written[0].stem
    assert len(stem) == 32
    assert all(c in "0123456789abcdef" for c in stem)
    assert "." not in stem

    # Nothing was written outside the project's pages/ directory.
    assert not (project_dir / "evil.png").exists()
    assert not (project_dir.parent / "evil.png").exists()


def test_upload_rejects_a_non_image_with_4xx(client):
    """PROJ-02, RESEARCH.md Pitfall 4 (T-01-IMG): a file that is not a
    readable image is rejected with a 400 carrying the UI-SPEC error
    sentence, never a bare 500."""
    volume_id = _make_volume(client)

    response = client.post(
        f"/api/pages/?volume_id={volume_id}",
        files=[("files", ("notes.png", b"this is not an image", "image/png"))],
    )

    assert response.status_code == 400
    body = response.json()
    assert body["rejected"][0]["detail"] == UPLOAD_ERROR_DETAIL


def test_stage_field_is_panels_after_upload(client):
    """PROJ-04, D-07, D-11: every page reports a single stage value, which
    is ``panels`` the instant its upload completes."""
    volume_id = _make_volume(client)

    upload = _upload_png(client, volume_id, "page-01.png")
    accepted = upload.json()["accepted"][0]
    assert accepted["stage"] == "panels"

    detail = client.get(f"/api/pages/{accepted['id']}")
    assert detail.status_code == 200
    assert detail.json()["stage"] == "panels"


def test_adding_pages_later_preserves_existing_pages(client):
    """PROJ-02: uploading a second batch of pages to a volume leaves every
    page from the first batch exactly where it was."""
    volume_id = _make_volume(client)

    first_batch = client.post(
        f"/api/pages/?volume_id={volume_id}",
        files=[
            ("files", ("p1.png", _png_bytes(), "image/png")),
            ("files", ("p2.png", _png_bytes(), "image/png")),
        ],
    ).json()["accepted"]

    second_batch = client.post(
        f"/api/pages/?volume_id={volume_id}",
        files=[
            ("files", ("p3.png", _png_bytes(), "image/png")),
            ("files", ("p4.png", _png_bytes(), "image/png")),
        ],
    ).json()["accepted"]

    listing = client.get(f"/api/pages/?volume_id={volume_id}").json()
    assert len(listing) == 4
    assert [p["index"] for p in listing] == [0, 1, 2, 3]

    for original, listed in zip(first_batch + second_batch, listing):
        assert original["id"] == listed["id"]
        assert original["index"] == listed["index"]
        assert original["original_name"] == listed["original_name"]


def test_volume_crud_round_trip(client):
    """D-03: an artist creates, renames and deletes volumes and files pages
    into them."""
    create = client.post("/api/volumes/", json={"name": "Chapter 1"})
    assert create.status_code == 201
    volume_id = create.json()["id"]

    duplicate = client.post("/api/volumes/", json={"name": "Chapter 1"})
    assert duplicate.status_code == 409

    rename = client.patch(f"/api/volumes/{volume_id}", json={"name": "Chapter 1 (final)"})
    assert rename.status_code == 200
    assert rename.json()["name"] == "Chapter 1 (final)"

    listing = client.get("/api/volumes/").json()
    assert any(v["name"] == "Chapter 1 (final)" for v in listing)

    delete = client.delete(f"/api/volumes/{volume_id}")
    assert delete.status_code == 204

    listing_after = client.get("/api/volumes/").json()
    assert all(v["id"] != volume_id for v in listing_after)


def test_pipeline_stages_endpoint_lists_eight_stages(blank_client):
    """PROJ-04, D-11, RESEARCH.md § Architecture Patterns Pattern 5: the
    eight-stage chain and each stage's runner availability are served from
    the registry, never hardcoded in the frontend, and the endpoint answers
    with no project open."""
    response = blank_client.get("/api/pipeline/stages")

    assert response.status_code == 200
    stages = response.json()
    assert [s["name"] for s in stages] == [
        "import",
        "panels",
        "protected",
        "zones",
        "propose",
        "snap",
        "review",
        "export",
    ]
    assert sum(1 for s in stages if s["has_runner"]) == 1
    assert stages[0]["has_runner"] is True


def test_a_bad_file_does_not_lose_the_good_ones(client):
    """PROJ-02, RESEARCH.md Pitfall 4: a mixed batch returns both accepted
    and rejected populated, and the good page is persisted."""
    volume_id = _make_volume(client)

    response = client.post(
        f"/api/pages/?volume_id={volume_id}",
        files=[
            ("files", ("good.png", _png_bytes(), "image/png")),
            ("files", ("bad.png", b"not an image", "image/png")),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["accepted"]) == 1
    assert len(body["rejected"]) == 1

    listing = client.get(f"/api/pages/?volume_id={volume_id}").json()
    assert len(listing) == 1
    assert listing[0]["id"] == body["accepted"][0]["id"]


def test_page_image_is_served_from_inside_the_project_folder(client):
    """T-01-SERVE: ``GET /api/pages/{id}/image`` returns 200 and the bytes
    round-trip through Pillow; a nonexistent id returns 404 with
    PAGE_NOT_FOUND_DETAIL."""
    volume_id = _make_volume(client)
    accepted = _upload_png(client, volume_id, "page.png").json()["accepted"][0]

    response = client.get(f"/api/pages/{accepted['id']}/image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    image = Image.open(io.BytesIO(response.content))
    image.verify()

    missing = client.get("/api/pages/999999/image")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "That page no longer exists — refresh and try again."


def _png_bytes(width=8, height=8, colour=(9, 9, 9)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, "PNG")
    return buf.getvalue()


def test_upload_to_an_unknown_volume_is_a_404_and_writes_nothing(client, project_dir):
    """CR-03: ``volume_id`` is checked before a byte reaches ``pages/``.

    ``volume_id`` arrives as a raw query parameter. Before the fix it was
    never checked, so an unknown id reached ``store.add_page`` as a
    foreign-key violation — a bare 500 — *after* ``save_upload`` had
    already written the image, leaving a file with no row pointing at it.
    """
    response = _upload_png(client, 9999, "page.png")

    assert response.status_code == 404
    assert list((project_dir / "pages").iterdir()) == []


def test_a_failed_batch_leaves_no_orphan_files(client, project_dir):
    """The same guarantee across a multi-file batch.

    A mid-batch abort used to persist the pages accepted earlier in the
    request without reporting them, while later files were never processed
    at all — the module's "a bad file in a batch is reported in `rejected`
    without losing the good ones" promise failing in the one direction the
    artist cannot see.
    """
    import io

    from PIL import Image

    def png(colour):
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), colour).save(buf, "PNG")
        return buf.getvalue()

    response = client.post(
        "/api/pages/?volume_id=9999",
        files=[
            ("files", ("a.png", png((1, 1, 1)), "image/png")),
            ("files", ("b.png", png((2, 2, 2)), "image/png")),
        ],
    )

    assert response.status_code == 404
    assert list((project_dir / "pages").iterdir()) == []


def test_page_image_is_a_404_when_the_file_is_gone(client, project_dir):
    """WR-03: a page image moved or deleted outside the app is not a 500.

    D-04's "copy the folder, hand it over" model actively encourages the
    artist to touch these files directly, so this is a routine state.
    Starlette's ``FileResponse`` raises at send time for a missing file,
    which is why the existence check has to happen in the handler.
    """
    volume_id = _make_volume(client)
    page = _upload_png(client, volume_id, "page.png").json()["accepted"][0]

    assert client.get(page["image_url"]).status_code == 200

    for stray in (project_dir / "pages").iterdir():
        stray.unlink()

    response = client.get(page["image_url"])
    assert response.status_code == 404


def test_all_rejected_batch_reports_every_file(client):
    """WR-17: the 400 body is the declared ``PageUploadRejection`` shape."""
    response = client.post(
        f"/api/pages/?volume_id={_make_volume(client)}",
        files=[("files", ("notes.txt", b"not an image", "text/plain"))],
    )

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"detail", "rejected"}
    assert body["rejected"] == [
        {"filename": "notes.txt", "detail": UPLOAD_ERROR_DETAIL}
    ]


def test_upload_rejection_shape_is_in_the_openapi_contract(client):
    """The 400 shape is discoverable, not just observed in practice."""
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/api/pages/"]["post"]["responses"]

    assert "400" in responses
    ref = responses["400"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/PageUploadRejection")
