"""The §3 invariants, as tests.

The point of most of these is that the *schema* prevents the mistake, so the
assertions are about what is impossible rather than what is computed.
"""

import sqlite3

import pytest

from comiccolor.model import (
    Page,
    PaletteEntry,
    Panel,
    Region,
    RegionStatus,
    Series,
    Store,
    Volume,
)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s


@pytest.fixture
def volume(store):
    series = store.add_series(Series(name="Kaito"))
    return store.add_volume(Volume(series_id=series.id, name="v1"))


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


def test_palette_edit_is_a_single_row_update(store, volume, panel):
    entry = store.add_palette_entry(
        PaletteEntry(volume_id=volume.id, rgb=(200, 150, 90), label="Kaito / hair / base")
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
    assert store.palette_for_volume(volume.id)[0].rgb == (10, 20, 30)


def test_panels_affected_by_is_the_repaint_set(store, volume, panel):
    hair = store.add_palette_entry(
        PaletteEntry(volume_id=volume.id, rgb=(0, 0, 0), label="hair")
    )
    skin = store.add_palette_entry(
        PaletteEntry(volume_id=volume.id, rgb=(1, 1, 1), label="skin")
    )
    store.add_regions([Region(panel_id=panel.id, label=1, palette_entry_id=hair.id)])

    assert store.panels_affected_by(hair.id) == [panel.id]
    assert store.panels_affected_by(skin.id) == []


def test_one_label_per_panel_is_unique(store, panel):
    store.add_regions([Region(panel_id=panel.id, label=1)])
    with pytest.raises(sqlite3.IntegrityError):
        store.add_regions([Region(panel_id=panel.id, label=1)])


def test_reassignment_marks_the_region_manual(store, volume, panel):
    entry = store.add_palette_entry(
        PaletteEntry(volume_id=volume.id, rgb=(5, 5, 5), label="cloak")
    )
    region = store.add_regions([Region(panel_id=panel.id, label=1)])[0]

    store.assign_palette(region.id, entry.id)

    updated = store.regions_for_panel(panel.id)[0]
    assert updated.palette_entry_id == entry.id
    assert updated.status is RegionStatus.MANUAL


def test_deleting_a_palette_entry_orphans_rather_than_corrupts(store, volume, panel):
    entry = store.add_palette_entry(
        PaletteEntry(volume_id=volume.id, rgb=(9, 9, 9), label="prop")
    )
    store.add_regions([Region(panel_id=panel.id, label=1, palette_entry_id=entry.id)])

    store.conn.execute("PRAGMA foreign_keys = ON")
    store.conn.execute("DELETE FROM palette_entry WHERE id = ?", (entry.id,))
    store.conn.commit()

    # An unpainted region is recoverable; a wrong colour silently baked in is not.
    assert store.regions_for_panel(panel.id)[0].palette_entry_id is None
