"""The §3 invariants, as tests.

The point of most of these is that the *schema* prevents the mistake, so the
assertions are about what is impossible rather than what is computed.
"""

import shutil
import sqlite3

import pytest

from comiccolor.model import (
    Entity,
    Page,
    PaletteEntry,
    Panel,
    PipelineStage,
    Project,
    Region,
    RegionStatus,
    Store,
    Volume,
)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s


@pytest.fixture
def project(store):
    return store.add_project(Project(name="Kaito"))


@pytest.fixture
def volume(store, project):
    return store.add_volume(Volume(project_id=project.id, name="v1"))


@pytest.fixture
def panel(store, volume):
    page = store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
    return store.add_panel(
        Panel(page_id=page.id, x=0, y=0, width=100, height=100, reading_order=0)
    )


def test_region_table_has_no_rgb_column(store):
    """§9: do not bake RGB into regions. Enforced by the schema."""
    columns = {row[1] for row in store.conn.execute("PRAGMA table_info(region)")}
    assert not columns & {"r", "g", "b", "rgb", "colour", "color"}
    assert "palette_entry_id" in columns


def test_rgb_lives_only_on_palette_entry(store):
    tables = [
        row[0]
        for row in store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    ]
    holders = []
    for table in tables:
        columns = {row[1] for row in store.conn.execute(f"PRAGMA table_info({table})")}
        if columns & {"r", "g", "b"}:
            holders.append(table)
    assert holders == ["palette_entry"]


def test_palette_lives_at_project_scope(store):
    """D-02: a palette entry (and an entity) cannot be scoped to a volume
    even by accident — that is what lets the palette accumulate across the
    whole project."""
    palette_columns = {
        row[1] for row in store.conn.execute("PRAGMA table_info(palette_entry)")
    }
    entity_columns = {row[1] for row in store.conn.execute("PRAGMA table_info(entity)")}
    assert "project_id" in palette_columns
    assert "volume_id" not in palette_columns
    assert "project_id" in entity_columns
    assert "volume_id" not in entity_columns


def test_a_project_db_holds_one_project(store, project):
    """D-04: a project folder holds exactly one project, enforced by the
    schema's ``CHECK (id = 1)`` rather than checked by a caller."""
    with pytest.raises(sqlite3.IntegrityError):
        store.add_project(Project(name="Second Project"))


def test_page_stage_defaults_to_panels(store, volume):
    """D-07: a successful upload auto-advances a page past import — there is
    nothing for the artist to review at that boundary yet."""
    page = store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
    reread = store.page_by_id(page.id)
    assert reread.stage is PipelineStage.PANELS


def test_palette_edit_is_a_single_row_update(store, project, panel):
    entry = store.add_palette_entry(
        PaletteEntry(project_id=project.id, rgb=(200, 150, 90), label="Kaito / hair / base")
    )
    store.add_regions(
        [
            Region(panel_id=panel.id, label=1, palette_entry_id=entry.id),
            Region(panel_id=panel.id, label=2, palette_entry_id=entry.id),
        ]
    )

    revision = store.update_palette_rgb(entry.id, (10, 20, 30))

    assert revision == entry.revision + 1
    # No region row was touched: they never held the colour to begin with.
    for region in store.regions_for_panel(panel.id):
        assert region.palette_entry_id == entry.id
        assert region.status is RegionStatus.AUTO
    assert store.palette_for_project(project.id)[0].rgb == (10, 20, 30)


def test_panels_affected_by_is_the_repaint_set(store, project, panel):
    hair = store.add_palette_entry(
        PaletteEntry(project_id=project.id, rgb=(0, 0, 0), label="hair")
    )
    skin = store.add_palette_entry(
        PaletteEntry(project_id=project.id, rgb=(1, 1, 1), label="skin")
    )
    store.add_regions([Region(panel_id=panel.id, label=1, palette_entry_id=hair.id)])

    assert store.panels_affected_by(hair.id) == [panel.id]
    assert store.panels_affected_by(skin.id) == []


def test_one_label_per_panel_is_unique(store, panel):
    store.add_regions([Region(panel_id=panel.id, label=1)])
    with pytest.raises(sqlite3.IntegrityError):
        store.add_regions([Region(panel_id=panel.id, label=1)])


def test_reassignment_marks_the_region_manual(store, project, panel):
    entry = store.add_palette_entry(
        PaletteEntry(project_id=project.id, rgb=(5, 5, 5), label="cloak")
    )
    region = store.add_regions([Region(panel_id=panel.id, label=1)])[0]

    store.assign_palette(region.id, entry.id)

    updated = store.regions_for_panel(panel.id)[0]
    assert updated.palette_entry_id == entry.id
    assert updated.status is RegionStatus.MANUAL


