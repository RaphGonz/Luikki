---
phase: 02-panel-polygon-editor-protected-masks
plan: 10
subsystem: frontend-editor
tags: [typescript, canvas, pointer-events, vitest, jsdom]

# Dependency graph
requires: ["02-06"]
provides:
  - "frontend/src/editor/canvasEditor.ts — mountCanvasEditor: hand-rolled 2D canvas (no Konva/canvas library), two geometry layers, pan/zoom, select/drag/insert/delete/draw pointer interaction, all coordinate math delegated to transform.ts"
  - "frontend/src/styles/editor.css — canvas surround and floating zoom pill, tokens.css only"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Every coordinate conversion in canvasEditor.ts routes through screenToLabelMap/labelMapToScreen — the module itself contains no ad-hoc screen-to-page arithmetic outside the two named viewport constructors (fitToScreen, applyZoomStep)"
    - "Pointer position is converted to a devicePixelRatio-scaled 'backing point' once per event (toBackingPoint), matching the canvas backing store's own dpr-scaled pixel space, so Viewport.zoom * Viewport.devicePixelRatio is the single scale factor used everywhere, per transform.ts's own contract"
    - "T-01-FLOOD / swatchCard.ts's input-updates-visual, change-commits split, reused verbatim: pointermove mutates local state and redraws only; the one onCommit* write happens on pointerup, skipped entirely on a zero-distance drag"
    - "rafScheduled flag decoupled from rafHandle's own assignment, so scheduleRedraw is correct whether requestAnimationFrame is asynchronous (real browsers) or synchronous (the jsdom test stub Task 3 requires)"

key-files:
  created:
    - frontend/src/editor/canvasEditor.ts
    - frontend/src/styles/editor.css
    - frontend/tests/editor/canvasEditor.test.ts
  modified: []

key-decisions:
  - "Reading-order badges are drawn in a dedicated drawPanelBadges() pass at the very end of the z-order (after drawLayer/drawDraft), not interleaved per-shape inside drawLayer — because a panel's badge dimming state depends only on whether 'panels' is the active tool mode as a whole, not on any individual shape's own active/inactive status; a single ctx.globalAlpha for the whole badge pass is both simpler and more correct than threading dimming through drawShape."
  - "canvasEditor.ts's own docstring avoids the literal string 'Konva' (paraphrased as 'any third-party canvas library'/'that library'), matching the precedent 02-01/02-06 set for innerHTML/canvas avoidance wording — the plan's own acceptance criteria grep for 'konva|Konva|fabric' would otherwise false-positive on a comment explaining why the library is NOT used."
  - "setPointerCapture/releasePointerCapture calls are guarded by typeof checks rather than called unconditionally — jsdom does not implement the Pointer Capture API, and the guard makes the module correct in both real browsers and the jsdom test environment without any environment-detection branch."
  - "mount.getBoundingClientRect() is used for both canvas backing-store sizing and pointer-to-backing conversion (never canvas.getBoundingClientRect(), which is a different element even though it fills the same box) — this is what the jsdom test stubs to make screen coordinates deterministic, per the plan's own Task 3 guidance."

requirements-completed: [PAN-02, PAN-03, PROT-02, PROT-03]

# Metrics
duration: 70min
completed: 2026-08-16
---

# Phase 2 Plan 10: Canvas Editor (Mount, Draw Loop, Pointer Interaction) Summary

**A hand-rolled 2D canvas (zero runtime dependencies, D-26) that renders panels and protected masks in UI-SPEC's exact z-order and visual vocabulary, and drives the full select/drag/insert/delete/draw interaction set entirely through plan 02-06's pure reducers, committing a vertex drag exactly once on pointerup.**

## Performance

- **Duration:** ~70 min
- **Tasks:** 3 (2 auto, 1 auto+TDD)
- **Files modified:** 3 (all newly created)

## Accomplishments

