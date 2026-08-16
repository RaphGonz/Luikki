---
phase: 02-panel-polygon-editor-protected-masks
plan: 07
subsystem: pipeline
tags: [pipeline, runner, stage-registry, panels, protected-masks, tdd]

# Dependency graph
requires:
  - "02-02: box_to_polygon, PanelParams.min_solidity=0.25/reading=\"ltr\" defaults"
  - "02-03: Store.add_panel/panels_for_page/delete_panels_for_page, Store.add_protected_mask/protected_for_page/delete_protected_for_page"
  - "02-04: detect_bubbles, mask_to_polygon (comiccolor.segmentation.bubbles)"
provides:
  - "src/comiccolor/pipeline/runner.py — run_panels(store, page), run_protected(store, page), BubbleDetectionFailed, BUBBLE_DETECTION_FAILED_MESSAGE"
  - "src/comiccolor/pipeline/stages.py — PANELS and PROTECTED stages now carry live runners"
affects: ["02-08", "02-09", "02-11"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Stage runners resolve a page's raster the same way the route layer does: store.path.parent / page.source_path, matching web/routers/page.py's get_page_image — one resolution path, not two."
    - "Both runners import segmentation modules (cv2-backed) locally inside the function body, never at module level, preserving pipeline/runner.py's existing import-direction discipline (pipeline stays importable without OpenCV for callers that never run a stage)."
    - "Delete-then-insert on every runner invocation makes re-running a stage idempotent by construction — no separate 'has this already run' check needed."

key-files:
  created: []
  modified:
    - src/comiccolor/pipeline/runner.py
    - src/comiccolor/pipeline/stages.py
    - tests/test_pipeline.py
    - tests/test_web/test_page_routes.py

key-decisions:
  - "D-17/D-18/D-20/D-24 implemented as specified in 02-CONTEXT.md; no reinterpretation."
  - "run_panels calls segment_panels(line_mask) with no explicit PanelParams instance, relying entirely on the dataclass's own defaults (min_solidity=0.25, reading=\"ltr\") rather than constructing and passing a params object that would just restate them — keeps the D-18/UI-SPEC decisions living in exactly the one place (panels.py) the plan's docstring instruction requires."
  - "FileNotFoundError is raised by an explicit image_path.is_file() check before calling load_line_art, rather than relying on load_line_art's own FileNotFoundError (which it already raises via cv2.imread returning None) — the explicit check lets the message name the page id, which load_line_art's generic 'could not read image: {path}' does not."

requirements-completed: [PAN-01, PROT-01, PROT-04]

# Metrics
duration: 40min
completed: 2026-08-16
---

# Phase 2 Plan 7: Panels and Protected Stage Runners Summary

**`run_panels` and `run_protected` are now live in the stage registry — an imported page's line art can be turned into reading-ordered four-vertex panel polygons and, separately, into detector-proposed bubble masks, both persisted, both idempotent on re-run, neither advancing the page's own gate, and a bubble-detection failure surfacing as a typed `BubbleDetectionFailed` carrying the UI-SPEC §4 banner copy rather than trapping the artist.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 3 (Tasks 1-2 `type="auto" tdd="true"`, Task 3 `type="auto"`)
- **Files modified:** 4 (0 created)

## Accomplishments

- `src/comiccolor/pipeline/runner.py`:
  - `run_panels(store, page)`: resolves `store.path.parent / page.source_path`
    exactly as `web/routers/page.py`'s `get_page_image` does, raises
    `FileNotFoundError` naming the page id when the file is missing, loads
    the line mask via `load_line_art`, calls `segment_panels(line_mask)`
    (already reading-ordered, defaults carrying D-18's lowered
    `min_solidity` and UI-SPEC §7's `ltr` default), deletes the page's
    existing panels, and persists each box as a `Panel` with
    `polygon=box_to_polygon(box)` and `reading_order=index`. Does not touch
    `page.stage` — the registry declares, it never orchestrates (D-10); the
    artist's own "Confirm & Continue" is what advances a page whose output
    is meant for review.
  - `run_protected(store, page)`: same raster resolution and
    `FileNotFoundError` behavior. Calls `detect_bubbles(grey, line_mask)`
    inside a `try`; any exception is re-raised as `BubbleDetectionFailed`
    chained via `raise ... from exc`, carrying the new module-level
    `BUBBLE_DETECTION_FAILED_MESSAGE` constant (UI-SPEC §4's exact copy, one
    place only). Zero detected bubbles is not an error — it persists zero
    masks and returns normally, since a splash page with no dialogue is
    legitimate. On success: deletes the page's existing protected masks,
    then for each detected mask calls `mask_to_polygon`, skips any trace
    under 3 vertices, computes `area`/`bbox` via
    `protected_bbox_and_area`, and persists a `ProtectedMask` with
    `kind=ProtectedKind.BUBBLE` (D-24: detector output is always a bubble by
    construction) and `touched=False` (UI-SPEC §3: dashed outline until
    reshaped). Does not touch `page.stage`, same reasoning as `run_panels`.
  - Both runners import their segmentation dependencies (`segment_panels`,
    `box_to_polygon`, `load_line_art`, `detect_bubbles`, `mask_to_polygon`,
    `protected_bbox_and_area`) inside the function body, not at module
    level — the existing discipline this module's docstring already states,
    keeping `pipeline` importable without pulling in OpenCV for callers
    that never actually run a stage.
- `src/comiccolor/pipeline/stages.py`: `PANELS` and `PROTECTED` `Stage`
  entries now carry `runner=run_panels` / `runner=run_protected`;
  `display_name`, `upstream`, `produces` unchanged on both. `Stage.runner`'s
  docstring updated to say six of eight stages remain declared without a
  runner as of Phase 2, so the note stays accurate instead of reading as
  stale against the two now-live entries.
- `tests/test_pipeline.py`: 11 new tests — `run_panels` persistence,
  polygon-shape, reading-order, idempotence and missing-source-path
  coverage; `run_protected` persistence (`kind`/`touched`/polygon/area),
  the legitimate-zero-bubbles case, idempotence, the
  `BubbleDetectionFailed` path (monkeypatched `detect_bubbles`, asserts the
  prior successful run's masks survive the subsequent failure), and missing
  source path; a registry test replacing the old "only import has a runner"
  assertion with "exactly import/panels/protected have a runner"; a new
  test proving `run_stage(store, page, PANELS)` does not also run
  `protected` and does not advance `page.stage` (D-10). A `_two_panel_grid_image`
  helper (raster PNG builder) lives in this file rather than
  `conftest.py`, since only this plan's runner tests need a real on-disk
  raster — the existing in-memory array builders in `conftest.py`
  (`bubble_page`, `boundary_crossing_page`) stay plan 02-01's, and this
  plan reuses `bubble_page` directly via `cv2.imwrite` of its returned
  `grey` array rather than duplicating bubble-page construction.

## Task Commits

Each task was committed atomically, RED then GREEN per the TDD gate for Tasks 1-2:

1. **Task 1+2 — `run_panels` and `run_protected` (combined RED/GREEN, one
   behavioral test file covering both runners together)**
   - `aed6c4e` (test): 11 failing tests, `ImportError` on missing
     `run_panels`/`run_protected`/`BubbleDetectionFailed` (RED)
   - `2d34265` (feat): both runners implemented, `pytest tests/test_pipeline.py -x -q`
     18/18 green, `pytest tests/ -q` 196 passed + 2 xfailed (GREEN)
2. **Task 3 — Wire both runners into the stage registry**
   - `df35652` (feat): `stages.py` wiring, registry-test updates, and the
     one existing route test (`test_pipeline_stages_endpoint_lists_eight_stages`)
     updated for the new `has_runner` count; `pytest tests/test_pipeline.py tests/test_web/ -x -q`
     103 passed, `pytest tests/ -q` 197 passed + 2 xfailed

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `src/comiccolor/pipeline/runner.py` — `run_panels`, `run_protected`, `BubbleDetectionFailed`, `BUBBLE_DETECTION_FAILED_MESSAGE`
- `src/comiccolor/pipeline/stages.py` — `runner=run_panels`/`run_protected` on the PANELS/PROTECTED entries, docstring update
- `tests/test_pipeline.py` — 12 new tests (11 runner behavior + 1 registry no-chain-walk), 1 registry test rewritten, 2 new fixtures + 1 raster builder helper
- `tests/test_web/test_page_routes.py` — `has_runner` count assertion updated from 1 to 3 (Rule 1, see Deviations)

## Decisions Made

- Implemented D-17, D-18, D-20, D-24 exactly as locked in `02-CONTEXT.md`;
  no re-derivation.
- `run_panels` calls `segment_panels(line_mask)` with no explicit
  `PanelParams()` instance — the function's own default already is
  `PanelParams()`, and constructing one here would just restate values the
  plan's own docstring instruction says belong in exactly one place
  (`panels.py`'s dataclass defaults).
- `FileNotFoundError` is raised via an explicit `image_path.is_file()`
  check ahead of `load_line_art`, rather than relying on
  `load_line_art`'s own `FileNotFoundError` (it already raises one, since
  `cv2.imread` on a missing path returns `None`) — the explicit check lets
  the message name the page id, per the plan's action text, which
  `load_line_art`'s generic `"could not read image: {path}"` does not.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_pipeline_stages_endpoint_lists_eight_stages` asserted the Phase 1 baseline (`has_runner` count == 1)**
- **Found during:** Task 3, running `pytest tests/test_pipeline.py tests/test_web/ -x -q`
- **Issue:** `tests/test_web/test_page_routes.py` had a test asserting
  exactly one stage (`import`) reports `has_runner: true` from the
  `/api/pipeline/stages` route — true under Phase 1, now stale the moment
  `PANELS`/`PROTECTED` get real runners. Task 3's own `read_first` note
  flagged this exact file and line as something "this change flips two of
  its eight entries" on, so the test needing an update was expected, not a
  surprise; it was simply not listed in the plan's `files_modified`.
- **Fix:** Updated the assertion to expect exactly three stages
  (`import`, `panels`, `protected`, in that positional order) reporting
  `has_runner: true`, and the remaining five reporting `false`.
- **Files modified:** `tests/test_web/test_page_routes.py`
- **Verification:** `pytest tests/test_pipeline.py tests/test_web/ -x -q` — 103 passed.
- **Commit:** `df35652`

## Issues Encountered

The plan's acceptance criterion `python -c "from comiccolor.pipeline import STAGES; ..."` returned `['import']` only when run as a bare `python -c` from this worktree, because the venv's editable install resolves `comiccolor` to the *main checkout's* `src/`, not this worktree's — the environment brief's own note that pytest resolves the worktree's `src/` via `pythonpath` while a bare interpreter invocation does not. Re-running with `PYTHONPATH=src` pointed at the worktree confirmed `['import', 'panels', 'protected']`, matching the plan's expected output; `pytest` itself (which is what actually exercises this code under test) was green throughout. Documented here rather than as a deviation, since no code needed changing — only the verification method for that one ad hoc grep.

## User Setup Required

None.

## Next Phase Readiness

- Three of eight stages are now live: `import`, `panels`, `protected`. The
  remaining five (`zones`, `propose`, `snap`, `review`, `export`) stay
  declared with `runner=None` per D-11, refusing via
  `StageNotImplementedError` until later phases fill them in.
- `Panel.polygon` and `ProtectedMask` (page-scoped, `touched`, `kind`) are
  now populated by real pipeline runs, not just testable in isolation —
  ready for the panel/protected editor routes and frontend (later plans in
  this wave/phase) to read real, persisted data.
- `BubbleDetectionFailed` and `BUBBLE_DETECTION_FAILED_MESSAGE` are ready
  for whichever route plan wires the `protected` stage's HTTP endpoint to
  catch this exception and render the UI-SPEC §4 non-blocking banner.
- `frontend/src/components/stageStrip.ts` was not touched, preserving its
  deliberate blindness to `has_runner` (STATE.md).
- No blockers for downstream Phase 2 plans.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16*
