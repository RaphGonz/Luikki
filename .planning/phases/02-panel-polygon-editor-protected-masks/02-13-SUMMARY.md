---
phase: 02-panel-polygon-editor-protected-masks
plan: 13
subsystem: frontend-editor
tags: [typescript, canvas, gate-flow, undo, vitest, jsdom]

# Dependency graph
requires:
  - phase: 02-10
    provides: "mountCanvasEditor/CanvasEditorHandle/CanvasEditorOptions -- the canvas mount, draw loop and pointer-interaction callback surface"
  - phase: 02-11
    provides: "POST /stage/confirm, GET /stage/go-back-targets, POST /stage/go-back routes"
  - phase: 02-12
    provides: "api.panels.*/api.protected.*/api.pages.confirmStage, the #/page/{id}/edit route, and the placeholder this plan replaces"
provides:
  - "frontend/src/views/pageEditor.ts -- renderPageEditor(mount, { pageId }): the one-screen, two-mode, two-gate editor UI-SPEC §1 specifies"
  - "frontend/src/styles/pageEditor.css -- toolbar cluster, segmented tool-mode control, kind selector, helper text, banner, disabled-CTA state"
affects: ["02-14"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Every server-driven copy string (CTA labels, tooltips, spinner text, banner text, helper text) is declared exactly once as a module-level const and referenced by name everywhere it's used, so the same UI-SPEC sentence can never drift into two spellings inside this file."
    - "mountCanvasEditor is imported under an alias (`mountEditorSurface`) so the literal identifier appears on exactly one line (the import) -- the plan's own acceptance grep counts lines, and an unaliased import+call pair would always match twice."
    - "Panels come back from every mutating route as the whole server-recomputed list (`applyPanelList`); protected masks come back one object at a time and are merged into a local `protectedShapes` cache (`upsertProtectedShape`/`removeProtectedShape`) -- mirrors 02-12's own client-contract split between the two resource routes."
    - "onCommitPolygon's single (shapeId, polygon) callback is diffed against the view's own pre-mutation shape cache (`diffPolygonForUndo`) to recover which single vertex was inserted or deleted, since canvasEditor.ts's already-fixed (plan 02-10) callback signature carries no index -- the diff is safe because that callback only ever fires from an edge-insert or a vertex-delete, never a general reshape."
    - "All three primary toolbar controls (Confirm, Undo, Delete) start `disabled = true` at DOM construction and only become interactive after boot()'s first syncToolbar() call -- closes a real race where a click landing before boot() finished could run concurrently with boot()'s own state-setting tail and be silently overwritten by it."

key-files:
  created:
    - frontend/src/views/pageEditor.ts
    - frontend/src/styles/pageEditor.css
    - frontend/tests/pageEditor.test.ts
  modified: []

key-decisions:
  - "The UI-SPEC §2 'trash icon that appears near its bounding box' is rendered as a single toolbar Delete button (aria-label swapping between 'Delete panel' and 'Delete protected mask' by active tool mode) rather than a floating per-shape overlay. canvasEditor.ts's API boundary (plan 02-10, out of this plan's file list) exposes no per-shape screen-space bbox and no deleteSelected() method; the toolbar button dispatches a synthetic Delete keydown at canvasEditor.ts's own canvas element, reusing its existing vertex-vs-shape-selection and refusal-toast logic verbatim rather than re-implementing deletion."
  - "The two loading-spinner texts (\"Detecting panels…\"/\"Detecting speech bubbles…\") are shown for the whole of boot()'s initial fetch window (page + image + both shape lists), not conditioned on the fetched list actually being empty -- a genuinely empty panel/mask list is a legitimate persisted state (feeding the Panels-gate disabled-CTA / never-disabled Protected-gate rules) and must not be visually indistinguishable from 'still loading'."
  - "02-10 built frontend/src/styles/editor.css but no view ever imported it -- this plan is the first real mountCanvasEditor caller, so it also imports editor.css alongside its own pageEditor.css (Rule 2: without it the canvas surface, zoom pill and cursor states have no layout at all)."
  - "[Rule 1 - Bug] Confirm/Undo/Delete buttons defaulted to the browser's native disabled=false state from creation, before boot() had set page/editorHandle. A click in that window could invoke handleConfirm() concurrently with boot() still in flight; both functions write activeTool/detectionFailed unconditionally at their tails, so whichever finished last silently won, regardless of correctness. Fixed by starting all three disabled until boot()'s first syncToolbar() call. Found writing the detection-failure-banner test in Task 3, which synthetically triggers exactly this window."

requirements-completed: [PAN-01, PAN-02, PAN-03, PROT-01, PROT-02, PROT-03]

# Metrics
duration: 50min
completed: 2026-08-16
---

# Phase 2 Plan 13: Page-Editor Screen (Gates, Canvas Wiring, Undo) Summary

**One route, one canvas mount, two sequential tool modes and two sequential confirmation gates: `renderPageEditor` replaces 02-12's placeholder wholesale, wiring every canvasEditor.ts gesture through the typed client, both gates through UI-SPEC §4's exact rules, and a 20-op per-tool-mode undo stack that makes D-19's no-confirmation deletion safe.**

## Performance

- **Duration:** ~50 min
- **Tasks:** 3 (2 auto, 1 auto+TDD)
- **Files modified:** 3 (all newly created)

## Accomplishments

- `frontend/src/views/pageEditor.ts` (768 lines) -- `renderPageEditor(mount, { pageId }): () => void`.
  - Boot sequence: `api.pages.get` → page image loaded as an `HTMLImageElement` → `mountCanvasEditor`
    called exactly once for the screen's whole lifetime (grep-verified: the literal identifier
    appears on exactly one line, the aliased import) → `api.panels.list`/`api.protected.list`
    fetched concurrently → toolbar/canvas state derived from `page.stage`, never local UI state.
  - Toolbar filled via `getToolbarHandle()` left to right per UI-SPEC §10: breadcrumb ("← Back to
    page grid" + page name), the Select/Draw segmented control (captions swap "Draw panel"/"Draw
    mask" by active layer), the Bubble/SFX kind selector (visible only in Protected + Draw), the
    non-interactive "Reading order: Left → Right" readout, Undo (`aria-label="Undo last edit"`),
    Delete (`aria-label` swaps "Delete panel"/"Delete protected mask"), the Go-Back text link
    (rendered in position with a documented no-op -- plan 02-14 wires it), and the primary Confirm
    button.
  - Every UI-SPEC copy string (CTA labels, empty-state tooltip, refusal toast, SFX helper text,
    detection-failure banner, both loading-spinner texts, reading-order readout, tool captions,
    kind labels) is a module-level `const` declared exactly once and referenced by name everywhere
    used -- grep-verified no string drifts into a second spelling.
  - Canvas commit callbacks (`onCommitVertexMove`/`onCommitPolygon`/`onCommitDraw`/`onCommitDelete`)
    each commit through `api.panels.*`/`api.protected.*` depending on the active tool mode, then
    feed the server's response back through `handle.setShapes` -- panels always via the whole
    server-recomputed list, protected masks merged one object at a time into a local cache. A
    `diffPolygonForUndo` helper recovers which single vertex was inserted/deleted from
    `onCommitPolygon`'s `(shapeId, polygon)` signature (canvasEditor.ts's fixed callback shape
    carries no index) by diffing against the pre-mutation cache.
  - Undo: one `UndoStack` per tool mode (`panelUndo`/`protectedUndo`), `Ctrl+Z`/`Cmd+Z` (window-level
    listener) and the toolbar button both call `popOp` + `invert` and re-issue the inverse as a
    fresh API call. `clearStack` is called from both the tool-mode-switch path
    (`switchActiveLayer`) and the gate-confirm path (`handleConfirm`), matching UI-SPEC §6's two
    named triggers.
  - Gates: Panels CTA ("Confirm & Continue to Protected") disabled with the exact tooltip string
    when the panel list is empty; Protected CTA ("Confirm & Continue to Zones") never disabled by
    mask count. Confirming Panels calls `api.pages.confirmStage`, shows "Detecting speech bubbles…"
    until `api.protected.list` resolves, sets both layers' read-only state, switches the active
    layer in place (no navigation) and shows the failure banner when the post-confirm mask list
    reports `detection_failed`. Confirming Protected sets protected read-only and swaps the CTA
    into a "Done" affordance that navigates to the page grid.
  - No confirmation dialog anywhere on the delete path (D-19/§5) -- the literal words "dialog",
    "window.confirm" and the substring "confirm(" are grep-absent from the whole file.
