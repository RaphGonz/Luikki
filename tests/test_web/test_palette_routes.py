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

import pytest


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


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-10")
def test_sheet_upload_returns_unpersisted_proposals():
    """PROJ-03, PAL-02, D-05: uploading a character sheet is one
    drag-and-drop with zero prompts; the app proposes palette entries
    extracted from it, and nothing is written to the database until the
    artist accepts — proposals live only in the HTTP response."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-10")
def test_accept_creates_entity_and_labelled_entries():
    """PAL-02, D-05: the artist accepts a proposal by naming the
    character and the part; the entry lands as ``{character} / {part}``
    and only then gets a database row."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-10")
def test_reject_discards_the_pending_sheet():
    """PAL-02: rejecting a proposal discards it; nothing about a
    rejected proposal persists anywhere."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-10")
def test_sheet_id_with_path_separators_is_rejected():
    """Security Domain V12, T-01-PATH: a sheet id containing a path
    separator or traversal segment is rejected before it touches the
    filesystem."""
    ...
