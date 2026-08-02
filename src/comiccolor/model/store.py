"""SQLite persistence for the §3 data model.

The schema is deliberately narrow. Note there is no ``rgb`` column on
``region`` — the only place an RGB value exists in the database is
``palette_entry``. That is the §9 anti-pattern "do not bake RGB into regions"
enforced by the schema rather than by review.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .entities import (
    Entity,
    Page,
    PaletteEntry,
    Panel,
    ProtectedKind,
    ProtectedMask,
    Region,
    RegionStatus,
    Series,
    Volume,
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS series (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS volume (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id        INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    palette_revision INTEGER NOT NULL DEFAULT 0,
    UNIQUE (series_id, name)
);

CREATE TABLE IF NOT EXISTS page (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id   INTEGER NOT NULL REFERENCES volume(id) ON DELETE CASCADE,
    source_path TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    width       INTEGER NOT NULL DEFAULT 0,
    height      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (volume_id, idx)
);

CREATE TABLE IF NOT EXISTS panel (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id        INTEGER NOT NULL REFERENCES page(id) ON DELETE CASCADE,
    x              INTEGER NOT NULL,
    y              INTEGER NOT NULL,
    width          INTEGER NOT NULL,
    height         INTEGER NOT NULL,
    reading_order  INTEGER NOT NULL,
    label_map_path TEXT,
    polygon        TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS entity (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id        INTEGER NOT NULL REFERENCES volume(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    reference_images TEXT NOT NULL DEFAULT '[]',
    UNIQUE (volume_id, name)
);

CREATE TABLE IF NOT EXISTS palette_entry (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id INTEGER NOT NULL REFERENCES volume(id) ON DELETE CASCADE,
    r         INTEGER NOT NULL,
    g         INTEGER NOT NULL,
    b         INTEGER NOT NULL,
    label     TEXT NOT NULL,
    entity_id INTEGER REFERENCES entity(id) ON DELETE SET NULL,
    revision  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS region (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    panel_id         INTEGER NOT NULL REFERENCES panel(id) ON DELETE CASCADE,
    label            INTEGER NOT NULL,
    palette_entry_id INTEGER REFERENCES palette_entry(id) ON DELETE SET NULL,
    confidence       REAL,
    status           TEXT NOT NULL DEFAULT 'auto',
    area             INTEGER NOT NULL DEFAULT 0,
    bbox_x           INTEGER NOT NULL DEFAULT 0,
    bbox_y           INTEGER NOT NULL DEFAULT 0,
    bbox_w           INTEGER NOT NULL DEFAULT 0,
    bbox_h           INTEGER NOT NULL DEFAULT 0,
    UNIQUE (panel_id, label)
);

CREATE TABLE IF NOT EXISTS protected_mask (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    panel_id  INTEGER NOT NULL REFERENCES panel(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    mask_path TEXT NOT NULL,
    area      INTEGER NOT NULL DEFAULT 0,
    bbox_x    INTEGER NOT NULL DEFAULT 0,
    bbox_y    INTEGER NOT NULL DEFAULT 0,
    bbox_w    INTEGER NOT NULL DEFAULT 0,
    bbox_h    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_panel_page ON panel(page_id);
CREATE INDEX IF NOT EXISTS idx_region_panel ON region(panel_id);
CREATE INDEX IF NOT EXISTS idx_region_palette ON region(palette_entry_id);
CREATE INDEX IF NOT EXISTS idx_protected_panel ON protected_mask(panel_id);
CREATE INDEX IF NOT EXISTS idx_palette_volume ON palette_entry(volume_id);
"""