def test_deleting_a_palette_entry_orphans_rather_than_corrupts(store, project, panel):
    """Exercises ``Store.delete_palette_entry``, which relies on the schema's
    ``region.palette_entry_id ... ON DELETE SET NULL``."""
    entry = store.add_palette_entry(
        PaletteEntry(project_id=project.id, rgb=(9, 9, 9), label="prop")
    )
    store.add_regions([Region(panel_id=panel.id, label=1, palette_entry_id=entry.id)])

    store.delete_palette_entry(entry.id)

    # An unpainted region is recoverable; a wrong colour silently baked in is not.
    assert store.regions_for_panel(panel.id)[0].palette_entry_id is None


# ---- Store surface added for the web layer (plans 01-06..01-09) -----------


def test_next_page_index_appends_after_existing_pages(store, volume):
    """PROJ-02: adding pages weeks later appends rather than collides with
    the ``UNIQUE (volume_id, idx)`` constraint."""
    assert store.next_page_index(volume.id) == 0
    store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
    store.add_page(Page(volume_id=volume.id, source_path="p2.png", index=1))
    assert store.next_page_index(volume.id) == 2


def test_set_page_stage_persists_and_reads_back_as_enum(store, volume):
    page = store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
    store.set_page_stage(page.id, PipelineStage.ZONES)
    reread = store.page_by_id(page.id)
    assert reread.stage is PipelineStage.ZONES


def test_pages_affected_by_counts_pages_not_panels(store, project, volume):
    """The UI-SPEC recolour toast reads "Updated on {N} page{s}" — two
    panels on one page referencing the same entry must count as one page."""
    entry = store.add_palette_entry(
        PaletteEntry(project_id=project.id, rgb=(3, 3, 3), label="ink")
    )
    page = store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
    panel_a = store.add_panel(
        Panel(page_id=page.id, x=0, y=0, width=10, height=10, reading_order=0)
    )
    panel_b = store.add_panel(
        Panel(page_id=page.id, x=10, y=0, width=10, height=10, reading_order=1)
    )
    store.add_regions(
        [
            Region(panel_id=panel_a.id, label=1, palette_entry_id=entry.id),
            Region(panel_id=panel_b.id, label=1, palette_entry_id=entry.id),
        ]
    )

    assert store.pages_affected_by(entry.id) == [page.id]


def test_renaming_a_volume_keeps_its_pages(store, volume):
    page = store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
    store.rename_volume(volume.id, "v2")
    assert store.page_by_id(page.id) is not None
    volumes = store.volumes_for_project(volume.project_id)
    assert [v.name for v in volumes] == ["v2"]


def test_entity_by_name_reuses_rather_than_duplicates(store, project):
    """Accepting a proposal for a character who already exists must reuse
    the row, not create a duplicate."""
    original = store.add_entity(Entity(project_id=project.id, name="Kaito"))
    found = store.entity_by_name(project.id, "Kaito")
    assert found.id == original.id
    assert store.entity_by_name(project.id, "Nobody") is None


# ---- WAL, busy timeout, checkpoint (Open Question 1, resolved) ------------


def test_journal_mode_is_wal(store):
    mode = store.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_checkpoint_truncates_the_wal_side_file(tmp_path):
    with Store(tmp_path / "test.db") as s:
        s.add_project(Project(name="Kaito"))
        wal_path = tmp_path / "test.db-wal"
        assert wal_path.exists()
        assert wal_path.stat().st_size > 0

        s.checkpoint()
        assert wal_path.stat().st_size == 0


def test_copying_the_folder_after_close_preserves_every_row(tmp_path):
    """D-04's portability promise, as an executable assertion."""
    original_dir = tmp_path / "original"
    with Store(original_dir / "project.db") as s:
        project = s.add_project(Project(name="Kaito"))
        volume = s.add_volume(Volume(project_id=project.id, name="v1"))
        s.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
        s.add_palette_entry(
            PaletteEntry(project_id=project.id, rgb=(1, 2, 3), label="hair")
        )

    copy_dir = tmp_path / "copy"
    shutil.copytree(original_dir, copy_dir)

    with Store(copy_dir / "project.db") as s:
        reread_project = s.the_project()
        pages = s.pages_for_volume(volume.id)
        palette = s.palette_for_project(reread_project.id)
        assert len(pages) == 1
        assert len(palette) == 1
        assert palette[0].rgb == (1, 2, 3)


def test_an_uncommitted_process_death_loses_nothing(tmp_path):
    """The automatable half of PROJ-05: a second Store opened on the same
    file without the first ever calling close() still sees committed work.
    The literal process-kill remains a manual UAT step per 01-VALIDATION.md.
    """
    db_path = tmp_path / "test.db"
    first = Store(db_path)
    project = first.add_project(Project(name="Kaito"))
    entry = first.add_palette_entry(
        PaletteEntry(project_id=project.id, rgb=(7, 7, 7), label="cloak")
    )

    second = Store(db_path)
    try:
        found = second.palette_entry_by_id(entry.id)
        assert found is not None
        assert found.rgb == (7, 7, 7)
    finally:
        second.close()
        # Deliberately not calling first.close() — that would checkpoint and
        # defeat the point of this test. Just release the raw connection.
        first.conn.close()
