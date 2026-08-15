---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 12
subsystem: frontend
tags: [vite, typescript, vitest, stage-strip, upload, page-grid]

# Dependency graph
requires:
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Page/volume/pipeline routes and DTOs (plan 01-08)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "App shell, hash router, typed API client, stub views, toolbar (plan 01-11)"
provides:
  - "frontend/src/components/stageStrip.ts — segmentStates (pure) + renderStageStrip (compact/full), reused unchanged by Phase 2+"
  - "frontend/src/components/uploadDrop.ts — partitionUploadResult (pure), renderUploadDrop, uploadWithProgress (XHR-based real progress)"
  - "frontend/src/views/pageGrid.ts, pageDetail.ts — real implementations replacing plan 01-11's stubs"
  - "frontend/src/shell/toolbar.ts — getToolbarHandle(), a singleton accessor for the stage-strip slot"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "segmentStates() ignores has_runner entirely by design (UI-SPEC §1) — the two not-yet-reached situations must render identically, and this is the one place that product decision lives"
    - "Upload uses XMLHttpRequest, not fetch, specifically for xhr.upload.onprogress (fetch has no equivalent upload-progress event) — 201 and 400 responses are both normalised into the same PageUploadDto shape before partitionUploadResult decides success/failure per file"
    - "renderUploadDrop/renderStageStrip return a handle/void rather than a teardown — they are components mounted inside a view's own teardown scope, not views themselves"

key-files:
  created:
    - frontend/src/components/stageStrip.ts
    - frontend/src/components/uploadDrop.ts
    - frontend/src/styles/pages.css
    - frontend/tests/stageStrip.test.ts
    - frontend/tests/uploadDrop.test.ts
  modified:
    - frontend/src/views/pageGrid.ts
    - frontend/src/views/pageDetail.ts
    - frontend/src/shell/toolbar.ts

key-decisions:
  - "toolbar.ts gained getToolbarHandle(), a module-level singleton accessor, because main.ts (plan 01-11) discards renderToolbar()'s return value and never threads it to the router or views. Without this, pageDetail.ts had no way to reach the toolbar's stage-strip slot at all — a Rule 3 blocking fix, not a signature change to renderToolbar() itself."
  - "uploadWithProgress() normalises both the 201 (partial/full success) and 400 (all-rejected) response bodies into one PageUploadDto shape before handing off to partitionUploadResult — the HTTP status decides nothing about which files succeeded; only the per-file rejected/accepted lists in the body do, matching plan 01-08's documented 201-vs-400 contract."
  - "renderUploadDrop's drop zone is always present (not swapped out once a volume has pages) — only its inner prompt content toggles between the empty-state copy and the 'Upload Pages' CTA via setHasPages(), so drag-and-drop keeps working identically before and after the volume's first page."

requirements-completed: [PROJ-02, PROJ-04]

# Metrics
duration: ~55min
completed: 2026-08-15
---

# Phase 01 Plan 12: Page Grid, Upload Drop, Stage Strip and Page Detail Summary

**The eight-segment pipeline stage strip driven entirely by `GET /api/pipeline/stages` (never a hardcoded list, both not-yet-reached situations rendering identically per UI-SPEC §1), the artwork-led page grid with real drag-and-drop upload progress via `XMLHttpRequest`, and the page detail screen's full strip in the toolbar over an unpadded, canvas-ready content region — 47/47 Vitest tests, clean typecheck, clean build.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 3
- **Files modified:** 8 (5 created, 3 modified)

## Accomplishments

- `stageStrip.ts`'s `segmentStates()` is a pure function deriving `complete`/`current`/`not-reached` from a `StageDto[]` and the page's current stage name, in declaration order, with no hardcoded stage names anywhere. `has_runner` is never consulted — the docstring explains why without using the literal field name, so the grep that pins this stays green. `renderStageStrip()` builds non-interactive DOM in both `compact` (4px, page grid) and `full` (24px + labels, page detail toolbar) variants, `role="list"`/`role="listitem"` with a per-segment accessible name so state isn't colour-only.
- `uploadDrop.ts`'s `partitionUploadResult()` is pure and splits a `PageUploadDto` into `added`/`failures`/`summary`, writing the Copywriting Contract's error-shape sentence only when there are failures. `renderUploadDrop()` renders the verbatim empty-state heading/body or the "Upload Pages" CTA depending on `hasPages`, supports both click-to-browse and real drag-and-drop, and exposes a handle for progress/failure-banner control. `uploadWithProgress()` uses `XMLHttpRequest` (not `fetch`) specifically for `xhr.upload.onprogress`, normalising both the 201 and 400 response shapes into one `PageUploadDto` before handoff.
- `pageGrid.ts` replaces the plan 01-11 stub: fetches `api.pipeline.stages()` and `api.pages.list()` once on mount, renders an artwork-anchored card grid (`<img loading="lazy">` at full card scale, compact strip beneath, name below), appends accepted uploads immediately while a bad file in the same batch shows a persistent failure banner without discarding the good ones (T-01-PARTIAL), and never renders a Save control.
- `pageDetail.ts` replaces the plan 01-11 stub: mounts the full stage strip and a "Back to pages" control into the toolbar's slot, shows the page image at fit-to-width scale in an unpadded `.page-detail-content` region (no padding/max-width/margin:auto, verified by grep), and documents the deliberate D-08/UI-SPEC §3 omission of Go-Back and Confirm & Continue in its module docstring.
- `toolbar.ts` gained `getToolbarHandle()` — a minimal module-level singleton so `pageDetail.ts` can reach the slot `renderToolbar()` already builds, without changing `renderToolbar()`'s own signature or `main.ts`.
- Full verification: `npm --prefix frontend run typecheck` exits 0, `npm --prefix frontend run test -- --run` exits 0 with 47/47 tests across 6 suites (11 transform + 9 client + 12 router + 6 projectPicker + 5 stageStrip + 4 uploadDrop), and `npm --prefix frontend run build` succeeds.

