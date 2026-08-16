---
phase: 02-panel-polygon-editor-protected-masks
plan: 03
subsystem: model
tags: [protected-masks, panels, store, sqlite, tdd, page-scope]

# Dependency graph
requires:
  - "02-02: src/comiccolor/segmentation/protected.py (rasterize_protected_for_panel, protected_bbox_and_area) — the callers this store surface exists for"
provides:
  - "src/comiccolor/model/entities.py — ProtectedMask(page_id, kind, polygon, id, touched, area, bbox); panel_id and mask_path removed"
  - "src/comiccolor/model/store.py — protected_mask table rewritten to page_id/polygon/touched; stale-database guard in Store.__init__; 11 new Store methods for panel and protected-mask CRUD"
affects: ["02-04", "02-05", "02-06", "02-07", "02-08", "02-09"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "bbox recompute lives in exactly one place — update_panel_vertex reads the current polygon, mutates one tuple, and delegates to update_panel_polygon rather than duplicating the min/max arithmetic."
    - "any protected-mask polygon rewrite unconditionally sets touched=1 (UI-SPEC §3) — there is no update path that leaves an artist-edited mask looking machine-proposed."
    - "stale-schema guard: Store.__init__ raises RuntimeError naming the file and the fix (delete it) rather than silently writing pre-Phase-2 columns after CREATE TABLE IF NOT EXISTS is a no-op against an existing table."

key-files:
  created: []
  modified:
    - src/comiccolor/model/entities.py
    - src/comiccolor/model/store.py
    - tests/test_store.py

key-decisions:
  - "D-17/D-18/D-20/D-21 implemented as specified in 02-CONTEXT.md; no reinterpretation."
  - "protected_for_panel deleted outright rather than kept alongside protected_for_page — a panel-scoped protected-mask query is meaningless under D-20 and leaving it would invite a caller to reintroduce panel scope."

requirements-completed: [PAN-02, PAN-03, PROT-02, PROT-03]

# Metrics
duration: ~35min
completed: 2026-08-16
---

# Phase 2 Plan 3: Page-Scoped Protected Masks and Panel/Protected CRUD Summary

**`ProtectedMask` moves from panel scope to page scope with an editable vertex polygon and a `touched` flag, the `protected_mask` table is rewritten to match with a loud guard against a stale pre-Phase-2 database, and eleven new `Store` methods give the panel and protected-mask editor routes everything they need to read, mutate and delete — all parameterized, all tested, and a page delete cascades away both panels and protected masks.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3 (Task 3 `tdd="true"`)
- **Files modified:** 3 (0 created)

## Accomplishments

- `src/comiccolor/model/entities.py`:
  - `ProtectedMask` rewritten: `page_id: int` replaces `panel_id` entirely;
    `polygon: list[tuple[int, int]]` added (page-pixel space, same type as
    `Panel.polygon`); `touched: bool = False` added; `mask_path: str`
    (raster-PNG representation) deleted per RESEARCH.md's State of the Art
    finding that a PNG path cannot be hand-edited as vertices.
  - Docstring gained D-20 (page scope, clip-at-use via
    `rasterize_protected_for_panel`), D-21 ("never coloured", not "content
    preserved" — no `assert_invariant`-style integrity chain belongs here),
    and the `touched` semantics from UI-SPEC §3.
- `src/comiccolor/model/store.py`:
  - `protected_mask` table rewritten wholesale (no `ALTER TABLE` — D-20:
    Phase 2 is the only phase in which protected masks exist, so there is no
    shipped data to migrate). New columns: `page_id` (FK to `page`, `ON
    DELETE CASCADE`), `kind`, `polygon` (TEXT/JSON), `touched` (INTEGER),
    `area`, `bbox_x/y/w/h`. `idx_protected_page` replaces `idx_protected_panel`.
  - `Store.__init__` now calls `_check_protected_mask_schema()` after
    `executescript(SCHEMA)`: queries `PRAGMA table_info(protected_mask)` and
    raises `RuntimeError` naming the database path if `page_id` is absent —
    the guard against `CREATE TABLE IF NOT EXISTS` silently leaving a stale
    pre-Phase-2 database on the old `panel_id`/`mask_path` shape
    (RESEARCH.md Pitfall 5).
  - `_protected` row adapter rewritten for the new columns, mirroring
    `_panel`'s `json.loads` idiom for `polygon`.
  - `add_protected_mask` rewritten for the new columns.
  - Eleven new methods (all parameterized `self._execute(...)` +
    `self.conn.commit()`, no raw SQL leaving this module):
    - Panel: `panel_by_id`, `update_panel_polygon` (rewrites the polygon
      and recomputes `x/y/width/height` from it in the same UPDATE; raises
      `ValueError` on a polygon with fewer than 3 vertices per threat
      T-2-15), `update_panel_vertex` (delegates to `update_panel_polygon`
      so the bbox recompute happens in exactly one place; raises
      `IndexError` on an out-of-range index), `delete_panel`,
      `delete_panels_for_page` (returns count deleted),
      `set_panel_reading_order`.
    - Protected mask: `protected_for_page` (replaces `protected_for_panel`,
      deleted outright — a panel-scoped query is meaningless under D-20),
      `protected_mask_by_id`, `update_protected_mask_polygon` (rewrites
      polygon/area/bbox and unconditionally sets `touched = 1` per
      UI-SPEC §3 — any reshape is by definition an artist touch),
      `delete_protected_mask`, `delete_protected_for_page` (returns count
      deleted).
- `tests/test_store.py`: 13 new tests covering every method above plus
  `test_deleting_a_page_cascades_panels_and_protected_masks` (relies on the
  existing `ON DELETE CASCADE` foreign keys — no new schema logic needed for
  the cascade itself, only proof it holds under the new shape). A `page`
  fixture was factored out of the existing `panel` fixture so the new tests
  can build panels and protected masks against the same page.

## Task Commits

Each task was committed atomically; Task 3 followed the RED then GREEN TDD gate:

1. **Task 1 — `ProtectedMask` becomes page-scoped, polygonal and touch-aware**
   - `eb90878` (feat): dataclass rewrite
2. **Task 2 — Rewrite the `protected_mask` table and its row adapter**
   - `e24bb9e` (feat): schema, stale-database guard, `add_protected_mask`/`_protected`
3. **Task 3 — Panel and protected-mask CRUD methods**
   - `f6e0e5c` (test): 13 failing tests, all `AttributeError` on missing methods (RED)
   - `564d05d` (feat): 11 new `Store` methods, all 32 tests in `test_store.py` green (GREEN)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `src/comiccolor/model/entities.py` — `ProtectedMask` rewritten (`page_id`, `polygon`, `touched`; `panel_id`/`mask_path` removed)
- `src/comiccolor/model/store.py` — `protected_mask` table rewritten, stale-DB guard, `add_protected_mask`/`_protected` updated, 11 new CRUD methods
- `tests/test_store.py` — `page` fixture factored out, `ProtectedKind`/`ProtectedMask` imports added, 13 new tests

## TDD Gate Compliance

Task 3's gate sequence is present in git log: `f6e0e5c` (`test(...)`, RED — 13
tests failing with `AttributeError` before any implementation) followed by
`564d05d` (`feat(...)`, GREEN — 32/32 tests passing). No REFACTOR commit was
needed; the implementation matched the plan's method shapes on the first
pass.

## Decisions Made

- Implemented D-17, D-18, D-20, D-21 exactly as locked in `02-CONTEXT.md`;
  no re-derivation.
- `protected_for_panel` deleted outright rather than deprecated or kept
  alongside `protected_for_page` — per the plan's explicit instruction, since
  a panel-scoped query is meaningless once protection is page-scoped and
  leaving it callable would invite a future caller to reintroduce panel
  scope by accident.
- `update_panel_vertex` raises `IndexError` both for an out-of-range vertex
  index and for a panel id that does not exist, rather than distinguishing
  the two cases — the plan only specifies the out-of-range behavior, and a
  missing panel is a strict subset of "no such vertex."

## Deviations from Plan

None — plan executed exactly as written. `_check_protected_mask_schema` is
a small private helper method rather than inline code in `__init__`, purely
for readability; the acceptance criterion's `grep -n "PRAGMA
table_info(protected_mask)"` still matches, and the guard runs at the exact
point (`Store.__init__`, immediately after `executescript(SCHEMA)`) the plan
specifies.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- All eleven `Store` methods this plan promised now exist, are tested, and
  are ready for the route plans (02-04 onward) that call into them —
  `panel_by_id`/`update_panel_polygon`/`update_panel_vertex`/`delete_panel`/
  `delete_panels_for_page`/`set_panel_reading_order` for the panel editor,
  and `protected_for_page`/`protected_mask_by_id`/
  `update_protected_mask_polygon`/`delete_protected_mask`/
  `delete_protected_for_page` for the protected-mask editor.
- Ownership checks (`_get_owned_panel`/`_get_owned_protected_mask`, threat
  T-2-02) are explicitly deferred to the route layer per the plan's threat
  model — `Store` itself has no project-scoping on these lookups by design,
  since it is already one file per project.
- A stale local database from before this plan will now fail loudly at
  `Store` construction with a clear message naming the file and the fix
  (delete it); this is a deliberate behavior change worth knowing about if
  `comiccolor serve` was ever run against Phase 1 code on this machine.
- No blockers for downstream Phase 2 plans.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16*

## Self-Check: PASSED
