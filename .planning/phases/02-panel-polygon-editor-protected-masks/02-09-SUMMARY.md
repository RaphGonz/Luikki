---
phase: 02-panel-polygon-editor-protected-masks
plan: 09
subsystem: api
tags: [fastapi, protected-masks, geometry, touched-state]

# Dependency graph
requires:
  - phase: 02-05
    provides: "ProtectedMaskCreateRequest/Response/ListResponse, VertexUpdateRequest, PolygonUpdateRequest, protected.router stub, get_owned_page"
  - phase: 02-03
    provides: "page-scoped ProtectedMask entity and Store CRUD (protected_for_page, protected_mask_by_id, add_protected_mask, update_protected_mask_polygon, delete_protected_mask)"
provides:
  - "Five protected-mask routes: GET list, POST create (hand-draw), PATCH vertex, PATCH polygon, DELETE"
  - "_masks_response(store, page_id) list-read helper with detection_failed/detection_message hardcoded False/None (only the stage-confirm route in 02-11 sets those)"
  - "MAX_MASKS_PER_PAGE=256 / TOO_MANY_MASKS_DETAIL (409) and POLYGON_OUT_OF_PAGE_DETAIL (422) guards reused across create and both write routes"
affects: [02-11, 02-12]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_polygon_within_page(polygon, width, height) is the one page-bounds check every create/write route calls before persisting (T-2-03)"
    - "Every reshape route (vertex and polygon) re-reads the mask after Store.update_protected_mask_polygon and 404s if it vanished — the same concurrent-delete re-read guard palette.py's update_palette_entry established"

key-files:
  created:
    - tests/test_web/test_protected_routes.py
  modified:
    - src/comiccolor/web/routers/protected.py

key-decisions:
  - "run_protected (plan 02-07) is same-wave and was not merged into this worktree at execution time, so test_detector_proposed_masks_are_untouched_bubbles constructs the detector-shaped row directly through Store instead of calling run_protected — pins the touched=False/kind=bubble contract the real runner's output must satisfy once merged, rather than skipping the assertion or importing code that does not exist yet in this branch"
  - "Route enumeration and grep-based acceptance checks against a bare `python -c` invocation silently pick up the main checkout's installed src/ (editable install), not the worktree — verification must set PYTHONPATH=src (or run under pytest, which already does this via pyproject.toml's pythonpath) or it validates stale code"

requirements-completed: [PROT-01, PROT-02, PROT-03]

# Metrics
duration: ~40min
completed: 2026-08-16
---

# Phase 2 Plan 9: Protected-Mask Editing Routes Summary

**Protected masks get the same editing vocabulary panels have — list, hand-draw, move-vertex, replace-polygon, delete — plus the one thing panels don't need: a `touched` flip that turns a dashed detector proposal solid the instant the artist reshapes or hand-draws it.**

## What Was Built

**Task 1 — `src/comiccolor/web/routers/protected.py`:** five routes added
to the plan-02-05 stub (adapter, ownership helper, and not-found constant
were already there):

- `GET /api/pages/{page_id}/protected` — the whole page's mask list
  (`_masks_response`), docstring recording D-20's "no per-panel listing
  route" decision.
- `POST /api/pages/{page_id}/protected` — hand-draw a bubble or SFX mask
  (D-24: `kind` comes from the request body, since the detector only ever
  proposes bubbles), born `touched=True`. Validates the polygon against
  `(0, 0, page.width, page.height)` (422, `POLYGON_OUT_OF_PAGE_DETAIL`)
  before checking the page's mask count against
  `MAX_MASKS_PER_PAGE = 256` (409, `TOO_MANY_MASKS_DETAIL`), then computes
  `area`/`bbox` via `protected_bbox_and_area` and persists.
- `PATCH /api/protected/{mask_id}/vertex/{vertex_index}` — moves exactly
  one vertex (400 on an out-of-range index), re-checks page bounds on the
  mutated polygon, and calls `store.update_protected_mask_polygon`, which
  unconditionally sets `touched`.
- `PATCH /api/protected/{mask_id}/polygon` — wholesale replace for vertex
  insert/delete, same bounds check and `touched` flip.
- `DELETE /api/protected/{mask_id}` — 204, no confirmation step (D-19).

A new `_polygon_within_page` helper is the single page-bounds check every
create/write route calls. No `panel_id`, no `async def`, no raw SQL
anywhere in the module (all grep-verified).

**Task 2 — `tests/test_web/test_protected_routes.py`:** 10 tests covering
hand-drawn bubble and SFX creation, the reshape-then-delete round trip
(`test_reshape_and_delete`, named exactly as 02-VALIDATION.md expects),
move-vertex touching only the targeted point, a detector-proposed-shaped
listing asserting `touched is False`, the straddling-mask route-level test
(one POST, one row in the list, `rasterize_protected_for_panel` non-empty
against both panels — D-20 and success criterion 4), out-of-page-bounds
422, over-512-vertex 422 (schema-level), unknown-id 404 across all three
mutating routes, and the no-open-project 409.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `run_protected` (plan 02-07) is unavailable in this worktree**

- **Found during:** Task 2, writing `test_detector_proposed_masks_are_untouched_bubbles`.
- **Issue:** The plan's behavior spec calls for this test to run
  `run_protected` directly against a `Store`. Plan 02-07 is wave 3 — the
  same wave as this plan — and was not yet merged into this worktree
  (`src/comiccolor/pipeline/runner.py` has no `run_protected`, and that
  file belongs to 02-07's file list, not this plan's, so writing it here
  would collide with a sibling agent's in-progress work).
- **Fix:** The test constructs the detector-shaped row directly through
  `Store.add_protected_mask` (`touched=False`, `kind=ProtectedKind.BUBBLE`)
  instead of calling `run_protected`, then asserts the list route reports
  exactly that shape. This pins the same contract (`touched=False`/
  `kind=bubble` for a detector-proposed mask) that `run_protected`'s real
  output must satisfy once 02-07 merges, without depending on code this
  plan cannot touch. A comment in both the module docstring and the test
  itself explains why.
- **Files modified:** `tests/test_web/test_protected_routes.py` only —
  no production code affected.
- **Commit:** `0e14fae`

**2. [Rule 3 - Blocking] `python -c` route/grep verification silently used the main checkout, not the worktree**

- **Found during:** Task 1 acceptance-criteria verification.
- **Issue:** `python -c "from comiccolor.web.app import create_app..."`
  resolved `comiccolor` from the main checkout's installed `src/` (an
  editable install), not this worktree's `src/`, because a bare `python -c`
  has no `pyproject.toml`-driven `pythonpath` injection the way pytest
  does. The route walk against that install found zero protected/panel
  routes — not because the routes were missing, but because it was
  inspecting stale code.
- **Fix:** Re-ran the same verification with `PYTHONPATH=src` set from the
  worktree root, confirming all five routes register
  (`list_protected`, `create_mask`, `move_mask_vertex`,
  `replace_mask_polygon`, `delete_mask`) under `protected.router.routes`.
  Documented as a `key-decision` above so a future plan's ad-hoc `python -c`
  verification in a worktree does the same.
- **Files modified:** None (verification-only).
- **Commit:** n/a.

### None further — plan executed as written otherwise.

## Self-Check: PASSED