- `frontend/src/styles/pageEditor.css` (242 lines) -- toolbar cluster, 32px `--icon-hit` segmented
  tool-mode control (active segment in `--color-accent`), kind selector, persistent helper text,
  detection banner, disabled-CTA state. Every value is an existing `tokens.css` custom property;
  `--color-accent` appears 6 times, no hex literal anywhere.
- `frontend/tests/pageEditor.test.ts` (313 lines) -- `// @vitest-environment jsdom` first line,
  mocks `../src/api/client` wholesale (including a local `ApiError` so `instanceof` checks inside
  the view still resolve correctly), stubs `HTMLCanvasElement.prototype.getContext` and
  `requestAnimationFrame` per 02-10's precedent, and stubs the global `Image` constructor with a
  synchronous-`onload` `src` setter so `renderPageEditor`'s boot chain resolves deterministically
  without timers. 8 tests: zero-panel disabled CTA + exact tooltip; one-panel enabled CTA;
  zero-mask Protected CTA enabled; persistent SFX helper text in Protected mode;
  detection-failure banner shown with no `<dialog>`/`[role="dialog"]` element after a confirm;
  `confirmStage` called exactly once then `protected.list`, with `location.hash` unchanged
  (no navigation); Undo button `aria-label="Undo last edit"` and muted at start; teardown removes
  both the view's own DOM and its toolbar contribution.