- `frontend/src/editor/canvasEditor.ts` — `mountCanvasEditor(mount, options): CanvasEditorHandle`.
  Builds one `<canvas>` (backing store sized to `clientWidth/clientHeight * devicePixelRatio`,
  CSS size 100%) plus a sibling floating zoom-pill `<div>` with three `aria-label`led buttons
  ("Zoom in" / "Zoom out" / "Fit to screen"). A single `requestAnimationFrame`-scheduled draw
  loop paints, in UI-SPEC §10's z-order: page raster → inactive layer at 40% opacity
  (non-interactive) → active layer → selected shape's 2px accent outline and 8px handles →
  hovered edge's 6px half-opacity ghost → in-progress draft polyline with live cursor edge and
  snap-to-close halo → panel reading-order badges (24px, drawn last, dimmed together with the
  rest of the panels layer when it is inactive). Protected masks fill with a `createPattern`
  diagonal hatch in `--color-text-muted` at 25% opacity, dashed when `touched` is false and
  solid when true. Every colour and font token is read once from `getComputedStyle(mount)` — no
  hex literal anywhere in the file. `panelOffset` is hard-coded `{ x: 0, y: 0 }` with a comment
  explaining why (page-pixel space; Phase 3's zone editor is the first consumer of a non-zero
  offset).
- Pointer interaction (Pointer Events only, `setPointerCapture` during a drag, guarded by
  `typeof` checks since jsdom does not implement pointer capture): `pointerdown` tries
  `hitTestVertex` → `hitTestEdge` → `hitTestShape` in that priority order. A vertex hit starts a
  drag that mutates local state on every `pointermove` and redraws, calling no `onCommit*`
  callback until `pointerup` — and skips the call entirely on a zero-distance drag, mirroring
  `swatchCard.ts`'s `lastCommittedHex` guard. An edge hit inserts a vertex and commits
  immediately (no drag phase). A shape hit selects and fires `onSelectionChange`; empty canvas
  clears selection. `Delete`/`Backspace` removes the selected vertex (firing `onDeleteRefused`
  below 3 vertices, changing nothing) or the selected shape (no dialog, per D-19/§5). `Escape`
  cancels an in-progress draft, `Enter` closes it. `+`/`-`/`0` map to zoom in/out/fit. Middle-drag
  or space-drag pans; wheel zooms about the cursor, both routed through
  `screenToLabelMap`/`labelMapToScreen` rather than duplicating their arithmetic.
  `setReadOnly(mode, true)` makes every mutating path a no-op while selection/hover keep working.
  Inactive-layer shapes are never passed to `hitTest`.
- `frontend/src/styles/editor.css` — full-bleed canvas surround (`--color-surface-dominant`, no
  card padding), the floating pill (`--color-surface-secondary`, 32px `--icon-hit` buttons,
  `--space-lg` offset, `z-index: 10`), and cursor states for select/draw/pan. Every value is an
  existing token; no new colour declared.
- `frontend/tests/editor/canvasEditor.test.ts` — `// @vitest-environment jsdom` first line, stubs
  `HTMLCanvasElement.prototype.getContext` (all 2D-context methods as `vi.fn()` no-ops) and a
  synchronous `requestAnimationFrame`, dispatches real `PointerEvent`s (with a documented
  `MouseEvent` fallback for jsdom versions lacking `PointerEvent`) against a stubbed
  `mount.getBoundingClientRect()`. 7 tests: mount structure + ARIA labels; a multi-move drag
  commits exactly once; a zero-distance drag commits zero times; read-only mode commits zero
  times; a shape-body click fires `onSelectionChange`; a vertex delete on a 3-vertex triangle
  fires `onDeleteRefused` and never `onCommitPolygon`; `destroy()` detaches the canvas and a
  subsequent `pointerdown` on it fires nothing. No assertion inspects drawn pixels or canvas
  image data.
- `cd frontend && npx vitest run` — whole suite green: 13 test files, 117 tests (110 pre-existing
  + 7 new). `npm run typecheck` and `npm run build` both exit 0.
