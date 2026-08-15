---
phase: 01-foundation-project-palette-pipeline-backbone
verified: 2026-08-15T22:46:38Z
status: human_needed
score: 9/9 must-haves verified (roadmap success criteria); 9/9 requirement IDs SATISFIED
overrides_applied: 0
human_verification:
  - test: "Create a named project via the picker, add a volume and pages, close the app (POST /close or quit the server), reopen it and navigate back in."
    expected: "The same project opens with its volumes, pages, thumbnails and palette all present; nothing looks reset or partially loaded."
    why_human: "Route-level tests (`test_reopen_after_close_keeps_pages_and_palette`) prove the DB/WAL mechanics survive a close, but no test renders the actual screens in a browser — visual/UX confirmation of 'nothing lost' has never been observed."
  - test: "Drag-and-drop a batch of line art pages onto a volume, including one corrupt/non-image file, then add more pages to the same volume in a later session."
    expected: "Good pages appear with thumbnails and a stage indicator at 'Panels'; the bad file is reported inline without losing the others; later uploads append rather than replace."
    why_human: "Backend batch/partial-failure logic is unit-tested (`test_a_bad_file_does_not_lose_the_good_ones`), but the drag-and-drop UI, progress bar and failure banner (`uploadDrop.ts`) have zero DOM tests (WR-14, deferred) — never observed rendering in a real browser."
  - test: "Upload a swatch image with a few flat colour chips; separately upload a character sheet, then accept some proposals and reject/discard others individually, naming the character."
    expected: "Swatch upload creates named 'Colour N' entries matching the chip colours; sheet proposals render as dashed cards the artist can accept one-by-one into '{character} / {part}' entries, and the sheet stays actionable after a partial accept (CR-04 fix)."
    why_human: "Extraction accuracy and the accept/reject route contract are unit-tested, but the proposal-card grid, accept form and swatch grid have no render tests — visual correctness and click-through flow are unverified."
  - test: "Rename, recolour and delete a palette entry by hand; then recolour an entry that came from a swatch or sheet and watch for a toast, not a confirmation dialog."
    expected: "Recolour applies immediately with a 'Updated on N pages.' toast and no confirmation step (D-09); rename and delete work with no stage-chain interaction."
    why_human: "`swatchCard.ts` has a known stale-snapshot bug on rename (WR-13, deferred) that only shows up interactively; toast/dialog behaviour has no DOM test coverage."
  - test: "Open a page from the grid and confirm the stage strip shows 'Import'/'Panels' complete and every later stage visually neutral, identically, regardless of whether a runner exists."
    expected: "The strip renders 8 segments with the current position highlighted and all not-yet-reached segments looking the same (01-UI-SPEC.md contract)."
    why_human: "`segmentStates` (the pure state model) is unit-tested; `renderStageStrip`'s actual DOM/CSS output has never been visually confirmed."
---

# Phase 1: Foundation — Project, Palette & Pipeline Backbone Verification Report

**Phase Goal:** An artist can create a persistent project, add pages and reference images to it over time, and build a palette by hand, from a swatch, or from a proposed character-sheet extraction — with every edit surviving a refresh or crash. Underneath, the pipeline stage registry, the shared screen↔label-map coordinate transform, and the label-map exclusivity/exhaustiveness invariant check are built and unit-tested as the foundation every later editor and stage depends on.

