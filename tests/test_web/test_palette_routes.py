"""The palette-construction contract, as tests.

The first three stubs (PAL-01, PAL-03, PAL-04) are the swatch-and-hand
half of palette construction — extraction from a single flat swatch,
manual CRUD, and D-09's "recolour is never a stage regression." The
final four (PROJ-03, PAL-02) are the character-sheet proposal half:
D-05's zero-prompt upload with binding deferred to accept time, and the
resolved Open Question 2 answer that unaccepted sheets live only on
disk, as files, until accepted. ``test_sheet_id_with_path_separators_is_rejected``
covers Security Domain V12 (T-01-PATH): 01-VALIDATION.md's
``::test_sheet_upload`` reference in its Requirement → Test Map resolves
to ``test_sheet_upload_returns_unpersisted_proposals`` below — the two
documents stay reconcilable under that name, not a separate alias.
"""

def test_swatch_upload_creates_colour_n_entries(client, make_png):
    """PAL-01, D-12, D-16: a swatch image produces named palette entries
    built exactly from its colour chips, auto-named ``Colour 1..N``, and
    they land on the same grid ``GET /api/palette`` returns."""
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    png = make_png(40, 40, colours)

    resp = client.post(
        "/api/palette/swatch", files={"file": ("chips.png", png, "image/png")}
    )

    assert resp.status_code == 201
    entries = resp.json()["entries"]
    assert sorted(e["label"] for e in entries) == [
        "Colour 1",
        "Colour 2",
        "Colour 3",
        "Colour 4",
    ]
    assert sorted(tuple(e["rgb"]) for e in entries) == sorted(colours)

    listed = client.get("/api/palette").json()
    assert len(listed) == 4


def test_hand_crud_round_trip(client, make_png):
    """PAL-03, D-15: an artist can create, rename, recolour and delete a
    palette entry entirely by hand, on the same screen as the extraction
    result — including deleting an entry that was extracted seconds
    earlier."""
    swatch = client.post(
        "/api/palette/swatch",
        files={"file": ("chips.png", make_png(20, 20, [(10, 20, 30)]), "image/png")},
    )
    extracted_id = swatch.json()["entries"][0]["id"]

    created = client.post(
        "/api/palette", json={"rgb": [1, 2, 3], "label": "Hand entry"}
    ).json()
    assert created["label"] == "Hand entry"

    renamed = client.patch(
        f"/api/palette/{created['id']}", json={"label": "Renamed entry"}
    ).json()
    assert renamed["entry"]["label"] == "Renamed entry"
    assert renamed["entry"]["rgb"] == [1, 2, 3]

    recoloured = client.patch(
        f"/api/palette/{created['id']}", json={"rgb": [4, 5, 6]}
    ).json()
    assert recoloured["entry"]["rgb"] == [4, 5, 6]
    assert recoloured["entry"]["revision"] == 1

    # D-15: add and delete work on an entry extracted seconds earlier, not
    # just on hand-created ones — the "same screen" contract in practice.
    assert client.delete(f"/api/palette/{extracted_id}").status_code == 204
    assert client.delete(f"/api/palette/{created['id']}").status_code == 204
    assert client.get("/api/palette").json() == []


def test_recolour_reports_affected_pages_and_leaves_stage_alone(client, project_dir):
    """PAL-04, D-09: changing a palette entry's colour returns the number
    of pages affected and touches no region row and no page stage — a
    recolour is never a stage regression, at any stage."""
    from comiccolor.model import PaletteEntry, Panel, Page, Region, RegionStatus, Store, Volume
    from comiccolor.web.appconfig import PROJECT_DB_NAME

    with Store(project_dir / PROJECT_DB_NAME) as store:
        project = store.the_project()
        volume = store.add_volume(Volume(project_id=project.id, name="Volume 1"))
        page = store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
        original_stage = page.stage
        panel_a = store.add_panel(
            Panel(page_id=page.id, x=0, y=0, width=10, height=10, reading_order=0)
        )
        panel_b = store.add_panel(
            Panel(page_id=page.id, x=10, y=0, width=10, height=10, reading_order=1)
        )
        entry = store.add_palette_entry(
            PaletteEntry(project_id=project.id, rgb=(200, 150, 90), label="hair")
        )
        store.add_regions(
            [
                Region(panel_id=panel_a.id, label=1, palette_entry_id=entry.id),
                Region(panel_id=panel_b.id, label=1, palette_entry_id=entry.id),
            ]
        )

    resp = client.patch(f"/api/palette/{entry.id}", json={"rgb": [10, 20, 30]})

    assert resp.status_code == 200
    body = resp.json()
    # The toast counts pages, not panels — two panels on one page referencing
    # the entry is still one affected page.
    assert body["pages_affected"] == 1
    assert body["entry"]["rgb"] == [10, 20, 30]
    assert body["entry"]["revision"] == entry.revision + 1

    with Store(project_dir / PROJECT_DB_NAME) as store:
        reread_page = store.page_by_id(page.id)
        assert reread_page.stage == original_stage
        for panel_id in (panel_a.id, panel_b.id):
            for region in store.regions_for_panel(panel_id):
                assert region.palette_entry_id == entry.id
                assert region.status is RegionStatus.AUTO