- All plan-specified greps pass: `screenToLabelMap|labelMapToScreen` appears 20 times in
  `canvasEditor.ts`; the ad-hoc-arithmetic pattern (`* vp.zoom`, `/ vp.zoom`, `* zoom * `,
  `panX +`, `panY +`) matches only inside `fitToScreen`/`applyZoomStep`; no `innerHTML`; no hex
  colour literals; no `konva|Konva|fabric` reference; `frontend/package.json` still declares zero
  runtime dependencies; no `mousedown|mousemove|mouseup`; `setPointerCapture` present; no
  `fetch|api.` reference; no `onCommit*` call inside the `pointermove` handler.

## Task Commits

Each task was committed atomically:

1. **Task 1 + Task 2: canvas mount, draw loop, viewport control, pointer interaction** —
   `0bb71ff` (feat) — combined into one commit since both tasks build the same single file
   incrementally (mount/render, then interaction on top of it) and the plan's acceptance
   criteria for both are only meaningfully checkable once the file is complete.
2. **Task 3: jsdom coverage** — `10501ae` (test) — includes the `rafScheduled` bug fix described
   below, found while writing this task's tests, before any commit.

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `frontend/src/editor/canvasEditor.ts` (new) — canvas mount, draw loop, pointer interaction
- `frontend/src/styles/editor.css` (new) — canvas surround, floating zoom pill
- `frontend/tests/editor/canvasEditor.test.ts` (new)

## Decisions Made

See `key-decisions` in the frontmatter for the four load-bearing ones (badge-dimming pass
placement, docstring wording to satisfy the Konva-absence grep literally, pointer-capture
guards, and using `mount.getBoundingClientRect()` consistently).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `rafScheduled` flag added to fix a synchronous-`requestAnimationFrame`
redraw-blocking bug**
- **Found during:** Task 3, while writing the jsdom test's synchronous `requestAnimationFrame`
  stub (required by the plan's own Task 3 action text).
- **Issue:** `scheduleRedraw()` guarded re-entrancy with `if (rafHandle !== null) return;` and set
  `rafHandle = requestAnimationFrame(cb)`, where `cb` itself set `rafHandle = null`. Under a
  *synchronous* `requestAnimationFrame` (the shape the test stub uses, and the shape the plan's
  Task 3 explicitly specifies: "stub `requestAnimationFrame` to run its callback synchronously"),
  `cb` runs and sets `rafHandle = null` *before* the outer `rafHandle = requestAnimationFrame(...)`
  assignment itself completes — so the outer assignment then overwrites `rafHandle` back to a
  non-null value immediately afterward, permanently tripping the re-entrancy guard for the rest
  of the module's lifetime. In a real (asynchronous) browser this ordering issue never surfaces,
  but the module must be correct under both, since the plan's own required test harness is
  synchronous.
- **Fix:** Introduced a separate `rafScheduled` boolean, set `true` before calling
  `requestAnimationFrame` and reset to `false` inside the callback — independent of when
  `rafHandle`'s own assignment completes, so the guard is correct regardless of sync/async timing.
- **Files modified:** `frontend/src/editor/canvasEditor.ts`
- **Commit:** `10501ae`

None beyond the above.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- All three artifacts this plan promised exist: `canvasEditor.ts` (798 lines, well above the
  250-line floor), `editor.css`, and `canvasEditor.test.ts` (279 lines, above the 70-line floor).
- `mountCanvasEditor`/`CanvasEditorHandle`/`CanvasEditorOptions` are the exact exported shapes the
  plan specified, ready for a toolbar/view-layer plan to wire `setShapes` from server responses,
  `onCommit*` to real API calls, and the in-editor undo stack (`undoStack.ts`, plan 02-06) on top
  — none of which this plan's tasks included, per its own stated module boundary ("this module
  raises the events, the view commits them").
- No blockers for downstream Phase 2 plans.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16*

## Self-Check: PASSED
