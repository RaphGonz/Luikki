---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 09
subsystem: api
tags: [fastapi, palette, sqlite, uploads]

# Dependency graph
requires:
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Project-scoped Store palette/region/panel/page surface (plan 01-03)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "extract_palette/ExtractedColour/EmptyImageError (plan 01-05)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "schemas.py DTOs, deps.py, uploads.py, app.py router registration and EmptyImageError handler (plan 01-06)"
provides:
  - "GET/POST /api/palette, PATCH/DELETE /api/palette/{entry_id}, POST /api/palette/swatch — the complete palette HTTP surface"
  - "_entry_response/_next_colour_number helpers and ENTRY_NOT_FOUND_DETAIL/AUTO_NAME_PREFIX constants in src/comiccolor/web/routers/palette.py"
  - "5 filled route tests in tests/test_web/test_palette_routes.py (3 required stubs + 2 added)"
affects: ["01-13"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sync def, not async def, for any route mixing UploadFile with the get_store dependency — FastAPI runs sync path operations and their sync dependencies on the same thread-pool thread, which Store's 'one Store per thread' sqlite contract requires; async def would split the connection across threads and raise sqlite3.ProgrammingError"
    - "APIRouter path decorators use \"\" not \"/\" for the router root, so the mounted path is exactly /api/palette (no trailing slash) rather than /api/palette/ — matches the sibling routers' expected shape"

key-files:
  created: []
  modified:
    - src/comiccolor/web/routers/palette.py
    - tests/test_web/test_palette_routes.py

key-decisions:
  - "upload_swatch is a sync `def`, discovered mid-implementation: the plan's <read_first> didn't flag the async/thread-affinity interaction, and the first cut (async def + `await file.read()`) failed with sqlite3.ProgrammingError because get_store's connection was created on a threadpool thread while the async handler ran on the event loop thread. Fixed by making the route sync and reading via `file.file.read()` (Rule 1 - bug, caught before any commit)."
  - "The plan's Task 2 acceptance criterion 'an all-black swatch returns 400 (via the EmptyImageError handler)' does not hold given extract_palette's already-locked (plan 01-05) semantics: without sheet_mode, a single-colour image always survives as one 100%-share cluster, so EmptyImageError is never raised on the swatch path for any valid image. Deliberately not special-cased to force a rejection — a genuine solid-colour swatch is legitimate artist input under D-16, and inventing an all-black rejection would contradict 'no naming prompt blocks a working palette.' Verified empirically (10x10 pure-black PNG → 201, one entry, rgb [0,0,0])."

requirements-completed: [PAL-01, PAL-03, PAL-04]

# Metrics
duration: 45min
completed: 2026-08-15
---

# Phase 1 Plan 9: Palette Routes Summary

**The full palette HTTP surface — swatch extraction (PAL-01), hand CRUD (PAL-03) and single-row recolour with affected-page reporting (PAL-04) — implemented as thin marshalling over an already-complete `Store` mechanic, with zero pipeline-stage coupling anywhere in the module.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-08-15 (worktree wave 4)
- **Completed:** 2026-08-15
- **Tasks:** 3
- **Files modified:** 2

## Route list (final, for plan 01-13's palette grid and toast)

| Method | Path | Status | Response |
|---|---|---|---|
| GET | `/api/palette` | 200 | `list[PaletteEntryResponse]` |
| POST | `/api/palette` | 201 | `PaletteEntryResponse` |
| PATCH | `/api/palette/{entry_id}` | 200 | `PaletteUpdateResponse` (404 if unknown id) |
| DELETE | `/api/palette/{entry_id}` | 204 | none (404 if unknown id) |
| POST | `/api/palette/swatch` | 201 | `SwatchExtractResponse` (400 on unreadable image) |

`PaletteUpdateResponse` shape: `{entry: PaletteEntryResponse, pages_affected: int}` — `pages_affected` is `len(store.pages_affected_by(entry_id))`, computed fresh on every `PATCH`, whether or not `rgb` changed (a rename-only call also returns the current affected-page count, which is always a defined, non-error value).

Auto-naming rule: `AUTO_NAME_PREFIX = "Colour "`; `_next_colour_number` scans the project's existing entries for labels starting with that prefix followed by a digit, takes the max, and adds one. A fresh project starts at `Colour 1`. Hand-created or renamed entries never collide with this scan since they simply don't match the prefix pattern.

## Accomplishments

- `GET /api/palette`, `POST /api/palette` — project-scoped list/create (D-02: palette accumulates across every volume, never volume-scoped).
- `PATCH /api/palette/{entry_id}` — rename via `update_palette_label`, recolour via `update_palette_rgb` (exactly one call each, grep-verified), returns the affected-page count via `pages_affected_by`. No region row, no page stage, no re-run reference anywhere in the module (grep-verified against `set_page_stage|run_stage|run_import|invalidate|re-?run|stale`).
- `DELETE /api/palette/{entry_id}` — relies on the schema's `ON DELETE SET NULL`; docstring states the unpainted-vs-wrong-colour rationale.
- `POST /api/palette/swatch` — decodes via `uploads.decode_image`, extracts via `extract_palette(image)` (never `sheet_mode`), persists every colour immediately as a real `PaletteEntry`, saves the source image under `references/` via `uploads.save_upload`. Sync `def`, not `async def` — see key-decisions.
- `tests/test_web/test_palette_routes.py`: 5 tests passing (3 required + `test_a_second_swatch_continues_the_numbering`, `test_deleting_a_colour_leaves_its_regions_unpainted_not_wrong`), 4 character-sheet stubs left skipped for plan 01-10.
- Full suite: 76 passed, 15 skipped, 2 xfailed (baseline was 71/18/2 — exactly +5 passed, -3 skipped, matching the 3 unskipped stubs).

## Task Commits

1. **Task 1: Palette CRUD by hand, with recolour reporting its propagation set** - `fe2b210` (feat)
2. **Task 2: Swatch upload creates auto-named palette entries** - `c611dd4` (feat)
3. **Task 3: Fill the palette CRUD, swatch and recolour tests** - `6b1893d` (test)

## Files Created/Modified

- `src/comiccolor/web/routers/palette.py` (200 lines) - `router`, `_entry_response`, `_next_colour_number`, `ENTRY_NOT_FOUND_DETAIL`, `AUTO_NAME_PREFIX`, and the five routes above.
- `tests/test_web/test_palette_routes.py` (201 lines) - 5 tests filled/added, 4 character-sheet stubs untouched.

## Decisions Made

- **Sync route for the upload endpoint.** `POST /api/palette/swatch` mixes `UploadFile` with `Depends(get_store)`. The first implementation used `async def upload_swatch(...)` with `await file.read()`, following an instinct that "upload handler = async." It failed immediately in manual verification with `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread` — FastAPI runs `async def` path operations directly on the event loop, but `get_store` is a regular `def` generator dependency, which FastAPI runs in the thread pool via `run_in_threadpool`. The sqlite connection ends up created on a threadpool thread and then used from the event-loop thread. Fixed by making the route `def` (not `async def`) and reading the upload via `file.file.read()` instead of `await file.read()` — this keeps the whole request, dependency included, on one thread-pool thread, matching `Store`'s documented "one Store per thread" contract. Caught and fixed before any commit (Rule 1 — bug, not a deviation to the plan's intent).
- **`APIRouter` path decorators use `""` not `"/"`.** With the router mounted at prefix `/api/palette`, `@router.get("/")` would produce `/api/palette/` (trailing slash), which the plan's own route-introspection acceptance check expects to be exactly `/api/palette`. Used `""` for the collection routes (`GET`/`POST`) so the mounted path has no trailing slash.
- **The "all-black swatch → 400" acceptance criterion does not hold** given `extract_palette`'s already-locked (plan 01-05) behaviour — see key-decisions above for the full reasoning. Not treated as a bug to fix by special-casing; documented instead, since forcing a rejection would itself violate D-16.

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 - Bug] `async def` + sync `Store` dependency crashed with a cross-thread sqlite error**
- **Found during:** Task 2, first manual verification run of the swatch route
- **Issue:** `async def upload_swatch(...)` ran on the event loop thread while `Depends(get_store)` (a sync generator dependency) ran its sqlite connection setup in FastAPI's thread pool; the handler's `store.palette_for_project(...)` call then hit `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread.`
- **Fix:** Changed the route to `def upload_swatch(...)` (sync) and switched `await file.read()` to `file.file.read()`. Documented the reasoning in the route's own docstring so a future edit doesn't silently reintroduce `async def` here.
- **Files modified:** `src/comiccolor/web/routers/palette.py`
- **Commit:** `c611dd4`

