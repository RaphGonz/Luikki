---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 04
subsystem: pipeline
tags: [dataclass, registry, sqlite, pytest]

# Dependency graph
requires:
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Wave 0 test scaffolding (tests/test_pipeline.py skip-marked stubs) from plan 01-01"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "PipelineStage enum, page.stage column, Store.set_page_stage/page_by_id from plan 01-03"
provides:
  - "src/comiccolor/pipeline/ package: Stage dataclass, STAGES (8-entry declarative registry), stage_for, next_stage, StageRunner alias"
  - "run_import(store, page) — the only implemented stage runner this phase; persists page.stage=PANELS"
  - "run_stage(store, page, name) — thin dispatcher; raises StageNotImplementedError for undeclared runners, never walks the chain"
  - "LabelMapInvariantError + assert_invariant(label_map, line_mask, protected=None) in comiccolor.model.masks, exported from comiccolor.model"
affects: ["01-07", "01-11", "phase-3-zone-editor"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Declarative registry as a frozen-dataclass list (Stage/STAGES), not a Protocol multiple classes implement — stage_for/next_stage read it, nothing dispatches dynamically"
    - "One-way module dependency between stages.py and runner.py: stages.py imports run_import from runner.py at module level; runner.py resolves stage_for with a local import inside run_stage to avoid a module-level circular import"
    - "assert_invariant wraps check_coverage rather than reimplementing exhaustiveness/leak detection — edit-time enforcement (raise) layered over a reporting function (return dict)"

key-files:
  created:
    - src/comiccolor/pipeline/__init__.py
    - src/comiccolor/pipeline/stages.py
    - src/comiccolor/pipeline/runner.py
  modified:
    - src/comiccolor/model/masks.py
    - src/comiccolor/model/__init__.py
    - tests/test_masks.py
    - tests/test_pipeline.py

key-decisions:
  - "runner.py's full implementation (run_import, run_stage, StageNotImplementedError) was written in the Task 2 commit rather than deferred to Task 3, because stages.py imports run_import from it at module level — Task 2's own verification could not pass without runner.py existing first. Task 3's commit is the test file only."
  - "assert_invariant raises separately on uncovered pixels vs. leaked pixels rather than folding both into one check, because check_coverage still reports exhaustive=True when a label leaks onto a line/protected pixel (a leak is not a gap) — the leak needs its own explicit raise or it would pass silently."

patterns-established:
  - "Stage/STAGES frozen-dataclass registry: declares name, display_name, upstream, produces, runner per stage; a stage with runner=None is a normal declared-but-unimplemented state, not an error"

requirements-completed: [PROJ-04]

# Metrics
duration: ~30min
completed: 2026-08-15
---

# Phase 1 Plan 4: Pipeline Stage Registry and Label-Map Invariant Summary

**Declarative 8-stage pipeline registry (Stage/STAGES/stage_for/next_stage) with only `run_import` implemented, plus `assert_invariant`/`LabelMapInvariantError` in `masks.py` wrapping the existing `check_coverage` for edit-time enforcement — two of Phase 1's three foundation primitives, both built with no live consumer yet.**

## Performance

- **Duration:** ~30 min
- **Tasks:** 3
- **Files modified:** 7 (3 created, 4 modified)

## Accomplishments

- `src/comiccolor/model/masks.py` gained `LabelMapInvariantError` and `assert_invariant(label_map, line_mask, protected=None)`, additive-only, delegating to `check_coverage` and raising on either uncovered pixels or leaked pixels (a label sitting on a line/protected pixel, which `check_coverage` alone reports as `exhaustive: True`). Exported from `comiccolor.model`, alphabetised in `__all__`.
- `src/comiccolor/pipeline/` created: `Stage` frozen dataclass (`name`, `display_name`, `upstream`, `produces`, `runner`), `STAGES` — all eight `PipelineStage` values in chain order with display names from 01-UI-SPEC.md §1, `upstream` links (`IMPORT.upstream is None`, every other stage names its predecessor), and exactly one non-`None` runner (`run_import` on `IMPORT`). `stage_for`/`next_stage` read the registry; no dynamic dispatch anywhere.
- `run_import(store, page)` persists `page.stage = PipelineStage.PANELS` via `Store.set_page_stage`. `run_stage(store, page, name)` is the thin D-10 dispatcher: looks the stage up, raises `StageNotImplementedError` if undeclared, calls the runner, and stops — it never walks the chain or advances a page past its own gate.
- `tests/test_pipeline.py`'s five Wave 0 stubs (from plan 01-01) filled in and unskipped; two more tests added (`test_run_stage_refuses_a_stage_with_no_runner`, `test_the_registry_never_advances_a_page_on_its_own`) pinning D-11 and D-10 as executable assertions. `tests/test_masks.py` gained five new tests for the invariant wrapper.
- Full suite: `pytest -q` — 62 passed, 24 skipped, 2 xfailed. `tests/test_pipeline.py` and `tests/test_masks.py` both green with zero skips remaining in the former.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the label-map invariant assertion over the existing coverage check** - `65aff51` (feat)
2. **Task 2: Declare the eight-stage pipeline registry** - `86a39d4` (feat) — includes `runner.py`'s full implementation; see Deviations
3. **Task 3: Implement the import runner and fill the pipeline test module** - `d20880a` (test)

**Plan metadata:** pending (this commit, docs: complete plan)

## Files Created/Modified

- `src/comiccolor/model/masks.py` - added `LabelMapInvariantError`, `assert_invariant`; `check_coverage` and every other existing function untouched
- `src/comiccolor/model/__init__.py` - exported the two new names, alphabetised in `__all__`
- `tests/test_masks.py` - five new tests: pass, uncovered-pixel raise (message carries the count), protected-pixel pass, leak-onto-line raise, exclusivity-is-structural extension
- `src/comiccolor/pipeline/__init__.py` - re-exports `Stage`, `STAGES`, `StageRunner`, `stage_for`, `next_stage`, `run_import`, `run_stage`, `StageNotImplementedError`
- `src/comiccolor/pipeline/stages.py` - `Stage` dataclass, `STAGES` (8 entries), `stage_for`, `next_stage`; module docstring cites D-06/D-07/D-08/D-10/D-11
- `src/comiccolor/pipeline/runner.py` - `run_import`, `run_stage`, `StageNotImplementedError`
- `tests/test_pipeline.py` - all five Wave 0 stubs filled in and unskipped; two new tests added

## Decisions Made

- `runner.py`'s complete implementation shipped in the Task 2 commit rather than Task 3's, driven by the module-dependency direction the plan itself specifies (`stages.py` imports `run_import` from `runner.py` at module level). Task 2's own acceptance criteria (`python -c "from comiccolor.pipeline import STAGES..."`) cannot pass without `runner.py` existing first, so both files were necessarily committed together. Task 3's commit is the test file only, since the runner code it exercises was already correct and covered.
- `assert_invariant` treats a leak (label on a line/protected pixel) as a second, independent failure mode from a gap (uncovered fillable pixel) — raising on either, with a distinct message — rather than trying to fold both into a single condition, because `check_coverage`'s own `exhaustive` flag does not flip for a leak-only map.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed a literal "PanelStageRun" mention from stages.py's own docstring**
- **Found during:** Task 2 acceptance-criteria verification
- **Issue:** The module docstring's "explicitly not built" paragraph named `PanelStageRun` (the table RESEARCH.md/ARCHITECTURE.md proposed and this phase deliberately excludes) to explain why it's absent. The plan's own acceptance criterion (`grep -c "PanelStageRun\|panel_stage_run" src/comiccolor/pipeline/stages.py` must return `0`) does not distinguish "names it while explaining its absence" from "implements it" — any literal occurrence trips the check.
- **Fix:** Reworded the docstring to describe the excluded design ("a per-panel run-tracking table") without using the literal identifier, preserving the same explanation.
- **Files modified:** `src/comiccolor/pipeline/stages.py`
- **Verification:** `grep -c "PanelStageRun\|panel_stage_run" src/comiccolor/pipeline/stages.py` → `0`; `grep -rn "PanelStageRun" src/` → no matches (after clearing a stale `.pyc` in `__pycache__`, which is gitignored and irrelevant to source)
- **Committed in:** `86a39d4` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — acceptance-criteria conflict resolved by rewording, no behavior change)
**Impact on plan:** No scope creep. The docstring still explains the same design decision; only the literal string used to name the excluded table changed.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `Stage`/`STAGES`/`stage_for`/`next_stage` are ready for plan 01-07's `GET /api/pipeline/stages` endpoint and plan 01-11's stage strip to serialise directly — `display_name`, `upstream`, and `runner is not None` are exactly the fields those consumers need.
- `assert_invariant`/`LabelMapInvariantError` are exported from `comiccolor.model` and ready for Phase 3's zone editor to call after every merge/split/gap-absorb/undo transition; no live consumer exists yet in this phase, as intended.
- Seven of the eight declared stages still have `runner=None` — later phases fill them in against the `Stage`/`StageRunner` contract declared here without needing to touch `stages.py`'s structure.
- No blockers for any other Wave 2 plan; this plan's files (`pipeline/`, `masks.py` additions) have no overlap with sibling wave-2 plans' `files_modified` lists.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*