class Store:
    """Thin data-access layer. Not thread-safe; one Store per thread."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- Series / Volume / Page ----------------------------------------

    def add_series(self, series: Series) -> Series:
        cur = self.conn.execute("INSERT INTO series (name) VALUES (?)", (series.name,))
        self.conn.commit()
        series.id = cur.lastrowid
        return series

    def add_volume(self, volume: Volume) -> Volume:
        cur = self.conn.execute(
            "INSERT INTO volume (series_id, name, palette_revision) VALUES (?, ?, ?)",
            (volume.series_id, volume.name, volume.palette_revision),
        )
        self.conn.commit()
        volume.id = cur.lastrowid
        return volume

    def add_page(self, page: Page) -> Page:
        cur = self.conn.execute(
            "INSERT INTO page (volume_id, source_path, idx, width, height)"
            " VALUES (?, ?, ?, ?, ?)",
            (page.volume_id, page.source_path, page.index, page.width, page.height),
        )
        self.conn.commit()
        page.id = cur.lastrowid
        return page

    def pages_for_volume(self, volume_id: int) -> list[Page]:
        rows = self.conn.execute(
            "SELECT * FROM page WHERE volume_id = ? ORDER BY idx", (volume_id,)
        ).fetchall()
        return [_page(r) for r in rows]

    # ---- Panel ----------------------------------------------------------

    def add_panel(self, panel: Panel) -> Panel:
        cur = self.conn.execute(
            "INSERT INTO panel (page_id, x, y, width, height, reading_order,"
            " label_map_path, polygon) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                panel.page_id,
                panel.x,
                panel.y,
                panel.width,
                panel.height,
                panel.reading_order,
                panel.label_map_path,
                json.dumps(panel.polygon),
            ),
        )
        self.conn.commit()
        panel.id = cur.lastrowid
        return panel

    def panels_for_page(self, page_id: int) -> list[Panel]:
        rows = self.conn.execute(
            "SELECT * FROM panel WHERE page_id = ? ORDER BY reading_order", (page_id,)
        ).fetchall()
        return [_panel(r) for r in rows]

    def set_label_map_path(self, panel_id: int, path: str) -> None:
        self.conn.execute("UPDATE panel SET label_map_path = ? WHERE id = ?", (path, panel_id))
        self.conn.commit()

    # ---- Palette / Entity ------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        cur = self.conn.execute(
            "INSERT INTO entity (volume_id, name, reference_images) VALUES (?, ?, ?)",
            (entity.volume_id, entity.name, json.dumps(entity.reference_images)),
        )
        self.conn.commit()
        entity.id = cur.lastrowid
        return entity

    def add_palette_entry(self, entry: PaletteEntry) -> PaletteEntry:
        r, g, b = entry.rgb
        cur = self.conn.execute(
            "INSERT INTO palette_entry (volume_id, r, g, b, label, entity_id, revision)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry.volume_id, r, g, b, entry.label, entry.entity_id, entry.revision),
        )
        self.conn.execute(
            "UPDATE volume SET palette_revision = palette_revision + 1 WHERE id = ?",
            (entry.volume_id,),
        )
        self.conn.commit()
        entry.id = cur.lastrowid
        return entry

    def palette_for_volume(self, volume_id: int) -> list[PaletteEntry]:
        rows = self.conn.execute(
            "SELECT * FROM palette_entry WHERE volume_id = ? ORDER BY id", (volume_id,)
        ).fetchall()
        return [_palette_entry(r) for r in rows]

    def update_palette_rgb(self, entry_id: int, rgb: tuple[int, int, int]) -> int:
        """Edit a colour. Returns the entry's new revision.

        This is the single-row update §3 is built around. No region rows are
        touched; nothing is re-run. Callers repaint only the panels named by
        ``panels_affected_by``.
        """
        r, g, b = rgb
        self.conn.execute(
            "UPDATE palette_entry SET r = ?, g = ?, b = ?, revision = revision + 1"
            " WHERE id = ?",
            (r, g, b, entry_id),
        )
        self.conn.execute(
            "UPDATE volume SET palette_revision = palette_revision + 1 WHERE id ="
            " (SELECT volume_id FROM palette_entry WHERE id = ?)",
            (entry_id,),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT revision FROM palette_entry WHERE id = ?", (entry_id,)
        ).fetchone()
        return int(row["revision"])

    def panels_affected_by(self, palette_entry_id: int) -> list[int]:
        """Panel ids referencing this entry — the incremental repaint set (§6)."""
        rows = self.conn.execute(
            "SELECT DISTINCT panel_id FROM region WHERE palette_entry_id = ?",
            (palette_entry_id,),
        ).fetchall()
        return [int(r["panel_id"]) for r in rows]

    # ---- Region ----------------------------------------------------------

    def add_regions(self, regions: list[Region]) -> list[Region]:
        for region in regions:
            cur = self.conn.execute(
                "INSERT INTO region (panel_id, label, palette_entry_id, confidence,"
                " status, area, bbox_x, bbox_y, bbox_w, bbox_h)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    region.panel_id,
                    region.label,
                    region.palette_entry_id,
                    region.confidence,
                    region.status.value,
                    region.area,
                    *region.bbox,
                ),
            )
            region.id = cur.lastrowid
        self.conn.commit()
        return regions

    def regions_for_panel(self, panel_id: int) -> list[Region]:
        rows = self.conn.execute(
            "SELECT * FROM region WHERE panel_id = ? ORDER BY label", (panel_id,)
        ).fetchall()
        return [_region(r) for r in rows]

    def assign_palette(
        self,
        region_id: int,
        palette_entry_id: int | None,
        status: RegionStatus = RegionStatus.MANUAL,
    ) -> None:
        """One-click reassignment (§1.9)."""
        self.conn.execute(
            "UPDATE region SET palette_entry_id = ?, status = ? WHERE id = ?",
            (palette_entry_id, status.value, region_id),
        )
        self.conn.commit()

    # ---- Protected masks --------------------------------------------------

    def add_protected_mask(self, mask: ProtectedMask) -> ProtectedMask:
        cur = self.conn.execute(
            "INSERT INTO protected_mask (panel_id, kind, mask_path, area,"
            " bbox_x, bbox_y, bbox_w, bbox_h) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (mask.panel_id, mask.kind.value, mask.mask_path, mask.area, *mask.bbox),
        )
        self.conn.commit()
        mask.id = cur.lastrowid
        return mask

    def protected_for_panel(self, panel_id: int) -> list[ProtectedMask]:
        rows = self.conn.execute(
            "SELECT * FROM protected_mask WHERE panel_id = ?", (panel_id,)
        ).fetchall()
        return [_protected(r) for r in rows]


# ---- Row adapters ---------------------------------------------------------


def _page(row: sqlite3.Row) -> Page:
    return Page(
        id=row["id"],
        volume_id=row["volume_id"],
        source_path=row["source_path"],
        index=row["idx"],
        width=row["width"],
        height=row["height"],
    )


def _panel(row: sqlite3.Row) -> Panel:
    return Panel(
        id=row["id"],
        page_id=row["page_id"],
        x=row["x"],
        y=row["y"],
        width=row["width"],
        height=row["height"],
        reading_order=row["reading_order"],
        label_map_path=row["label_map_path"],
        polygon=[tuple(p) for p in json.loads(row["polygon"])],
    )


def _palette_entry(row: sqlite3.Row) -> PaletteEntry:
    return PaletteEntry(
        id=row["id"],
        volume_id=row["volume_id"],
        rgb=(row["r"], row["g"], row["b"]),
        label=row["label"],
        entity_id=row["entity_id"],
        revision=row["revision"],
    )


def _region(row: sqlite3.Row) -> Region:
    return Region(
        id=row["id"],
        panel_id=row["panel_id"],
        label=row["label"],
        palette_entry_id=row["palette_entry_id"],
        confidence=row["confidence"],
        status=RegionStatus(row["status"]),
        area=row["area"],
        bbox=(row["bbox_x"], row["bbox_y"], row["bbox_w"], row["bbox_h"]),
    )


def _protected(row: sqlite3.Row) -> ProtectedMask:
    return ProtectedMask(
        id=row["id"],
        panel_id=row["panel_id"],
        kind=ProtectedKind(row["kind"]),
        mask_path=row["mask_path"],
        area=row["area"],
        bbox=(row["bbox_x"], row["bbox_y"], row["bbox_w"], row["bbox_h"]),
    )