### Documented discrepancies (not fixed)

**1. Task 2's "all-black swatch returns 400" acceptance criterion is unreachable as stated**
- `extract_palette(image)` without `sheet_mode` (the swatch path never sets it, per D-14) always returns at least one surviving cluster for any non-degenerate image — a solid-colour image quantizes to exactly one cluster at 100% share, which clears `MIN_PIXEL_SHARE` trivially. `EmptyImageError` is therefore never raised on this path for a real image; it is only reachable through `_drop_ink_and_paper`, which is sheet-only. Verified empirically: a 10x10 pure-black PNG posted to `/api/palette/swatch` returns `201` with one entry (`Colour N`, `rgb: [0, 0, 0]`), not `400`.
- Not treated as a bug: rejecting a genuine solid-colour swatch would contradict D-16 ("no naming prompt blocks a working palette") and PAL-01's contract that the app creates entries from whatever colours a swatch actually contains. The inline `<verify>` script for Task 2 (the actual required automated check) does not test this case — it tests a corrupt-bytes upload, which correctly returns 400 via `uploads.decode_image`, and that path is covered.
- No code change made; flagged here for whoever revisits `extract_palette`'s constants during the supervised video-call tuning sessions the 01-05 SUMMARY already anticipates.

## Issues Encountered

- The plan's literal route-introspection acceptance command (`r.path for r in a.create_app().routes if r.path.startswith(...)`) does not work as written against the installed `fastapi==0.141.1`: `app.include_router(...)` now produces a `fastapi.routing._IncludedRouter` wrapper object with no `.path` attribute at the top level, rather than exposing child routes flattened into `app.routes` directly. This is a framework-version detail unrelated to this plan's code — verified the actual mounted paths instead via `included_router.original_router.routes`, confirming exactly `/api/palette` (GET, POST) and `/api/palette/{entry_id}` (PATCH, DELETE) as required. No project code was changed to work around this; it only affected how I verified the route list manually.
- This worktree has no `.venv/`; verification used the global `python` after `python -m pip install -e ".[web,dev]"` per the environment note.
- `POST /api/projects` is not yet implemented in this worktree (plan 01-07 runs in a sibling worktree, not yet merged at this base commit), so manual verification opened a project directly via `Store` + `set_current_project`, mirroring the `client` fixture in `tests/test_web/conftest.py`, rather than going through the project-creation route as the plan's own inline verify script assumed.

## User Setup Required

None.

## Next Phase Readiness

- Plan 01-13 (palette grid UI) can consume the route list, `PaletteUpdateResponse` shape, and auto-naming rule documented above directly — no further backend changes anticipated for the palette surface within this phase.
- Plan 01-10 (character sheets) owns the four remaining skipped stubs in `tests/test_web/test_palette_routes.py` and can extend `_entry_response` (already the single shared adapter) rather than duplicating it.
- No blockers for downstream plans in this phase.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*

## Self-Check: PASSED

All created/modified files verified present on disk (`src/comiccolor/web/routers/palette.py`,
`tests/test_web/test_palette_routes.py`, this SUMMARY.md). All three task commits (`fe2b210`,
`c611dd4`, `6b1893d`) verified present in `git log`.
