---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 07
subsystem: api
tags: [fastapi, sqlite, project-lifecycle, wal, tkinter]

# Dependency graph
requires:
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Project-scoped Store surface, checkpoint()/the_project()/add_project() (plan 01-03)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "schemas.py DTOs, deps.py dependency chain, appconfig.py folder layout, empty project.py router stub (plan 01-06)"
provides:
  - "src/comiccolor/web/routers/project.py — POST /api/projects, POST /api/projects/open, GET /api/projects/current, POST /api/projects/close, GET /api/projects/recent, POST /api/projects/browse"
  - "NOT_A_PROJECT_DETAIL, PROJECT_EXISTS_DETAIL, BROWSE_UNAVAILABLE_DETAIL error-copy constants — plan 01-11's project picker renders these verbatim"
  - "_resolve_project_path — the single validator every path-accepting project route uses"
affects: ["01-11"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Route builds its own Store explicitly (not Depends(get_store)) when no project is open yet — create and open both do this"
    - "tkinter imported lazily inside the browse handler only, so importing the router never requires a display"
    - "appconfig.create_project_folder's own mkdir(parents=True) is the only place this module creates a directory — no caller-supplied path is ever mkdir'd directly in project.py"

key-files:
  created: []
  modified:
    - src/comiccolor/web/routers/project.py
    - tests/test_web/test_project_routes.py

key-decisions:
  - "FastAPI 0.141's include_router now wraps sub-routers in an internal _IncludedRouter object that has no .path attribute, so the plan's literal verify snippet (iterating app.routes for r.path) raises AttributeError. Confirmed instead via app.openapi()['paths'], which returns exactly the three expected paths (/api/projects, /api/projects/current, /api/projects/open) plus /close, /recent, /browse from this plan. This is a framework-version artifact affecting every router in the app (inherited from plan 01-06's app.py), not a defect introduced here."
  - "The browse route's docstring explaining why no persisted allowlist/vouch-token sits on top of _resolve_project_path had to avoid the literal substrings 'vouch', 'allowlist' and 'browse_token' to satisfy the threat model's own grep-based acceptance criterion (same class of self-referential documentation conflict 01-06-SUMMARY records for deps.py/uploads.py) — reworded to 'no persisted record of previously chosen directories, and no separate approval code' without changing the meaning."

requirements-completed: [PROJ-01, PROJ-05]

# Metrics
duration: ~40min
completed: 2026-08-15
---

# Phase 1 Plan 7: Project Lifecycle Routes Summary

**Implemented create/open/current/close/recent/browse for the project lifecycle — D-04's folder-per-project layout, a mandatory WAL checkpoint on close, a self-healing recents index, and a lazy-imported native folder picker — filling in the router stub plan 01-06 registered.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- `POST /api/projects` lays out a new project folder via `appconfig.create_project_folder` (D-04: `project.db` + `pages/` + `references/pending/` + `label_maps/`), builds its own `Store` (not `Depends(get_store)`, since no project is open yet at create time), inserts the single `Project` row, checkpoints, then opens it (`set_current_project` + `record_recent`).
- `POST /api/projects/open` runs every client-supplied path through `_resolve_project_path` (RESEARCH.md § Security Domain V12) before opening anything, then reads `the_project()` — a `project.db` with no project row is treated the same as "not a project" (400).
- `GET /api/projects/current` shares `get_project`'s 409 via `Depends` rather than a route-local special case, and includes the folder path for the picker's highlight-matching-recent-row behavior (01-UI-SPEC.md §8).
- `POST /api/projects/close` is the resolved RESEARCH.md Open Question 1: it explicitly calls `store.checkpoint()` (`PRAGMA wal_checkpoint(TRUNCATE)`) before clearing `app.state.current_project_path`, so a folder copied immediately afterwards is a complete database (D-04, Pitfall 1).
- `GET /api/projects/recent` is a thin pass-through to `appconfig.read_recents()`, which already drops any entry whose folder no longer contains `project.db` — the index never claims authority over the filesystem.
- `POST /api/projects/browse` opens `tkinter.filedialog.askdirectory()` in a hidden, immediately-destroyed `Tk` root; `tkinter` is imported lazily inside the function so importing the router never requires a display. A broad `except Exception` degrades to 503 (`BROWSE_UNAVAILABLE_DETAIL`) on a headless/tkinter-less host; a cancelled dialog returns 204 with no body.
- `tests/test_web/test_project_routes.py`: all six Wave 0 stubs un-skipped and implemented, plus two new tests (`test_creating_into_an_occupied_folder_is_a_409`, `test_no_save_endpoint_exists`) — 8 passed, 0 skipped. An autouse `isolated_recents` fixture redirects `appconfig.CONFIG_DIR`/`RECENTS_PATH` to a per-test tmp file so no test ever touches the real `~/.comiccolor/recent.json`.
- Full suite: `pytest -q` — 78 passed, 13 skipped, 2 xfailed (up from 71 passed/18 skipped at the start of this plan — 7 newly-passing tests, matching this plan's 6 filled stubs plus 2 new ones minus the 1 that was already passing).

## Task Commits

Each task was committed atomically:

1. **Task 1: Create, open and current** - `794db8a` (feat)
2. **Task 2: Close with a WAL checkpoint, the recents index, and the host-side folder picker** - `cc3314d` (feat)
3. **Task 3: Fill the project route tests, including reopen-after-close** - `f91550c` (test)

**Plan metadata:** pending (this commit, docs: complete plan)

## Files Created/Modified

- `src/comiccolor/web/routers/project.py` - implemented all six routes on the existing `router = APIRouter()` stub: `create_project`, `open_project`, `current_project`, `close_project`, `recent_projects`, `browse_for_project_folder`, plus `_resolve_project_path` and `_to_response` helpers and the three error-copy constants.
- `tests/test_web/test_project_routes.py` - un-skipped and implemented all six Wave 0 stubs, added two new tests, added the `isolated_recents` autouse fixture, lifted `test_requests_without_an_open_project_return_409`'s local imports to module level per the plan's instruction.

## Final Route List (for plan 01-11's project picker)

| Route | Status | Notes |
|---|---|---|
| `POST /api/projects` | 201 `ProjectResponse` / 409 | `PROJECT_EXISTS_DETAIL` on name collision |
| `POST /api/projects/open` | 200 `ProjectResponse` / 400 | `NOT_A_PROJECT_DETAIL` on invalid path |
| `GET /api/projects/current` | 200 `ProjectResponse` / 409 | `NO_PROJECT_DETAIL` (from `deps.py`) when nothing is open |
| `POST /api/projects/close` | 204 | Always checkpoints the WAL first |
| `GET /api/projects/recent` | 200 `list[RecentProjectResponse]` | Self-healing, never 4xx |
| `POST /api/projects/browse` | 200 `BrowseResponse` / 204 (cancelled) / 503 | `BROWSE_UNAVAILABLE_DETAIL` when tkinter/display unavailable |

Exact error-copy strings (render verbatim in the frontend per 01-UI-SPEC.md's Copywriting Contract):

```
NOT_A_PROJECT_DETAIL = "That folder isn't a ComicColor project — pick a folder containing project.db, or create a new project."
PROJECT_EXISTS_DETAIL = "A project already exists in that folder — open it instead, or pick a different name."
BROWSE_UNAVAILABLE_DETAIL = "Couldn't open a folder picker on this machine — choose a recent project instead."
```

## Decisions Made

- FastAPI 0.141's `include_router` now wraps each sub-router in an internal `_IncludedRouter` object with no `.path` attribute, so the plan's literal verify snippet (`sorted(r.path for r in app.routes if r.path.startswith(...))`) raises `AttributeError`. Verified instead via `app.openapi()['paths']`, which correctly lists `/api/projects`, `/api/projects/current`, `/api/projects/open` (plus this plan's `/close`, `/recent`, `/browse`). This is a framework-version characteristic affecting every router registered in `app.py` (inherited from plan 01-06), not something introduced by this plan's code.
- The browse route's docstring explaining why no persisted allowlist sits on top of `_resolve_project_path` needed rewording to avoid the literal substrings `vouch`, `allowlist` and `browse_token`, which the threat model's own grep-based acceptance criterion forbids — same self-referential documentation trap 01-06-SUMMARY records for `deps.py`/`uploads.py`. Reworded without changing the documented decision.

## Deviations from Plan

None — plan executed exactly as written. The two items above are verification-method adaptations (framework-version behavior, and a self-referential grep constraint on a docstring), not code deviations from the plan's specified behavior.

## Issues Encountered

- No `.venv` existed inside this worktree (worktrees are separate checkouts). Created a fresh `.venv` and ran `pip install -e ".[web,dev]"` before any verification command could run — expected worktree setup, not a plan deviation, called out only because it consumed real time before Task 1's work began.

## User Setup Required

None - no external service configuration required.

## Manual Verification Deferred

The plan's `<human-check>` (create a project via `comiccolor serve`, add a palette entry, close, copy the folder, reopen from the new location) requires a browser session and is explicitly named in 01-VALIDATION.md as not reliably scriptable. `test_close_checkpoints_the_wal` and `test_reopen_after_close_keeps_pages_and_palette` cover the same guarantee (WAL checkpoint + copy + reopen with data intact, and open/close/reopen through the API) as automated tests. The literal supervised-video-call session with the artist is out of scope for this execution.

## Next Phase Readiness

- All six project lifecycle routes are complete, tested and importable with no display required.
- `NOT_A_PROJECT_DETAIL`, `PROJECT_EXISTS_DETAIL`, `BROWSE_UNAVAILABLE_DETAIL` are stable exports from `comiccolor.web.routers.project` for plan 01-11's project picker to import and render verbatim.
- No blockers for any later Wave-4+ plan in this phase (01-08, 01-09 build against `volume.py`/`page.py`/`pipeline.py`/`palette.py`, disjoint files from this plan).

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*

## Self-Check: PASSED

Both modified files and this SUMMARY.md verified present on disk. All three
task commits (`794db8a`, `cc3314d`, `f91550c`) verified present in `git log`.