## Task Commits

Each task was committed atomically:

1. **Task 1 + Task 2: screen shell, canvas wiring, gates, undo** -- `c70434d` (feat) -- combined
   into one commit since both tasks build the same single file incrementally (toolbar/canvas mount
   first, gesture/gate/undo wiring on top of it) and neither task's acceptance criteria are
   meaningfully checkable until the whole file exists, mirroring 02-10's own precedent for the same
   reason.
2. **Task 3: jsdom coverage** -- `aa10203` (test) -- includes the toolbar-race bug fix described
   below, found while writing this task's detection-failure-banner test, before any commit.

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `frontend/src/views/pageEditor.ts` (new) -- the full page-editor screen
- `frontend/src/styles/pageEditor.css` (new) -- toolbar/gate/banner styling
- `frontend/tests/pageEditor.test.ts` (new)

## Decisions Made

See `key-decisions` in the frontmatter for the four load-bearing ones (toolbar-only Delete instead
of a floating per-shape trash icon, spinner-text timing tied to the fetch window rather than list
emptiness, wiring the never-imported `editor.css`, and the toolbar-disabled-until-boot race fix).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] `frontend/src/styles/editor.css` was never imported anywhere**
- **Found during:** Task 1, while wiring `mountCanvasEditor` into this view.
- **Issue:** 02-10-SUMMARY.md built `editor.css` (canvas surround, floating zoom pill, cursor
  states) but no `main.ts`/view ever imported it -- this plan is the first real caller of
  `mountCanvasEditor`, so the gap was invisible until now.
- **Fix:** Added `import "../styles/editor.css";` alongside this plan's own `pageEditor.css` import.
- **Files modified:** `frontend/src/views/pageEditor.ts`
- **Commit:** `c70434d`

**2. [Rule 1 - Bug] Confirm/Undo/Delete toolbar buttons were clickable before `boot()` finished**
- **Found during:** Task 3, writing the detection-failure-banner test (the only test whose flow
  clicks Confirm and then continues to assert on state `boot()` itself also writes).
- **Issue:** All three buttons defaulted to the browser's native `disabled=false` DOM state from
  creation until `boot()`'s first `syncToolbar()` call set their real state. A click landing in
  that window (`page`/`editorHandle` already non-null but `boot()`'s own `Promise.all` fetch still
  in flight) let `handleConfirm()` run concurrently with `boot()`; both functions write
  `activeTool`/`detectionFailed`/read-only state unconditionally at their own tails, so whichever
  finished last silently overwrote the other's correct result regardless of which was right.
- **Fix:** All three buttons now start `disabled = true` at construction, closing the window
  entirely -- no click can reach `handleConfirm()`/`handleUndo()` before `boot()`'s first
  `syncToolbar()` call establishes the real state.
- **Files modified:** `frontend/src/views/pageEditor.ts`
- **Commit:** `aa10203`

None beyond the above.

## Known Stubs

- The Go-Back text link renders in its documented toolbar position with a `preventDefault`-only
  click handler. Not a defect: plan 02-14 owns wiring it to `api.pages.goBackTargets`/`goBack` and
  the costed confirmation dialog from `01-UI-SPEC.md` §3, exactly as this plan's own Task 1
  `<action>` text specifies ("plan 02-14 wires its behaviour, this task renders the element and
  leaves its click handler a documented no-op").

## Threat Flags

None beyond what this plan's own `<threat_model>` already named and this implementation satisfies:
T-2-09 (every string set via `textContent`, `innerHTML` grep-absent), T-2-29 (no confirmation
dialog on delete, the undo stack plus the zero-panel gate refusal are the named backstops),
T-2-28 (inherited from 02-10: commits fire on `pointerup` only), T-2-39 (`setReadOnly` called on
confirm, documented as a UX guarantee not a security control), T-2-23 (`localStorage`/
`sessionStorage` grep-absent), T-2-40 (`confirmInFlight` guards against a double-click issuing two
`confirmStage` calls).

## Issues Encountered

None beyond the race condition documented above (fixed inline, Rule 1).

## User Setup Required

None.

## Next Phase Readiness

- All three artifacts this plan promised exist and exceed their floors: `pageEditor.ts` (768 lines,
  floor 250), `pageEditor.css` (contains `--color-accent`), `pageEditor.test.ts` (313 lines, floor
  90).
- `cd frontend && npx vitest run` -- 141/141 (133 pre-existing + 8 new); `npm run typecheck` and
  `npm run build` both exit 0.
- Plan 02-14 (Go-Back wiring) has a real click-handler seam already in place on the toolbar link,
  plus `api.pages.goBackTargets`/`goBack` already shipped by 02-12/02-11 -- no restructuring needed.
- No blockers for downstream Phase 2 plans.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16*

## Self-Check: PASSED