**Verified:** 2026-08-15T22:46:38Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Artist creates a named project, closes the app, reopens it later, finds pages/palette/edits intact | ✓ VERIFIED | `project` table `CHECK (id=1)` enforces one project per DB (`store.py:39-43`); `POST /api/projects`, `POST /open`, `POST /close` (checkpoint) in `routers/project.py`; `tests/test_web/test_project_routes.py::test_reopen_after_close_keeps_pages_and_palette` and `::test_close_checkpoints_the_wal` pass |
| 2 | Artist uploads line art pages and character-sheet reference images, adds more pages later without loss, sees each page's stage, opens any page | ✓ VERIFIED | `routers/page.py::upload_pages` validates `volume_id` before writing (CR-03 fixed), auto-advances via `run_import`; `routers/reference.py` handles sheet upload/pending storage; `GET /pipeline/stages` + `stageStrip.ts`/`pageDetail.ts`/`pageGrid.ts` render per-page stage; `test_adding_pages_later_preserves_existing_pages`, `test_stage_field_is_panels_after_upload` pass |
| 3 | Swatch → named entries from colour chips; sheet → individually accept/reject proposals; hand create/rename/recolour/delete | ✓ VERIFIED | `colour/extract.py` (Pillow quantize + CIELAB merge, D-12/D-13/D-14); `routers/palette.py` (swatch, CRUD); `routers/reference.py` (sheet propose/accept/reject, partial-accept fixed per CR-04); `test_swatch_upload_creates_colour_n_entries`, `test_hand_crud_round_trip`, `test_partial_accept_leaves_the_rest_acceptable` pass |
| 4 | Recolour a palette entry once; every referencing page updates immediately, no stage re-run | ✓ VERIFIED | `store.update_palette_rgb()` + `panels_affected_by()` (pre-existing, D-09); `palette.py` route returns `pages_affected`; frontend shows a toast only, no confirmation (`palette.ts:160-176`); `test_recolour_reports_affected_pages_and_leaves_stage_alone` passes |
| 5 | Every edit persists the instant it's made; refresh/crash loses no work | ✓ VERIFIED | Every `Store` mutation commits synchronously (module docstring + code); WAL + `busy_timeout` + `checkpoint()` on close; per-request `Store` via `get_store` (CR-01 thread-affinity bug fixed); no client-side "Save" button anywhere (`pageGrid.ts` docstring: "a drop is the commit") |

**Score:** 5/5 roadmap success criteria verified. All backed by passing automated tests, not narrative claims.

### Foundation Primitives (phase-specific, non-roadmap-numbered but load-bearing)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 6 | Declarative pipeline stage registry exists, thin runner, only `import` wired | ✓ VERIFIED | `pipeline/stages.py` (`STAGES`, 8 entries, `runner=None` for 7 of 8), `pipeline/runner.py` (`run_import`, `run_stage` refuses unimplemented stages); `tests/test_pipeline.py` (7 tests) including `test_the_registry_never_advances_a_page_on_its_own` |
| 7 | Shared screen↔label-map coordinate transform, unit-tested at extreme zoom | ✓ VERIFIED | `frontend/src/geometry/transform.ts` — pure TS, `Math.floor` binning documented to match NumPy; `frontend/tests/transform.test.ts` covers identity, floor-boundary, devicePixelRatio, panelOffset, and explicit extreme zoom-in (64x) / zoom-out (0.05x) round-trips per Pitfall 7 |
| 8 | Label-map exclusivity/exhaustiveness invariant check, unit-tested | ✓ VERIFIED | `model/masks.py::assert_invariant` + `LabelMapInvariantError`, wraps `check_coverage`; `tests/test_masks.py` has 4 dedicated `test_assert_invariant_*` tests plus structural-exclusivity tests |
| 9 | Test gate green (144 Python + 61 frontend) | ✓ VERIFIED | Ran directly this session: `144 passed, 2 xfailed` (pytest), `61 passed` (vitest) — reproduced independently, not taken from SUMMARY |