def test_a_second_swatch_continues_the_numbering(client, make_png):
    """D-16: a second swatch upload continues the auto-name numbering
    (``Colour 5`` onward) rather than restarting at ``Colour 1``."""
    colours = [(255, 0, 0), (0, 255, 0)]
    first = client.post(
        "/api/palette/swatch",
        files={"file": ("a.png", make_png(20, 20, colours), "image/png")},
    ).json()
    assert sorted(e["label"] for e in first["entries"]) == ["Colour 1", "Colour 2"]

    second = client.post(
        "/api/palette/swatch",
        files={"file": ("b.png", make_png(20, 20, colours), "image/png")},
    ).json()
    assert sorted(e["label"] for e in second["entries"]) == ["Colour 3", "Colour 4"]


def test_deleting_a_colour_leaves_its_regions_unpainted_not_wrong(client, project_dir):
    """CLAUDE.md's non-negotiable, exercised at the HTTP layer: after a
    delete, the regions that referenced the entry are unpainted
    (``palette_entry_id`` is ``NULL``), and no RGB value has been written
    anywhere outside ``palette_entry`` — ``Region`` has no RGB field at
    all to write one into."""
    from comiccolor.model import PaletteEntry, Panel, Page, Region, Store, Volume
    from comiccolor.web.appconfig import PROJECT_DB_NAME

    with Store(project_dir / PROJECT_DB_NAME) as store:
        project = store.the_project()
        volume = store.add_volume(Volume(project_id=project.id, name="Volume 1"))
        page = store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
        panel = store.add_panel(
            Panel(page_id=page.id, x=0, y=0, width=10, height=10, reading_order=0)
        )
        entry = store.add_palette_entry(
            PaletteEntry(project_id=project.id, rgb=(9, 9, 9), label="prop")
        )
        store.add_regions([Region(panel_id=panel.id, label=1, palette_entry_id=entry.id)])

    resp = client.delete(f"/api/palette/{entry.id}")
    assert resp.status_code == 204

    with Store(project_dir / PROJECT_DB_NAME) as store:
        region = store.regions_for_panel(panel.id)[0]
        assert region.palette_entry_id is None


def _sheet_bytes():
    """A synthetic character sheet: an ink band, a paper band, and two flat
    character colours — exactly the shape D-14's pre-pass is meant to
    separate."""
    import io

    from PIL import Image, ImageDraw

    width, height = 80, 80
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 19], fill=(8, 8, 8))  # ink band
    draw.rectangle([0, 20, width, 39], fill=(200, 120, 60))  # character colour 1
    draw.rectangle([0, 40, width, 59], fill=(40, 60, 160))  # character colour 2
    draw.rectangle([0, 60, width, 79], fill=(250, 250, 250))  # paper band

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_sheet_upload_returns_unpersisted_proposals(client, make_png):
    """PROJ-03, PAL-02, D-05, D-14: uploading a character sheet is one
    drag-and-drop with zero prompts; the app proposes palette entries
    extracted from it — the two character colours only, ink and paper
    dropped first — and nothing is written to the database until the
    artist accepts. Proposals live only in the HTTP response."""
    resp = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", _sheet_bytes(), "image/png")},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert len(body["proposals"]) == 2
    assert sorted(tuple(p["rgb"]) for p in body["proposals"]) == [
        (40, 60, 160),
        (200, 120, 60),
    ]
    assert {p["index"] for p in body["proposals"]} == {0, 1}

    # D-05: nothing is persisted by the upload alone.
    assert client.get("/api/palette").json() == []

    from comiccolor.model import Store
    from comiccolor.web.appconfig import PROJECT_DB_NAME

    project_dir = client.app.state.current_project_path
    with Store(project_dir / PROJECT_DB_NAME) as store:
        project = store.the_project()
        assert store.palette_for_project(project.id) == []
        assert store.entities_for_project(project.id) == []


