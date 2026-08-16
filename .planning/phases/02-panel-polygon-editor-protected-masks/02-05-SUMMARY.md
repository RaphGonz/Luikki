---
phase: 02-panel-polygon-editor-protected-masks
plan: 05
subsystem: api
tags: [fastapi, pydantic, panels, protected-masks, geometry-validation]

# Dependency graph
requires:
  - phase: 02-03
    provides: page-scoped Panel/ProtectedMask entities and Store CRUD (panel_by_id, protected_mask_by_id, panels_for_page, update_panel_polygon, update_protected_mask_polygon)
provides:
  - Bounded Pydantic geometry types (PixelCoord, Vertex, Polygon) that refuse oversized/out-of-range polygons with 422 before any handler runs
  - Every request/response model plans 02-08, 02-09 and 02-11 will consume (Panel/ProtectedMask create/response/list, StageConfirmResponse, GoBackTargetResponse, GoBackRequest)
  - Two registered-but-routeless routers (panel.router, protected.router) with their ownership helpers and response adapters
  - Public get_owned_page (renamed from _get_owned_page) as the cross-router ownership import point
affects: [02-08, 02-09, 02-11]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bounded geometry types at the Pydantic boundary (MAX_PAGE_PIXEL, MAX_POLYGON_VERTICES) mirror RGBTuple/ProjectName's constrained-field convention, stopping hostile geometry before cv2.fillPoly sees it"
    - "Ownership-chain helpers (_get_owned_panel -> get_owned_page, _get_owned_protected_mask -> get_owned_page) mirror get_owned_volume's T-01-IDOR framing one level deeper"
    - "Route-flattening test helper (walk original_router through _IncludedRouter) pinned as the correct way to enumerate a specific router's contributed paths under FastAPI 0.141.1's lazy include_router"

key-files:
  created:
    - src/comiccolor/web/routers/panel.py
    - src/comiccolor/web/routers/protected.py
    - tests/test_web/test_geometry_schemas.py
  modified:
    - src/comiccolor/web/schemas.py
    - src/comiccolor/web/routers/page.py
    - src/comiccolor/web/app.py

key-decisions:
  - "MAX_PAGE_PIXEL=100_000 and MAX_POLYGON_VERTICES=512 bound every polygon body this phase accepts, per 02-RESEARCH.md's two DoS rows"
  - "_get_owned_page renamed to public get_owned_page so panel.py and protected.py can import it, following the get_owned_volume cross-router precedent page.py already set"
  - "Both routers mounted under a single /api prefix (not a per-resource prefix) since each serves two path families of its own; documented inline in app.py"

patterns-established:
  - "Pattern: constrained Pydantic type + module constant for any DoS-relevant bound, declared once in schemas.py alongside a comment explaining both the number and the honest-refusal rationale"
---

# Phase 02 Plan 05: Panel/Protected-Mask Web Contract Summary

Bounded polygon/vertex Pydantic types plus every request/response model this
phase's two new geometry routers need, and the router modules themselves —
each with one ownership helper and one response adapter, registered inside
`create_app()` with zero routes of their own so 02-08 and 02-09 can add
routes to separate files in parallel.

## What Was Built

**Task 1 — `src/comiccolor/web/schemas.py`:** `MAX_PAGE_PIXEL = 100_000` and
`MAX_POLYGON_VERTICES = 512` as module constants, `PixelCoord` (bounded int),
`Vertex` (a coordinate pair), and `Polygon` (`min_length=3,
max_length=MAX_POLYGON_VERTICES`) as the shared constrained types. Every
model this phase's routers will use: `VertexUpdateRequest`,
`PolygonUpdateRequest`, `PanelCreateRequest`, `PanelResponse`,
`PanelListResponse`, `ProtectedMaskCreateRequest`, `ProtectedMaskResponse`,
`ProtectedMaskListResponse`, `StageConfirmResponse`, `GoBackTargetResponse`,
`GoBackRequest`.

**Task 2 — `src/comiccolor/web/routers/panel.py` and `protected.py`:** each
module gets a response adapter (`_panel_response`, `_protected_response`),
an ownership helper (`_get_owned_panel`, `_get_owned_protected_mask`) that
resolves the row then re-checks ownership through `get_owned_page`, and
module-level not-found detail constants. `panel.py` also gets
`_panel_list_response` for the "return the whole page's panel list"
contract. `page.py`'s `_get_owned_page` was renamed to public
`get_owned_page` for the new cross-router import, mirroring the
`get_owned_volume` precedent `page.py` already used. Both routers are
registered in `app.py`'s `create_app()` under a shared `/api` prefix (with
an inline comment explaining why a per-resource prefix cannot express two
path families per router), so they inherit `_reject_foreign_origins`.
Neither router declares a route in this plan.

**Task 3 — `tests/test_web/test_geometry_schemas.py`:** direct
`pydantic.ValidationError` assertions pinning the 513-vertex-rejected /
512-vertex-accepted boundary (not just "large is bad"), the 2-vertex and
coordinate-range rejections, `VertexUpdateRequest`'s bound, and
`ProtectedMaskCreateRequest` rejecting an unknown `kind` string. A
route-level test walks `create_app()`'s routes (using the same
`original_router`-unwrapping technique already established in
`test_concurrency.py`, required because FastAPI 0.141.1's `include_router`
wraps each router in a lazy `_IncludedRouter` rather than flattening routes
onto `app.routes`) and asserts every path either new router contributes
starts with `/api`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 2's literal verify command fails against this FastAPI version's lazy router objects**

- **Found during:** Task 2 verification
- **Issue:** The plan's suggested verify command (`for r in app.routes if
  r.path.startswith('/api')`) raises `AttributeError: '_IncludedRouter'
  object has no attribute 'path'`. FastAPI 0.141.1's `include_router` wraps
  each sub-router in a lazy `_IncludedRouter` that holds the real
  `APIRoute` objects on `.original_router` rather than exposing them
  directly on `app.routes` — a fact `tests/test_web/test_concurrency.py`
  already documents and works around for a different question (WR-01's
  async-route check).
- **Fix:** Verified router registration with the same
  `original_router`-unwrapping walk `test_concurrency.py` established,
  confirming both routers mount cleanly with zero routes and `/api/health`
  is the only currently-registered `/api` path. Task 3's route-level test
  uses the identical technique so it will actually enumerate routes once
  02-08/02-09 add them.
- **Files modified:** None (verification-only; the production code the
  plan specified was unaffected)
- **Commit:** n/a (no code change — verification method adjusted)

### None further — plan executed as written otherwise.

## Self-Check: PASSED

- FOUND: src/comiccolor/web/routers/panel.py
- FOUND: src/comiccolor/web/routers/protected.py
- FOUND: tests/test_web/test_geometry_schemas.py
- FOUND: commit 3d1d9fb (Task 1)
- FOUND: commit f6370b3 (Task 2)
- FOUND: commit 12e6901 (Task 3)
- `pytest tests/ -q`: 178 passed, 2 xfailed (baseline was 168 passed, 2 xfailed; +10 new tests, 0 regressions)