**Combined score: 9/9 must-haves verified.**

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/comiccolor/model/entities.py` | `Project`, `PipelineStage` enum, project-scoped `PaletteEntry`/`Entity` | ✓ VERIFIED | `PipelineStage(str, Enum)` with 8 values; `Project` dataclass with `palette_revision` |
| `src/comiccolor/model/store.py` | Schema migration, WAL, checkpoint, `update_palette_rgb`/`panels_affected_by` | ✓ VERIFIED | `CHECK (id=1)` on project; WAL PRAGMA; `checkpoint()`; both palette-propagation methods present |
| `src/comiccolor/model/masks.py` | `assert_invariant` wrapper | ✓ VERIFIED | Present, tested, extends `check_coverage` |
| `src/comiccolor/pipeline/{stages,runner}.py` | Declarative registry + thin runner | ✓ VERIFIED | Matches Pattern 5 exactly |
| `src/comiccolor/colour/extract.py` | Quantize+CIELAB-merge extractor, sheet pre-pass | ✓ VERIFIED | `extract_palette(image, sheet_mode=...)`; covered by `tests/test_extract.py` |
| `src/comiccolor/web/routers/{project,volume,page,reference,palette,pipeline}.py` | Full CRUD/upload surface | ✓ VERIFIED | All present, all critical/most-warning review findings fixed in subsequent commits |
| `frontend/src/geometry/transform.ts` | Pure coordinate transform | ✓ VERIFIED | No DOM, exported `Viewport`/functions, tested |
| `frontend/src/views/{projectPicker,pageGrid,pageDetail,palette}.ts` | Four screens per UI-SPEC | ✓ VERIFIED | All wired into `shell/router.ts`; call real API endpoints, not stubs |
| `frontend/src/components/stageStrip.ts` | Stage strip pure model + renderer | ✓ VERIFIED | `segmentStates` pure/tested; `renderStageStrip` builds real DOM from it |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `pageGrid.ts`/`pageDetail.ts` | `GET /api/pipeline/stages` + `GET /api/pages` | `api.pipeline.stages()`, `api.pages.*` | WIRED | Both awaited, response passed into `segmentStates`/render |
| `palette.ts` recolour | `PATCH /api/palette/{id}` → `store.update_palette_rgb` → `panels_affected_by` | `api.palette.update` | WIRED | Response's `pages_affected` drives the toast copy; verified by route test |
| `reference.ts` accept | `POST /sheets/{id}/accept` → `Entity`/`PaletteEntry` rows, non-consuming | `api.references.accept` | WIRED | Partial-accept regression test passes; frontend removes only accepted indices, matching server contract (CR-04 closed) |
| `page.py` upload | `volume.py::get_owned_volume` | Direct call before loop | WIRED | CR-03 fix confirmed present; orphan-file test passes |
| `deps.py::get_store` | `Store.__init__` (`check_same_thread=False`) | Per-request dependency | WIRED | CR-01 fix confirmed present in `store.py:179`-equivalent line |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `pageGrid.ts` thumbnails | `pages` (from `api.pages.list`) | `GET /api/pages/?volume_id=` → `store.pages_for_volume` (real SQLite query) | Yes | ✓ FLOWING |
| `palette.ts` swatch grid | `entries` (from `api.palette.list`) | `GET /api/palette` → real DB rows | Yes | ✓ FLOWING |
| `stageStrip` segments | `stages` (from `api.pipeline.stages`) | `GET /api/pipeline/stages` → `pipeline.STAGES` (static but truthful registry, not a stub) | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Python test suite | `PYTHONPATH=src python -m pytest tests/ -q` | `144 passed, 2 xfailed` | ✓ PASS |
| Frontend test suite | `npm test -- --run` (vitest) | `61 passed` (8 files) | ✓ PASS |
| No debt markers in phase files | grep `TODO\|FIXME\|XXX\|HACK\|PLACEHOLDER` across `web/`, `pipeline/`, `colour/`, `frontend/src/` | Zero hits (only benign HTML `placeholder=` input attributes) | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this project and no plan/summary declares probe-based verification for Phase 1. SKIPPED — not applicable to this phase's tooling.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|--------------|--------|----------|
| PROJ-01 | 01-06, 01-07, 01-11 | Create/reopen a named project with pages/palette/edits intact | ✓ SATISFIED | `routers/project.py`, `test_reopen_after_close_keeps_pages_and_palette` |
| PROJ-02 | 01-08, 01-12 | Upload pages, add more over time | ✓ SATISFIED | `routers/page.py::upload_pages`, `test_adding_pages_later_preserves_existing_pages` — **note:** REQUIREMENTS.md's top checklist still shows this unchecked/"Pending"; code evidence contradicts that tracking artifact (see Anti-Patterns) |
| PROJ-03 | 01-08, 01-10 | Upload character-sheet reference images | ✓ SATISFIED | `routers/reference.py`, D-05 accept-time binding implemented; same REQUIREMENTS.md staleness note applies |
| PROJ-04 | 01-04, 01-08, 01-12 | See each page's stage, open any page | ✓ SATISFIED | `GET /api/pipeline/stages`, `stageStrip.ts`, `GET /api/pages/{id}`; same staleness note applies |
| PROJ-05 | 01-03, 01-06, 01-07 | Edits persist instantly, no lost work | ✓ SATISFIED | Synchronous commits, WAL+checkpoint, per-request Store (CR-01 fixed) |
| PAL-01 | 01-05, 01-09, 01-13 | Swatch → named entries | ✓ SATISFIED | `colour/extract.py`, `routers/palette.py`, `test_swatch_upload_creates_colour_n_entries` |
| PAL-02 | 01-05, 01-08, 01-10, 01-13 | Sheet → individually accept/reject proposals | ✓ SATISFIED | `routers/reference.py`, CR-04/WR-05/WR-06/WR-18 fixes confirmed present |
| PAL-03 | 01-09, 01-13 | Hand create/rename/recolour/delete | ✓ SATISFIED | `routers/palette.py` CRUD, `test_hand_crud_round_trip` |
| PAL-04 | 01-09, 01-13 | Recolour propagates without stage re-run | ✓ SATISFIED | `update_palette_rgb`/`panels_affected_by`, toast-only UI, `test_recolour_reports_affected_pages_and_leaves_stage_alone` |

**All 9 phase requirement IDs are SATISFIED by direct codebase evidence** (route implementations + passing tests), independent of REQUIREMENTS.md's own checklist state.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `.planning/REQUIREMENTS.md` | 14-16, 128-130 | Top-of-file checklist (`- [ ]`) and Traceability table mark PROJ-02/PROJ-03/PROJ-04 as unchecked/"Pending" while PROJ-01/05 and all PAL-0x are checked/"Complete" for the same phase | ⚠️ WARNING | Documentation-sync gap only — codebase evidence (routes, docstrings referencing the req IDs, and passing route tests) shows all three are implemented. Recommend updating REQUIREMENTS.md's checkboxes/traceability table to `[x]`/"Complete" so future phase tooling doesn't read this as a real gap. Not a code defect. |
| `frontend/src/shell/sidebar.ts` | 153-169 | `refresh()` has no try/catch; a 409 (no project open) is an unhandled promise rejection, leaving the sidebar permanently blank until the app-level project state changes | ℹ️ INFO (already reviewed, deferred as WR-10/WR-12) | Does not block the core create/reopen flow — `projectPicker.ts`'s own `boot()` independently catches the same 409 and renders the picker correctly in the content area. Cosmetic only; explicitly deferred in 01-REVIEW.md, not re-raised as a blocker here per phase instructions. |
| `frontend/src/components/swatchCard.ts` | 84-93 | Stale closure-captured `entry` on rename (WR-13, deferred) | ℹ️ INFO (already reviewed, deferred) | Noted, not re-raised as a blocker. |
| `frontend/vitest.config.ts` | 4-6 | `environment: "node"` — zero DOM-level render tests exist for any view/component (WR-14, deferred) | ℹ️ INFO (already reviewed, deferred) | Drives the human-verification items below: the actual rendered screens have never been exercised by an automated check, only by pure-function unit tests. |

### Human Verification Required

See frontmatter `human_verification`. Five items, one per roadmap success criterion, all rooted in the same underlying gap: comprehensive backend/route test coverage exists, but zero of the four screens (project picker, page grid, page detail, palette) have ever been rendered and interacted with by an automated check (`environment: "node"`, WR-14, deliberately deferred) or by this verifier (no browser available). The backend mechanics behind every success criterion are proven; the on-screen experience is not yet independently confirmed.

### Gaps Summary

No BLOCKER-level gaps. All 5 roadmap success criteria and all 3 foundation primitives are backed by passing, independently-reproduced automated tests and direct code inspection — not SUMMARY narrative. All 4 Critical and 15 of 20 Warning code-review findings are confirmed fixed in the current codebase (verified by reading the actual files, not by trusting the commit messages). WR-10 through WR-14 remain as intentionally deferred, low-severity frontend robustness gaps per 01-REVIEW.md and are not re-raised as blockers here.

The phase is functionally complete. Status is `human_needed` rather than `passed` solely because the phase ships four new interactive screens with no automated DOM-level verification (WR-14) and this verifier has no way to render a browser — the roadmap's success criteria are user-facing flows ("artist creates...", "artist uploads...", "artist changes...and sees"), and those specific words have only been proven at the API/data layer, not visually. A quick supervised pass through the five flows listed in `human_verification` would close this out to `passed`.

Separately, recommend updating `.planning/REQUIREMENTS.md`'s checklist and traceability table for PROJ-02/PROJ-03/PROJ-04 to reflect completion — this is a paperwork fix, not a code change.

---

*Verified: 2026-08-15T22:46:38Z*
*Verifier: Claude (gsd-verifier)*