def test_accept_creates_entity_and_labelled_entries(client, make_png):
    """PAL-02, D-05: the artist accepts two proposals under one character
    name; that creates exactly one Entity and two labelled PaletteEntry
    rows, copies the sheet file into references/ with the path recorded on
    the entity, and a second sheet for the same character reuses that
    entity rather than duplicating it.

    The file is *copied*, not moved: the pending sheet stays available so a
    partial accept can be followed by another one (see
    ``test_partial_accept_leaves_the_rest_acceptable``). ``DELETE
    /sheets/{id}`` is what clears pending/."""
    sheet = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", _sheet_bytes(), "image/png")},
    ).json()

    resp = client.post(
        f"/api/references/sheets/{sheet['sheet_id']}/accept",
        json={
            "character_name": "Kaito",
            "items": [{"index": 0, "part": "hair"}, {"index": 1, "part": "eyes"}],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert sorted(e["label"] for e in body["entries"]) == [
        "Kaito / eyes",
        "Kaito / hair",
    ]
    assert all(e["entity_id"] == body["entity_id"] for e in body["entries"])

    listed = client.get("/api/palette").json()
    assert sorted(e["label"] for e in listed) == ["Kaito / eyes", "Kaito / hair"]

    from comiccolor.model import Store
    from comiccolor.web.appconfig import PROJECT_DB_NAME

    project_dir = client.app.state.current_project_path
    # Copied, not moved: the pending sheet survives the accept, and the
    # bound reference image exists independently in references/.
    assert len(list((project_dir / "references" / "pending").iterdir())) == 1
    references = [
        p for p in (project_dir / "references").iterdir() if p.is_file()
    ]
    assert len(references) == 1
    with Store(project_dir / PROJECT_DB_NAME) as store:
        project = store.the_project()
        entities = store.entities_for_project(project.id)
        assert len(entities) == 1
        assert len(entities[0].reference_images) == 1

    # A second sheet for "Kaito" reuses the same entity and appends a
    # second reference path, rather than creating a duplicate character.
    sheet_2 = client.post(
        "/api/references/sheets",
        files={"file": ("sheet2.png", _sheet_bytes(), "image/png")},
    ).json()
    client.post(
        f"/api/references/sheets/{sheet_2['sheet_id']}/accept",
        json={"character_name": "Kaito", "items": [{"index": 0, "part": "cape"}]},
    )
    with Store(project_dir / PROJECT_DB_NAME) as store:
        project = store.the_project()
        entities = store.entities_for_project(project.id)
        assert len(entities) == 1
        assert len(entities[0].reference_images) == 2


def test_reject_discards_the_pending_sheet(client, make_png):
    """PAL-02: rejecting a whole sheet discards it — the delete is
    idempotent, no palette entry was ever created, and a subset accept
    leaves the unlisted proposals with no database trace at all, since
    nothing about them was ever persisted in the first place."""
    sheet = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", _sheet_bytes(), "image/png")},
    ).json()
    project_dir = client.app.state.current_project_path
    pending_dir = project_dir / "references" / "pending"

    assert list(pending_dir.iterdir())

    resp = client.delete(f"/api/references/sheets/{sheet['sheet_id']}")
    assert resp.status_code == 204
    assert not list(pending_dir.iterdir())

    # Idempotent — discarding an already-gone sheet is still a clean 204.
    assert client.delete(f"/api/references/sheets/{sheet['sheet_id']}").status_code == 204
    assert client.get("/api/palette").json() == []

    # Accepting only one of two proposals leaves the other with no trace —
    # this is what "reject each proposal individually" means when nothing
    # was ever written for either one.
    sheet_2 = client.post(
        "/api/references/sheets",
        files={"file": ("sheet2.png", _sheet_bytes(), "image/png")},
    ).json()
    client.post(
        f"/api/references/sheets/{sheet_2['sheet_id']}/accept",
        json={"character_name": "Mira", "items": [{"index": 0, "part": "hair"}]},
    )
    listed = client.get("/api/palette").json()
    assert [e["label"] for e in listed] == ["Mira / hair"]


def test_sheet_id_with_path_separators_is_rejected(client, project_dir, make_png):
    """Security Domain V12, T-01-PATH: a sheet id containing a path
    separator or traversal segment is rejected before it touches the
    filesystem — always a 404, never a 500 or a filesystem error — and
    ``project.db`` survives untouched.

    ``sheet_id`` is a single-segment path parameter, so any id containing
    a literal or percent-encoded ``/`` (``../../project``,
    ``..%2F..%2Fproject.db``, ``a/b``) fails to match this route's shape at
    the ASGI routing layer itself, before ``_validate_sheet_id`` — or any
    of this module's own code — ever runs; Starlette's own generic 404
    fires instead of ``SHEET_NOT_FOUND_DETAIL``. That is T-01-SHEETID's
    mitigation holding even more strongly than the module's own validation
    alone: those payloads never reach a single line of this project's code.
    A same-shape id that is merely the wrong length (one character short
    of the required 32-hex shape) *does* reach ``_validate_sheet_id`` and
    is rejected there, with the module's own neutral copy — proving that
    code path directly.
    """
    from comiccolor.web.appconfig import PROJECT_DB_NAME
    from comiccolor.web.routers.reference import SHEET_NOT_FOUND_DETAIL

    unroutable_ids = ["../../project", "..%2F..%2Fproject.db", "a/b"]
    short_hex_id = "a" * 31  # one character short of the required 32-hex shape

    for bad_id in unroutable_ids:
        assert client.get(f"/api/references/sheets/{bad_id}/image").status_code == 404
        assert client.delete(f"/api/references/sheets/{bad_id}").status_code == 404
        resp = client.post(
            f"/api/references/sheets/{bad_id}/accept",
            json={"character_name": "Kaito", "items": [{"index": 0, "part": "hair"}]},
        )
        assert resp.status_code == 404

    image_resp = client.get(f"/api/references/sheets/{short_hex_id}/image")
    assert image_resp.status_code == 404
    assert image_resp.json()["detail"] == SHEET_NOT_FOUND_DETAIL

    delete_resp = client.delete(f"/api/references/sheets/{short_hex_id}")
    assert delete_resp.status_code == 404
    assert delete_resp.json()["detail"] == SHEET_NOT_FOUND_DETAIL

    accept_resp = client.post(
        f"/api/references/sheets/{short_hex_id}/accept",
        json={"character_name": "Kaito", "items": [{"index": 0, "part": "hair"}]},
    )
    assert accept_resp.status_code == 404
    assert accept_resp.json()["detail"] == SHEET_NOT_FOUND_DETAIL

    assert (project_dir / PROJECT_DB_NAME).is_file()


def test_proposals_are_stable_across_two_uploads_of_the_same_file(client, make_png):
    """The determinism the whole ephemeral-proposal design rests on:
    uploading the same bytes twice yields the same proposal RGB values in
    the same order. The accept route re-derives proposals by index from
    the file alone, so a non-deterministic extractor would mis-bind an
    artist's choices to the wrong colour."""
    payload = _sheet_bytes()

    first = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", payload, "image/png")},
    ).json()
    second = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", payload, "image/png")},
    ).json()

    assert [p["rgb"] for p in first["proposals"]] == [
        p["rgb"] for p in second["proposals"]
    ]


