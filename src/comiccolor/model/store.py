"""SQLite persistence for the §3 data model.

The schema is deliberately narrow. Note there is no ``rgb`` column on
``region`` — the only place an RGB value exists in the database is
``palette_entry``. That is the §9 anti-pattern "do not bake RGB into regions"
enforced by the schema rather than by review.

Every mutation commits synchronously before returning (PROJ-05: a refresh or
crash immediately after an edit loses no work). Do not add a write-behind
cache or a longer-lived transaction anywhere in this file — that would break
PROJ-05. WAL mode is only for concurrent per-request readers (RESEARCH.md
Pattern 1); ``checkpoint()`` is the separate, mandatory step that keeps a
copied project folder complete (D-04).
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
    PipelineStage,
    ProtectedKind,
    ProtectedMask,
    Project,
    Region,
    RegionStatus,
    Volume,
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    name             TEXT NOT NULL UNIQUE,
    palette_revision INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS volume (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS page (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id     INTEGER NOT NULL REFERENCES volume(id) ON DELETE CASCADE,
    source_path   TEXT NOT NULL,
    idx           INTEGER NOT NULL,
    width         INTEGER NOT NULL DEFAULT 0,
    height        INTEGER NOT NULL DEFAULT 0,
    stage         TEXT NOT NULL DEFAULT 'panels',
    original_name TEXT NOT NULL DEFAULT '',
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
    project_id       INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    reference_images TEXT NOT NULL DEFAULT '[]',
    UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS palette_entry (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    r          INTEGER NOT NULL,
    g          INTEGER NOT NULL,
    b          INTEGER NOT NULL,
    label      TEXT NOT NULL,
    entity_id  INTEGER REFERENCES entity(id) ON DELETE SET NULL,
    revision   INTEGER NOT NULL DEFAULT 0
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
CREATE INDEX IF NOT EXISTS idx_palette_project ON palette_entry(project_id);
CREATE INDEX IF NOT EXISTS idx_volume_project ON volume(project_id);
CREATE INDEX IF NOT EXISTS idx_entity_project ON entity(project_id);
"""


