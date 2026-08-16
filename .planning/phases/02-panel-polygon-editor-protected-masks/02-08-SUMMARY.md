---
phase: 02-panel-polygon-editor-protected-masks
plan: 08
subsystem: api
tags: [fastapi, panels, reading-order, geometry-validation]

# Dependency graph
requires:
  - phase: 02-05
    provides: "PanelListResponse/PanelResponse/PanelCreateRequest/VertexUpdateRequest/PolygonUpdateRequest schemas, panel.router skeleton, _panel_response/_panel_list_response/_get_owned_panel"
  - phase: 02-03
    provides: "Store.panels_for_page/add_panel/update_panel_vertex/update_panel_polygon/delete_panel/set_panel_reading_order"
provides:
  - "Five live panel routes under /api: GET/POST /pages/{page_id}/panels, PATCH /panels/{panel_id}/vertex/{i}, PATCH /panels/{panel_id}/polygon, DELETE /panels/{panel_id}"
  - "_recompute_reading_order(store, page_id) — the one place _reading_order() runs server-side after any panel mutation"
  - "_assert_polygon_in_page — the per-page geometry bound (T-2-03) on top of schemas.py's absolute PixelCoord bound (T-2-01)"
affects: [02-10, 02-11]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dynamic attribute on PanelBox (box.panel_id) to correlate _reading_order()'s reordered-but-identity-preserving output back to database rows without adding a field to the pure segmentation dataclass"
    - "Every mutating panel route ends with _recompute_reading_order then _panel_list_response — one shared tail, no route computes its own response shape"

key-files:
  created:
    - tests/test_web/test_panel_routes.py
  modified:
    - src/comiccolor/web/routers/panel.py

key-decisions:
  - "DELETE /panels/{panel_id} returns 200 with the renumbered list, not 204, because deletion shifts every later panel's reading_order and the client must not guess the new order (matches plan; documented in the route docstring)"
  - "No confirmation gate on panel delete (D-19/UI-SPEC §5, T-2-29 accepted) — in-editor undo is the safety net, not a server-side dialog"
  - "_recompute_reading_order imports _reading_order inside the function body so the router does not carry an OpenCV import at module load"

requirements-completed: [PAN-01, PAN-02, PAN-03]

# Metrics
duration: ~50min
completed: 2026-08-16
---

# Phase 02 Plan 08: Panel Polygon Editor Routes Summary

**The five panel routes an artist's polygon editor calls — list, draw-from-scratch, move-vertex, replace-polygon (covering both insert and delete), and delete-panel — each ending in a server-side reading-order recompute so `_reading_order()`'s tiering geometry lives in exactly one place.**

## What Was Built

**Task 1 — `src/comiccolor/web/routers/panel.py`:** `_assert_polygon_in_page` (422 `POLYGON_OUT_OF_PAGE_DETAIL` for any vertex outside `(0, 0, page.width, page.height)`, the per-page bound the schema's absolute `PixelCoord` range cannot express) and `_recompute_reading_order` (builds a `PanelBox` per panel, tags it with the source panel's id via a dynamic attribute since `PanelBox` carries no id field, calls `_reading_order(boxes, "ltr")`, writes the recomputed order back with `store.set_panel_reading_order`). Then five routes: `GET`/`POST /pages/{page_id}/panels`, `PATCH /panels/{panel_id}/vertex/{vertex_index}`, `PATCH /panels/{panel_id}/polygon`, `DELETE /panels/{panel_id}` — all plain `def`, all ending in `_recompute_reading_order` then `_panel_list_response` so every mutation returns the whole page's freshly reading-ordered panel list. `create_panel` derives the bbox from the posted polygon with the same min/max arithmetic `Store.update_panel_polygon` uses. `move_vertex` and `replace_polygon` both re-read the panel after mutating and 404 if it vanished (concurrent-delete guard, mirroring `update_palette_entry`). `delete_panel` answers 200, not 204, since a delete renumbers every panel after it.