def test_partial_accept_leaves_the_rest_acceptable(client, make_png):
    """CR-04: accepting 1 of 2 proposals must not consume the sheet.

    ``accept_sheet`` can only re-derive proposals from the *pending* file,
    so moving that file out of ``pending/`` on the first accept made the
    second one 404 — while ``palette.ts`` went on rendering the remaining
    proposal as a live, clickable card. Reproduced before the fix as
    201 then 404.
    """
    sheet = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", _sheet_bytes(), "image/png")},
    ).json()
    assert len(sheet["proposals"]) >= 2

    first = client.post(
        f"/api/references/sheets/{sheet['sheet_id']}/accept",
        json={"character_name": "Kaito", "items": [{"index": 0, "part": "hair"}]},
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/references/sheets/{sheet['sheet_id']}/accept",
        json={"character_name": "Kaito", "items": [{"index": 1, "part": "eyes"}]},
    )
    assert second.status_code == 201

    listed = client.get("/api/palette").json()
    assert sorted(e["label"] for e in listed) == ["Kaito / eyes", "Kaito / hair"]

    # One entity, and the same reference image recorded once — not once
    # per partial accept.
    from comiccolor.model import Store
    from comiccolor.web.appconfig import PROJECT_DB_NAME

    project_dir = client.app.state.current_project_path
    with Store(project_dir / PROJECT_DB_NAME) as store:
        entities = store.entities_for_project(store.the_project().id)
        assert len(entities) == 1
        assert len(entities[0].reference_images) == 1

    # The sheet image is still served, and discard is still what clears it.
    assert client.get(f"/api/references/sheets/{sheet['sheet_id']}/image").status_code == 200
    assert client.delete(f"/api/references/sheets/{sheet['sheet_id']}").status_code == 204
    assert not list((project_dir / "references" / "pending").iterdir())


