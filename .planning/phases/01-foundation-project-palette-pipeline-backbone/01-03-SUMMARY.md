---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 03
subsystem: database
tags: [sqlite, dataclasses, schema-migration, wal]

# Dependency graph
requires: []
provides:
  - "Project replaces Series end-to-end; palette_entry and entity are project-scoped, not volume-scoped"
  - "PipelineStage enum (8 stages) and page.stage/original_name columns for the pipeline registry"
  - "Complete Store surface (project/volume/page/palette/entity CRUD) that plans 01-04, 01-06..01-09 build against"
  - "WAL journal mode + busy_timeout + Store.checkpoint() for durable, portable project.db"
affects: [01-04, 01-06, 01-07, 01-08, 01-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Store._execute() rollback helper: every write statement rolls back on sqlite3.Error so a caught constraint violation never leaves the connection holding a stale transaction"
    - "project table constrained to exactly one row via PRIMARY KEY id with CHECK (id = 1), enforced by the schema not by review"

key-files:
  created: []
  modified:
    - src/comiccolor/model/entities.py
    - src/comiccolor/model/store.py
    - src/comiccolor/model/__init__.py
    - tests/test_store.py

key-decisions:
  - "Explicit id=1 INSERT for the single project row (not an implicit AUTOINCREMENT), so PRIMARY KEY uniqueness itself rejects a second project"
  - "update_palette_label does not bump palette_entry.revision — renaming is not a colour change, so renderer cache keys should not invalidate"
  - "close() always checkpoints before closing the connection, and the explicit test_an_uncommitted_process_death_loses_nothing test bypasses close() (calls conn.close() directly) to keep testing the true no-checkpoint durability path"

patterns-established:
  - "Store._execute() wraps every INSERT/UPDATE/DELETE; SELECT queries still go through self.conn.execute() directly since they cannot leave a dangling write transaction"

requirements-completed: [PROJ-01, PROJ-04, PROJ-05, PAL-04]

# Metrics
duration: ~25min
completed: 2026-08-15
---

# Phase 1 Plan 3: §3 Data Model Migration (Series → Project) Summary

**Migrated `entities.py`/`store.py` from series-scope to project-scope (D-01/D-02), added the `PipelineStage` enum and `page.stage` column (D-07), completed the full `Store` surface plans 01-04 and 01-06..01-09 depend on, and switched `project.db` to WAL journal mode with a mandatory `Store.checkpoint()` that keeps a copied project folder complete (resolved RESEARCH.md Open Question 1).**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3 planned tasks, executed as one cohesive commit (all three touch the same four files with heavy interdependency — Task 3's connection-lifecycle fix was needed for Task 1's constraint-violation tests to keep passing after adding checkpoint-on-close)
- **Files modified:** 4

## Accomplishments

- `Series` renamed to `Project` throughout `src/` and `tests/`; `palette_entry.project_id` and `entity.project_id` replace `volume_id`, and `project.palette_revision` replaces `volume.palette_revision` (D-01, D-02)
- Added `PipelineStage(str, Enum)` with all 8 members (`import`, `panels`, `protected`, `zones`, `propose`, `snap`, `review`, `export`) and `Page.stage`/`Page.original_name`; `page.stage` defaults to `panels` (D-07)
- `project` table constrained to a single row (`CHECK (id = 1)`) — a second `add_project` raises `sqlite3.IntegrityError` structurally, not by review (D-04)
- Added the full `Store` method surface needed by later plans: `add_project`/`the_project`, `volumes_for_project`/`rename_volume`/`delete_volume`, `page_by_id`/`next_page_index`/`set_page_stage`/`delete_page`, `palette_entry_by_id`/`update_palette_label`/`delete_palette_entry`/`pages_affected_by`, `entities_for_project`/`entity_by_name`/`set_entity_reference_images`
- `Store.__init__` sets `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`; `Store.checkpoint()` runs `PRAGMA wal_checkpoint(TRUNCATE)` and is called from `close()`, closing the loop on RESEARCH.md's resolved Open Question 1 and D-04's "copy the folder and it works" promise
- `tests/test_store.py` rewritten around project-scoped fixtures; 19 tests total (10 pre-existing intent preserved, 9 new), full suite green (`pytest -q`: 50 passed, 2 xfailed)

## Task Commits

Executed as a single atomic commit since Tasks 1-3 are a tightly-coupled schema migration touching the same four files, and Task 3's connection-lifecycle fix was directly required to keep Task 1's own constraint-violation tests passing once `checkpoint()` was wired into `close()`:

1. **Tasks 1-3: Re-scope data model, complete Store surface, WAL + checkpoint** - `e9627f7` (feat)

## Files Created/Modified

- `src/comiccolor/model/entities.py` - `Project` (was `Series`), `PipelineStage` enum, `Page.stage`/`original_name`, project-scoped `Entity`/`PaletteEntry`
- `src/comiccolor/model/store.py` - `project` table (was `series`), project-scoped FKs, WAL/busy_timeout/checkpoint, `_execute()` rollback helper, full CRUD surface, row adapters (`_project`, `_volume`, `_entity` added; `_page`/`_palette_entry` updated)
- `src/comiccolor/model/__init__.py` - `Project`/`PipelineStage` exported in place of `Series`, alphabetised
- `tests/test_store.py` - project-scoped fixtures, 9 new tests covering D-02/D-04/D-07 and the WAL/checkpoint/portability guarantees

## Final Store Method List

```
add_project(project: Project) -> Project
the_project() -> Project | None
add_volume(volume: Volume) -> Volume
volumes_for_project(project_id: int) -> list[Volume]
rename_volume(volume_id: int, name: str) -> None
delete_volume(volume_id: int) -> None
add_page(page: Page) -> Page
pages_for_volume(volume_id: int) -> list[Page]
page_by_id(page_id: int) -> Page | None
next_page_index(volume_id: int) -> int
set_page_stage(page_id: int, stage: PipelineStage) -> None
delete_page(page_id: int) -> None
add_panel(panel: Panel) -> Panel
panels_for_page(page_id: int) -> list[Panel]
set_label_map_path(panel_id: int, path: str) -> None
add_entity(entity: Entity) -> Entity
entities_for_project(project_id: int) -> list[Entity]
entity_by_name(project_id: int, name: str) -> Entity | None
set_entity_reference_images(entity_id: int, paths: list[str]) -> None
add_palette_entry(entry: PaletteEntry) -> PaletteEntry
palette_for_project(project_id: int) -> list[PaletteEntry]
palette_entry_by_id(entry_id: int) -> PaletteEntry | None
update_palette_label(entry_id: int, label: str) -> None
delete_palette_entry(entry_id: int) -> None
update_palette_rgb(entry_id: int, rgb: tuple[int, int, int]) -> int
panels_affected_by(palette_entry_id: int) -> list[int]
pages_affected_by(palette_entry_id: int) -> list[int]
add_regions(regions: list[Region]) -> list[Region]
regions_for_panel(panel_id: int) -> list[Region]
assign_palette(region_id: int, palette_entry_id: int | None, status: RegionStatus = MANUAL) -> None
add_protected_mask(mask: ProtectedMask) -> ProtectedMask
protected_for_panel(panel_id: int) -> list[ProtectedMask]
checkpoint() -> None
close() -> None
```

## Final SCHEMA Column List

- `project`: `id` (PK, CHECK id=1), `name` (UNIQUE NOT NULL), `palette_revision` (INTEGER DEFAULT 0)
- `volume`: `id` (PK), `project_id` (FK -> project, CASCADE), `name` — UNIQUE(project_id, name)
- `page`: `id` (PK), `volume_id` (FK -> volume, CASCADE), `source_path`, `idx`, `width`, `height`, `stage` (TEXT DEFAULT 'panels'), `original_name` (TEXT DEFAULT '') — UNIQUE(volume_id, idx)
- `entity`: `id` (PK), `project_id` (FK -> project, CASCADE), `name`, `reference_images` (JSON TEXT) — UNIQUE(project_id, name)
- `palette_entry`: `id` (PK), `project_id` (FK -> project, CASCADE), `r`, `g`, `b`, `label`, `entity_id` (FK -> entity, SET NULL), `revision`

(`panel`, `region`, `protected_mask` are unchanged by this plan — still `page_id`/`panel_id`-scoped, no RGB anywhere except `palette_entry`.)

## Decisions Made

- Explicit `id=1` on the `project` INSERT (rather than relying on implicit AUTOINCREMENT) so the PRIMARY KEY constraint itself, not just the `CHECK`, rejects a second project row.
- `update_palette_label` does not bump `revision` — a rename is not a colour edit, and bumping revision would needlessly invalidate a renderer's colour cache.
- The `_execute()` rollback helper is applied to every write statement (INSERT/UPDATE/DELETE), not just the two exercised directly by `pytest.raises` in the tests — any constraint violation anywhere in this file could otherwise leave a Store instance's connection stuck.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `Store.close()` failed with "database table is locked" after a caught constraint violation**
- **Found during:** Task 3 (adding `checkpoint()` to `close()`), surfaced by the pre-existing `test_one_label_per_panel_is_unique` and the new `test_a_project_db_holds_one_project`
- **Issue:** SQLite's `sqlite3` module implicitly begins a write transaction on the first DML statement. When that statement raises (e.g. a `UNIQUE`/`CHECK` constraint violation caught via `pytest.raises`), the transaction is never committed or rolled back, so it stays open on the connection. Once Task 3 wired `checkpoint()` (which runs `PRAGMA wal_checkpoint(TRUNCATE)`) into `close()`, that dangling transaction caused `close()` itself to raise `sqlite3.OperationalError: database table is locked` during pytest fixture teardown — turning a correctly-handled application error into a test failure.
- **Fix:** Added `Store._execute(sql, params)`, a private helper that runs `self.conn.execute(...)` and calls `self.conn.rollback()` on any `sqlite3.Error` before re-raising. Replaced every write-statement `self.conn.execute(...)` call in the class (`add_project`, `add_volume`, `rename_volume`, `delete_volume`, `add_page`, `set_page_stage`, `delete_page`, `add_panel`, `set_label_map_path`, `add_entity`, `set_entity_reference_images`, `add_palette_entry`, `update_palette_label`, `delete_palette_entry`, `update_palette_rgb`, `add_regions`, `assign_palette`, `add_protected_mask`) with `self._execute(...)`. Read-only `SELECT` queries were left on `self.conn.execute(...)` since they cannot leave a write transaction open.
- **Files modified:** `src/comiccolor/model/store.py`
- **Verification:** `pytest tests/test_store.py -q` — 19 passed (previously 2 errored at teardown); `pytest -q` full suite — 50 passed, 2 xfailed
- **Committed in:** `e9627f7` (part of the single task commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for correctness — without this fix, `Store.close()`/`checkpoint()` (Task 3's own deliverable) would break on any caller that correctly handles a schema-enforced constraint violation, which is exactly the "assert what is impossible" pattern this file's own tests use throughout. No scope creep.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `Store` exposes every method plans 01-04 and 01-06..01-09 need against `project`/`volume`/`page`/`entity`/`palette_entry` — no later plan should need to reopen this file for a missing method.
- WAL + `checkpoint()` is proven durable (`test_an_uncommitted_process_death_loses_nothing`) and portable (`test_copying_the_folder_after_close_preserves_every_row`), satisfying PROJ-05 and D-04's automatable halves; the literal process-kill remains a manual UAT step per 01-VALIDATION.md.
- No blockers. `masks.py` (`LabelMapInvariantError`/`assert_invariant`) referenced in 01-PATTERNS.md is out of scope for this plan and untouched.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*

## Self-Check: PASSED

- FOUND: src/comiccolor/model/entities.py
- FOUND: src/comiccolor/model/store.py
- FOUND: src/comiccolor/model/__init__.py
- FOUND: tests/test_store.py
- FOUND: .planning/phases/01-foundation-project-palette-pipeline-backbone/01-03-SUMMARY.md
- FOUND: e9627f7 (feat(01-03) migration commit)
- FOUND: c6976c1 (docs(01-03) summary commit)