## Task Commits

Each task was committed atomically:

1. **Task 1: The eight-segment stage strip, with a pure state model** - `276123b` (feat)
2. **Task 2: The page grid with drag-and-drop upload** - `1c3374b` (feat)
3. **Task 3: The page detail screen and its full stage strip** - `99d7e3f` (feat)

## Files Created/Modified

- `frontend/src/components/stageStrip.ts` - `SegmentState`, `SegmentModel`, `segmentStates`, `renderStageStrip`
- `frontend/src/components/uploadDrop.ts` - `UploadOutcome`, `partitionUploadResult`, `renderUploadDrop`, `uploadWithProgress`
- `frontend/src/styles/pages.css` - stage strip, page grid, upload drop and page detail rules, all token-only
- `frontend/tests/stageStrip.test.ts` - 5 tests over `segmentStates`
- `frontend/tests/uploadDrop.test.ts` - 4 tests over `partitionUploadResult`
- `frontend/src/views/pageGrid.ts` (replaced stub) - `renderPageGrid`
- `frontend/src/views/pageDetail.ts` (replaced stub) - `renderPageDetail`
- `frontend/src/shell/toolbar.ts` (modified) - added `getToolbarHandle()`

## Signatures (for Phase 2's editor and any later plan touching these files)

```ts
// frontend/src/components/stageStrip.ts
export type SegmentState = "complete" | "current" | "not-reached";
export interface SegmentModel { name: string; displayName: string; state: SegmentState; tooltip: string; }
export function segmentStates(stages: StageDto[], currentStage: string): SegmentModel[];
export function renderStageStrip(mount: HTMLElement, model: SegmentModel[], variant: "compact" | "full"): void;
```

```ts
// frontend/src/components/uploadDrop.ts
export interface UploadOutcome { added: PageDto[]; failures: {filename: string; detail: string}[]; summary: string; }
export function partitionUploadResult(result: PageUploadDto): UploadOutcome;
export function renderUploadDrop(mount: HTMLElement, options: {hasPages: boolean; onFiles: (files: File[]) => void | Promise<void>}): UploadDropHandle;
export function uploadWithProgress(url: string, files: File[], onProgress: (percent: number) => void): Promise<PageUploadDto>;
```

```ts
// frontend/src/shell/toolbar.ts (addition)
export function getToolbarHandle(): ToolbarHandle; // throws if renderToolbar() hasn't run yet
```

## Decisions Made

- See `key-decisions` in frontmatter: the `getToolbarHandle()` singleton, the unified 201/400 response normalisation in `uploadWithProgress`, and the always-present drop zone with a toggling inner prompt.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `pageDetail.ts` had no way to reach the toolbar's slot**
- **Found during:** Task 3, before writing `pageDetail.ts`'s body
- **Issue:** `main.ts` (plan 01-11) calls `renderToolbar(app)` and discards its return value; the `Route`/router contract gives views a `mount` element but no toolbar handle. Task 3's own action explicitly requires mounting the full stage strip "into the toolbar's slot", which was otherwise unreachable from `pageDetail.ts`.
- **Fix:** Added a minimal module-level singleton to `toolbar.ts` — `renderToolbar()` now also stores its returned handle in a module variable, and a new `getToolbarHandle()` export reads it back. `renderToolbar()`'s own signature and behaviour are unchanged; `main.ts` was not touched.
- **Files modified:** `frontend/src/shell/toolbar.ts`
- **Verification:** `npm --prefix frontend run typecheck && npm --prefix frontend run test -- --run && npm --prefix frontend run build` all passed after the fix, including the pre-existing `router.test.ts`/`projectPicker.test.ts` suites which don't touch the toolbar at all.
- **Impact:** No scope creep — additive-only change to an existing module already in this plan's dependency chain; no other plan's files were touched.

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking, additive singleton accessor)
**Impact on plan:** None on shipped behaviour beyond making Task 3 possible; `renderToolbar()`'s contract recorded in 01-11-SUMMARY.md is unchanged.

## Issues Encountered

- `frontend/node_modules` was absent in this fresh worktree (expected per the environment note) — ran `npm --prefix frontend install` once before Task 1's verification, which resolved cleanly against the committed `package-lock.json`. Baseline after install matched the stated 38/38 tests across 4 suites exactly.

## User Setup Required

None — no external service configuration required.

## Known Stubs

None. Both `pageGrid.ts` and `pageDetail.ts` are full implementations; no hardcoded empty values, placeholder text, or unwired data sources remain.

## Next Phase Readiness

- `stageStrip.ts`'s `segmentStates`/`renderStageStrip` are stable and reusable unchanged by Phase 2+ for the `current`→`complete` transitions the confirmation gate (UI-SPEC §2) will drive — no redesign needed, only new call sites.
- `getToolbarHandle()` is now the established way for any future view to reach the toolbar slot; Phase 2/3's canvas editor toolbar controls should use the same accessor rather than inventing a second one.
- The Go-Back contract (D-08, UI-SPEC §3) and the `upstream` links needed to compute its cost sentence are unimplemented by design, per the module docstring in `pageDetail.ts` — Phase 2 is the owner.
- No blockers for any later plan in this phase.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*