def test_accepting_nothing_is_refused(client, make_png):
    """CR-04: an empty ``items`` list used to consume the sheet silently.

    It returned 201, created an ``Entity`` with zero palette entries, and
    emptied ``pending/`` — the artist's uploaded sheet gone with nothing to
    show for it. "I don't want any of these" is ``DELETE /sheets/{id}``.
    """
    from comiccolor.web.routers.reference import NO_ITEMS_DETAIL

    sheet = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", _sheet_bytes(), "image/png")},
    ).json()

    resp = client.post(
        f"/api/references/sheets/{sheet['sheet_id']}/accept",
        json={"character_name": "Kaito", "items": []},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == NO_ITEMS_DETAIL
    assert client.get("/api/palette").json() == []

    project_dir = client.app.state.current_project_path
    assert len(list((project_dir / "references" / "pending").iterdir())) == 1

    from comiccolor.model import Store
    from comiccolor.web.appconfig import PROJECT_DB_NAME

    with Store(project_dir / PROJECT_DB_NAME) as store:
        assert store.entities_for_project(store.the_project().id) == []


def test_duplicate_proposal_index_is_refused(client, make_png):
    """WR-18: two items with the same index wrote two identical entries.

    Same rgb, same label, same entity_id, and no uniqueness constraint on
    ``palette_entry`` to catch it. Reproduced before the fix as a 201 with
    two ``Kaito / hair`` rows.
    """
    from comiccolor.web.routers.reference import DUPLICATE_INDEX_DETAIL

    sheet = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", _sheet_bytes(), "image/png")},
    ).json()

    resp = client.post(
        f"/api/references/sheets/{sheet['sheet_id']}/accept",
        json={
            "character_name": "Kaito",
            "items": [{"index": 0, "part": "hair"}, {"index": 0, "part": "fringe"}],
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == DUPLICATE_INDEX_DETAIL
    assert client.get("/api/palette").json() == []


def test_duplicate_part_name_is_refused(client, make_png):
    """WR-18: two different colours must not become the same label.

    ``_entry_label``'s docstring promises "two distinct labels under one
    entity, never a collision" — that only holds if the parts differ, which
    is what this checks. Case and surrounding whitespace do not make two
    parts distinct.
    """
    from comiccolor.web.routers.reference import DUPLICATE_PART_DETAIL

    sheet = client.post(
        "/api/references/sheets",
        files={"file": ("sheet.png", _sheet_bytes(), "image/png")},
    ).json()

    resp = client.post(
        f"/api/references/sheets/{sheet['sheet_id']}/accept",
        json={
            "character_name": "Kaito",
            "items": [{"index": 0, "part": "hair"}, {"index": 1, "part": " Hair "}],
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == DUPLICATE_PART_DETAIL
    assert client.get("/api/palette").json() == []


def test_a_degenerate_sheet_leaves_no_unreachable_file(client, make_png):
    """WR-06: a rejected sheet must not strand bytes in ``pending/``.

    ``save_upload`` used to run before ``extract_palette``. An all-ink or
    all-paper sheet raises ``EmptyImageError`` -> 400, and that response
    carries no ``sheet_id``, so the client could never name the file in a
    ``DELETE``. The file was unreachable and permanent. Reproduced before
    the fix as pending/ going 0 -> 1 on a 400.
    """
    project_dir = client.app.state.current_project_path
    pending_dir = project_dir / "references" / "pending"
    assert list(pending_dir.iterdir()) == []

    flat = make_png(32, 32, [(255, 255, 255)])
    resp = client.post(
        "/api/references/sheets", files={"file": ("blank.png", flat, "image/png")}
    )

    assert resp.status_code == 400
    assert "sheet_id" not in resp.json()
    assert list(pending_dir.iterdir()) == []