class Store:
    """Thin data-access layer. One Store per request, never shared.

    Not thread-*safe*: nothing here serialises concurrent access, so two
    threads must never use one ``Store`` at the same time. It is thread-
    *movable*: a single owner may hand it from one thread to the next, which
    is exactly what FastAPI does (see ``__init__``'s
    ``check_same_thread=False`` comment).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False is required, not a shortcut. FastAPI
        # resolves a sync generator dependency's __enter__, the endpoint
        # itself, and the dependency's __exit__ as three *separate*
        # run_in_threadpool calls, and anyio gives no guarantee that the
        # same worker thread serves all three. With the default
        # check_same_thread=True the connection raises
        # sqlite3.ProgrammingError the moment the endpoint runs on a
        # different worker than the one that opened it — reproducible with
        # as few as two concurrent requests.
        #
        # This relaxes only sqlite3's *object-level* thread assertion. It
        # does not make the connection shared: web/deps.py's get_store
        # builds one Store per request and closes it at teardown, so
        # exactly one request owns this connection at a time and no two
        # threads ever touch it simultaneously. Do not "simplify" this into
        # a module-level connection reused across requests — that is the
        # genuinely unsafe shape this comment exists to distinguish itself
        # from.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL is the user's resolution of RESEARCH.md Open Question 1: it is
        # what makes the web layer's per-request connections (Pattern 1) safe
        # under a read landing mid-write. The busy timeout is what stops a
        # GET landing mid-POST from raising "database is locked" instead of
        # just waiting. See checkpoint() for the other half of this promise.
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        """Checkpoint the WAL, then close the connection.

        WAL keeps recently committed data in ``project.db-wal`` rather than
        the main file. D-04 promises the artist can copy, move or hand over
        the project folder and have it work; without folding the WAL back in
        first that promise is not actually kept (RESEARCH.md Pitfall 1).
        """
        self.checkpoint()
        self.conn.close()

    def checkpoint(self) -> None:
        """Truncate ``project.db-wal`` back into ``project.db``.

        Every method on this class already commits synchronously before
        returning (PROJ-05: a refresh or crash immediately after an edit
        loses no work). This does not defer, batch or add a write-behind
        cache — it only folds already-committed WAL frames back into the
        single file, so the project folder is safe to zip, copy or hand off
        at any time (D-04, resolved RESEARCH.md Open Question 1).
        """
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        self.conn.commit()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Run a write statement, rolling back on failure.

        A caught constraint violation (e.g. a caller doing
        ``pytest.raises(sqlite3.IntegrityError)`` against one of the schema
        invariants in the module docstring) must not leave this connection
        holding a stale, uncommitted transaction — that would make the next
        ``checkpoint()``/``close()`` fail with "database is locked" even
        though the caller already handled the error correctly.
        """
        try:
            return self.conn.execute(sql, params)
        except sqlite3.Error:
            self.conn.rollback()
            raise

    # ---- Project ----------------------------------------------------------

    def add_project(self, project: Project) -> Project:
        """A project folder holds exactly one project (D-04). ``id`` is
        pinned to 1 by the schema's ``CHECK (id = 1)``, so a second insert
        collides on the primary key and raises ``sqlite3.IntegrityError``
        rather than being caught by review."""
        cur = self._execute(
            "INSERT INTO project (id, name, palette_revision) VALUES (1, ?, ?)",
            (project.name, project.palette_revision),
        )
        self.conn.commit()
        project.id = cur.lastrowid
        return project

    def the_project(self) -> Project | None:
        """The single project row, or None for a freshly created database."""
        row = self.conn.execute("SELECT * FROM project WHERE id = 1").fetchone()
        return _project(row) if row else None

    # ---- Volume -------------------------------------------------------------

    def add_volume(self, volume: Volume) -> Volume:
        cur = self._execute(
            "INSERT INTO volume (project_id, name) VALUES (?, ?)",
            (volume.project_id, volume.name),
        )
        self.conn.commit()
        volume.id = cur.lastrowid
        return volume

    def volumes_for_project(self, project_id: int) -> list[Volume]:
        rows = self.conn.execute(
            "SELECT * FROM volume WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
        return [_volume(r) for r in rows]

    def rename_volume(self, volume_id: int, name: str) -> None:
        """D-03: volumes are artist-visible and renameable."""
        self._execute("UPDATE volume SET name = ? WHERE id = ?", (name, volume_id))
        self.conn.commit()

    def delete_volume(self, volume_id: int) -> None:
        """D-03. The existing ``ON DELETE CASCADE`` already removes its pages."""
        self._execute("DELETE FROM volume WHERE id = ?", (volume_id,))
        self.conn.commit()

    # ---- Page ---------------------------------------------------------------

    def add_page(self, page: Page) -> Page:
        cur = self._execute(
            "INSERT INTO page (volume_id, source_path, idx, width, height, stage,"
            " original_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                page.volume_id,
                page.source_path,
                page.index,
                page.width,
                page.height,
                page.stage.value,
                page.original_name,
            ),
        )
        self.conn.commit()
        page.id = cur.lastrowid
        return page

    def pages_for_volume(self, volume_id: int) -> list[Page]:
        rows = self.conn.execute(
            "SELECT * FROM page WHERE volume_id = ? ORDER BY idx", (volume_id,)
        ).fetchall()
        return [_page(r) for r in rows]

    def page_by_id(self, page_id: int) -> Page | None:
        row = self.conn.execute("SELECT * FROM page WHERE id = ?", (page_id,)).fetchone()
        return _page(row) if row else None

    def next_page_index(self, volume_id: int) -> int:
        """``MAX(idx) + 1``, or 0 for an empty volume.

        This is what makes PROJ-02's "add more pages weeks later" append
        rather than collide with the ``UNIQUE (volume_id, idx)`` constraint.
        """
        row = self.conn.execute(
            "SELECT MAX(idx) AS max_idx FROM page WHERE volume_id = ?", (volume_id,)
        ).fetchone()
        return 0 if row["max_idx"] is None else int(row["max_idx"]) + 1

    def set_page_stage(self, page_id: int, stage: PipelineStage) -> None:
        self._execute(
            "UPDATE page SET stage = ? WHERE id = ?", (stage.value, page_id)
        )
        self.conn.commit()

    def delete_page(self, page_id: int) -> None:
        self._execute("DELETE FROM page WHERE id = ?", (page_id,))
        self.conn.commit()

    # ---- Panel ----------------------------------------------------------

    def add_panel(self, panel: Panel) -> Panel:
        cur = self._execute(
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
        self._execute("UPDATE panel SET label_map_path = ? WHERE id = ?", (path, panel_id))
        self.conn.commit()

    # ---- Palette / Entity ------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        cur = self._execute(
            "INSERT INTO entity (project_id, name, reference_images) VALUES (?, ?, ?)",
            (entity.project_id, entity.name, json.dumps(entity.reference_images)),
        )
        self.conn.commit()
        entity.id = cur.lastrowid
        return entity

    def entities_for_project(self, project_id: int) -> list[Entity]:
        rows = self.conn.execute(
            "SELECT * FROM entity WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
        return [_entity(r) for r in rows]

    def entity_by_name(self, project_id: int, name: str) -> Entity | None:
        """Accepting a proposal for a character who already exists must reuse
        this row, not create a duplicate — the schema's ``UNIQUE (project_id,
        name)`` makes a real duplicate impossible anyway, but callers still
        need a way to look the existing row up before deciding to insert."""
        row = self.conn.execute(
            "SELECT * FROM entity WHERE project_id = ? AND name = ?",
            (project_id, name),
        ).fetchone()
        return _entity(row) if row else None

    def set_entity_reference_images(self, entity_id: int, paths: list[str]) -> None:
        self._execute(
            "UPDATE entity SET reference_images = ? WHERE id = ?",
            (json.dumps(paths), entity_id),
        )
        self.conn.commit()

    def add_palette_entry(self, entry: PaletteEntry) -> PaletteEntry:
        r, g, b = entry.rgb
        cur = self._execute(
            "INSERT INTO palette_entry (project_id, r, g, b, label, entity_id, revision)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entry.project_id, r, g, b, entry.label, entry.entity_id, entry.revision),
        )
        self._execute(
            "UPDATE project SET palette_revision = palette_revision + 1 WHERE id = ?",
            (entry.project_id,),
        )
        self.conn.commit()
        entry.id = cur.lastrowid
        return entry

    def palette_for_project(self, project_id: int) -> list[PaletteEntry]:
        rows = self.conn.execute(
            "SELECT * FROM palette_entry WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
        return [_palette_entry(r) for r in rows]

    def palette_entry_by_id(self, entry_id: int) -> PaletteEntry | None:
        row = self.conn.execute(
            "SELECT * FROM palette_entry WHERE id = ?", (entry_id,)
        ).fetchone()
        return _palette_entry(row) if row else None

    def update_palette_label(self, entry_id: int, label: str) -> None:
        """PAL-03 rename (D-16): entries are auto-named and freely renameable.
        Does not touch ``rgb`` or bump ``revision`` — the colour itself has
        not changed, only its display name."""
        self._execute(
            "UPDATE palette_entry SET label = ? WHERE id = ?", (label, entry_id)
        )
        self.conn.commit()

    def delete_palette_entry(self, entry_id: int) -> None:
        """Relies on the existing ``region.palette_entry_id ...
        ON DELETE SET NULL`` so deleting an entry orphans its regions rather
        than corrupting them.

        Bumps ``project.palette_revision``, like ``add_palette_entry`` and
        ``update_palette_rgb`` and unlike ``update_palette_label`` (which
        deliberately does not — a rename changes no colour). A delete very
        much changes colour state: every region that referenced this entry
        becomes unpainted. ``entities.py`` documents the field as bumped on
        every palette mutation with "a renderer caches against this", so
        skipping it here would serve stale pixels after a delete — the
        exact §6 incremental-propagation case the field exists for.

        The bump runs *before* the delete: it reads ``project_id`` off the
        row being deleted, so afterwards there is nothing left to read it
        from.
        """
        self._execute(
            "UPDATE project SET palette_revision = palette_revision + 1 WHERE id ="
            " (SELECT project_id FROM palette_entry WHERE id = ?)",
            (entry_id,),
        )
        self._execute("DELETE FROM palette_entry WHERE id = ?", (entry_id,))
        self.conn.commit()

    def update_palette_rgb(self, entry_id: int, rgb: tuple[int, int, int]) -> int:
        """Edit a colour. Returns the entry's new revision.

        This is the single-row update §3 is built around. No region rows are
        touched; nothing is re-run. Callers repaint only the panels named by
        ``panels_affected_by`` (or the pages named by ``pages_affected_by``).
        """
        r, g, b = rgb
        self._execute(
            "UPDATE palette_entry SET r = ?, g = ?, b = ?, revision = revision + 1"
            " WHERE id = ?",
            (r, g, b, entry_id),
        )
        self._execute(
            "UPDATE project SET palette_revision = palette_revision + 1 WHERE id ="
            " (SELECT project_id FROM palette_entry WHERE id = ?)",
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

    def pages_affected_by(self, palette_entry_id: int) -> list[int]:
        """Distinct page ids referencing this entry.

        The same incremental propagation set as ``panels_affected_by`` (§6),
        expressed at the granularity the artist actually sees: the UI-SPEC
        recolour toast reads "Updated on {N} page{s}", which counts pages,
        not panels.
        """
        rows = self.conn.execute(
            "SELECT DISTINCT panel.page_id AS page_id FROM region"
            " JOIN panel ON panel.id = region.panel_id"
            " WHERE region.palette_entry_id = ?",
            (palette_entry_id,),
        ).fetchall()
        return [int(r["page_id"]) for r in rows]

    # ---- Region ----------------------------------------------------------

    def add_regions(self, regions: list[Region]) -> list[Region]:
        for region in regions:
            cur = self._execute(
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
        self._execute(
            "UPDATE region SET palette_entry_id = ?, status = ? WHERE id = ?",
            (palette_entry_id, status.value, region_id),
        )
        self.conn.commit()

    # ---- Protected masks --------------------------------------------------

    def add_protected_mask(self, mask: ProtectedMask) -> ProtectedMask:
        cur = self._execute(
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


def _project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        palette_revision=row["palette_revision"],
    )


def _volume(row: sqlite3.Row) -> Volume:
    return Volume(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
    )


def _page(row: sqlite3.Row) -> Page:
    return Page(
        id=row["id"],
        volume_id=row["volume_id"],
        source_path=row["source_path"],
        index=row["idx"],
        width=row["width"],
        height=row["height"],
        stage=PipelineStage(row["stage"]),
        original_name=row["original_name"],
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


def _entity(row: sqlite3.Row) -> Entity:
    return Entity(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        reference_images=json.loads(row["reference_images"]),
    )


def _palette_entry(row: sqlite3.Row) -> PaletteEntry:
    return PaletteEntry(
        id=row["id"],
        project_id=row["project_id"],
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