**Task 2 — `tests/test_web/test_panel_routes.py`:** 10 tests covering PAN-01 (detector-shaped listing, leftmost-first), PAN-03 (create-and-delete round trip), delete renumbering with no gap, PAN-02 (vertex move persisting into both polygon and bbox, out-of-range 400), the three 422 refusals (sub-3-vertex, out-of-page, 513-vertex — T-2-01/T-2-03), unknown-panel-id 404 (T-2-02), and the no-project-open case.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `run_panels` (plan 02-07) does not exist in this worktree**

- **Found during:** Task 2, writing `test_list_panels_returns_polygons_in_reading_order`
- **Issue:** The plan's `read_first` and `<action>` for this test call for using `run_panels` from `src/comiccolor/pipeline/runner.py` (plan 02-07). Plan 02-07 is a sibling wave-3 plan executing in parallel in its own worktree and had not merged into this branch's history at spawn time (`git log` shows only `run_import` implemented; `panels`/`protected` still declare `runner=None`).
- **Fix:** The test calls `segment_panels`/`box_to_polygon` directly from `comiccolor.segmentation.panels` — the exact detector call `run_panels` will wrap once it lands — and persists the resulting boxes as `Panel` rows through `Store` directly, matching what the eventual stage runner does. A comment in the test module docstring and inline at the test explains this is a stand-in, not a missing integration, so a future reader does not mistake it for skipped coverage.
- **Files modified:** `tests/test_web/test_panel_routes.py` only (no production code affected)
- **Commit:** `ba44cb7`

**2. [Rule 1 - Bug in plan] `test_panel_routes_404_with_no_project_open` asserts 409, not 404**

- **Found during:** Task 2, writing the no-project-open test
- **Issue:** The plan names this test with "404" and describes it as covering "a panel id belonging to no open project" via `blank_client`. But `get_store`'s upstream dependency `get_current_project_path` raises `HTTPException(409, NO_PROJECT_DETAIL)` before any route body — including any panel lookup — ever runs, when no project is open at all. This is the same gate every other project-scoped route in the codebase shares, and the existing precedent (`test_project_routes.py`'s `test_requests_without_an_open_project_return_409`, `test_page_routes.py`'s pipeline-stages test) is uniformly 409 for "no project open," reserving 404 for "a specific row does not exist inside the currently open project's own database" (T-2-02, covered separately by `test_unknown_panel_id_is_404`). Since this app is one SQLite file per project, there is no scenario where a foreign project's row leaks past a 404 within one open database — "no project open" and "unknown id in this project" are genuinely different gates.
- **Fix:** Kept the plan's literal test name (so the acceptance-criteria grep for it still matches) but asserted the actual, correct status (409) with a docstring explaining the distinction, rather than writing a test that would either fail against correct code or force the route to violate the established 409 convention to pass.
- **Files modified:** `tests/test_web/test_panel_routes.py` only
- **Commit:** `ba44cb7`

### Note on Task 1's literal `async def` grep

The plan's acceptance criterion `grep -n "async def" src/comiccolor/web/routers/panel.py` returns no matches is not literally satisfiable while keeping the module's own docstring, which explains (in prose, inherited unchanged from plan 02-05's stub) *why* every route is a plain `def` and therefore contains the substring `async def` as English text on lines 9-10. This is pre-existing (the same text was present in the file before this plan touched it) and not a new deviation. The functional intent — no route in this module is actually declared `async def` — is confirmed directly: `pytest tests/test_web/` passes, and the route-table walk shows all five routes with plain-`def` handlers.

## Self-Check: PASSED

- FOUND: src/comiccolor/web/routers/panel.py
- FOUND: tests/test_web/test_panel_routes.py
- FOUND: commit 83afecf (Task 1)
- FOUND: commit ba44cb7 (Task 2)
- `pytest tests/ -q`: 195 passed, 2 xfailed (baseline 185 passed, 2 xfailed; +10 new tests, 0 regressions)
- All five routes confirmed present via the `original_router`-unwrapping walk: `GET/POST /pages/{page_id}/panels`, `PATCH /panels/{panel_id}/vertex/{vertex_index}`, `PATCH /panels/{panel_id}/polygon`, `DELETE /panels/{panel_id}`
