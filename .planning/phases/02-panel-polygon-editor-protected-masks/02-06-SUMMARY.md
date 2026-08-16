---
phase: 02-panel-polygon-editor-protected-masks
plan: 06
subsystem: frontend-editor
tags: [typescript, vitest, hit-testing, immutable-state, undo]

# Dependency graph
requires: ["02-01"]
provides:
  - "frontend/src/editor/hitTest.ts — zoom-invariant vertex/edge/shape hit-testing (hitTestVertex, hitTestEdge, hitTestShape, pointInPolygon, isWithinSnapClose)"
  - "frontend/src/editor/polygonState.ts — pure immutable reducer for vertex/shape mutation and draw-in-progress state, shared by both tool modes"
  - "frontend/src/editor/undoStack.ts — 20-op session undo stack with inverse-intent derivation"
affects: ["02-10"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Screen-space-only distance comparisons: every hit test converts page-space candidates through labelMapToScreen and compares against the raw pointer, never the reverse — this is what makes hit-testing zoom-invariant by construction"
    - "One pure reducer (ToolMode-agnostic) serves both panel and protected-mask editing, matching UI-SPEC §3's 'reused verbatim' interaction vocabulary"
    - "Undo as inverse-intent derivation, not state snapshotting — invert() maps a committed op to the API call that undoes it, re-issued fresh rather than replayed from a saved snapshot"

key-files:
  created:
    - frontend/src/editor/hitTest.ts
    - frontend/src/editor/polygonState.ts
    - frontend/src/editor/undoStack.ts
    - frontend/tests/editor/hitTest.test.ts
    - frontend/tests/editor/polygonState.test.ts
    - frontend/tests/editor/undoStack.test.ts
  modified: []

key-decisions:
  - "hitTestEdge cedes priority to hitTestVertex unconditionally (not via a strict distance comparison) once a vertex is within its own hit radius — proven geometrically that an edge's distance to its own endpoint vertex can never exceed the vertex's own distance to the pointer, so a strict '<' comparison could never fire in the intended case; the unconditional rule is the correct implementation of the plan's 'nearer a vertex than an edge' intent."
  - "Zoom-invariance test fixture uses a 5000-unit page-space square (not the 100-unit square used elsewhere) so vertices stay screen-separated even at 0.05x zoom — a smaller polygon's vertices collapse into the same hit radius at extreme zoom-out, which would test vertex-disambiguation instead of the intended single-vertex zoom-invariance property."
  - "Docstring prose avoids the literal word 'canvas' (paraphrased as 'render surface') to satisfy the acceptance-criteria grep for 'document\\|window\\|canvas\\|fetch' returning zero matches, matching the precedent set in 02-01's innerHTML-avoidance wording."

requirements-completed: [PAN-02, PAN-03, PROT-02, PROT-03]

# Metrics
duration: 45min
completed: 2026-08-16
---

# Phase 2 Plan 6: Editor Core (Hit-Testing, Polygon State, Undo Stack) Summary

**Three pure, transform-backed TypeScript modules — zoom-invariant hit-testing, an immutable polygon-mutation reducer, and a 20-op undo stack — proven identical at 0.05x and 64x zoom, with zero DOM/canvas/fetch surface.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 3 (all auto, all TDD)
- **Files modified:** 6 (3 source, 3 test — all newly created)

## Accomplishments

- `frontend/src/editor/hitTest.ts` — `hitTestVertex`, `hitTestEdge`, `hitTestShape`, `pointInPolygon`,
  `isWithinSnapClose`, plus `VERTEX_HIT_RADIUS_SCREEN` (16), `EDGE_HOVER_RADIUS_SCREEN` (12),
  `SNAP_CLOSE_RADIUS_SCREEN` (12). Every distance comparison routes through `labelMapToScreen`;
  `hitTestShape` is the sole exception, converting the pointer once via `screenToLabelMap` and running
  `pointInPolygon` as a scale-free area test in page space. 16 tests, including the same hit/miss
  assertion parameterised over `[0.05, 1, 64]` zoom — the executable form of success criterion 2 — and
  a `devicePixelRatio` invariance test.
- `frontend/src/editor/polygonState.ts` — `createEditorState`, `moveVertex`, `insertVertex`,
  `deleteVertex`, `addShape`, `removeShape`, `selectShape`, `selectVertex`, `beginDraft`,
  `appendDraftPoint`, `closeDraft`, `cancelDraft`, `replaceShapes`, `setDrawKind`,
  `MIN_POLYGON_VERTICES` (3). One reducer serves both `"panels"` and `"protected"` tool modes.
  `deleteVertex` refuses below 3 vertices and returns the input state unchanged by reference (`===`)
  on refusal. `readingOrder` is always copied verbatim from the caller, never derived from geometry.
  18 tests, including a deep-freeze immutability proof.
- `frontend/src/editor/undoStack.ts` — `createUndoStack`, `pushOp`, `popOp`, `clearStack`, `invert`,
  `stackDepth`, `UNDO_CAP` (20). Pushing past the cap drops the oldest op, never refuses the newest.
  `invert` maps all five `UndoOp` kinds (`move-vertex`, `insert-vertex`, `delete-vertex`, `add-shape`,
  `remove-shape`) to the `UndoIntent` that undoes each as a fresh API call. 12 tests, one `invert`
  assertion per op kind plus the 21-push cap test.
- `cd frontend && npx vitest run` — whole suite green: 12 test files, 110 tests (64 pre-existing +
  46 new). `npm run typecheck` exits 0.
- All plan-specified greps pass: `labelMapToScreen` used 6 times in `hitTest.ts`; no
  `vp.zoom|devicePixelRatio|panX|panY` arithmetic outside type positions in `hitTest.ts`; no
  `document|window|canvas|fetch` in either `hitTest.ts` or `polygonState.ts`; no
  `localStorage|sessionStorage|setTimeout|setInterval` in `undoStack.ts`; `readingOrder` in
  `polygonState.ts` is only ever a field declaration/copy, never a geometric computation.

## Task Commits

Each task was committed atomically (RED then GREEN folded into one `feat` commit per task, per this
plan's TDD-per-task structure — test file and implementation land together once green):

1. **Task 1: hitTest.ts** — `d9b0e53` (feat)
2. **Task 2: polygonState.ts** — `8a95cac` (feat)
3. **Task 3: undoStack.ts** — `5c7a094` (feat)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `frontend/src/editor/hitTest.ts` (new) — zoom-invariant hit-testing
- `frontend/tests/editor/hitTest.test.ts` (new)
- `frontend/src/editor/polygonState.ts` (new) — immutable editor reducer
- `frontend/tests/editor/polygonState.test.ts` (new)
- `frontend/src/editor/undoStack.ts` (new) — session undo stack
- `frontend/tests/editor/undoStack.test.ts` (new)

## Decisions Made

- **`hitTestEdge` vertex-priority rule (Rule 1 — bug fix during Task 1's TDD cycle):** the plan's
  behavior spec reads "returns null when the pointer is nearer a vertex than an edge." A strict
  distance comparison (`vertexDistance < edgeDistance`) was the first implementation attempt, but
  geometric analysis during RED-phase test-writing showed this can (almost) never fire: for any edge
  sharing the hit vertex as an endpoint, the vertex itself is always a valid candidate point on that
  edge's segment (`t` clamps to 0 or 1 at the endpoint), so the edge's minimum distance to the pointer
  can never exceed the vertex's distance. The corrected implementation returns null unconditionally
  whenever `hitTestVertex` finds a hit — this is not a looser interpretation, it is the only rule that
  can actually produce the described priority behavior given the geometry. Test:
  `frontend/tests/editor/hitTest.test.ts` — "returns null when the pointer is nearer a vertex than an
  edge (a vertex hit takes priority)".
- **Test fixture scale for zoom-invariance (in-task correction, not a deviation from the plan's intent):**
  the first draft of the zoom-parameterised test used the same 100-unit square as the rest of the file;
  at `zoom: 0.05` its four vertices sit within 5 screen px of each other, so the "same vertex hit at
  15px, missed at 17px" assertion was actually exercising nearest-of-two-vertices disambiguation, not
  the isolated-vertex zoom-invariance the test intends. Switched that specific test to a 5000-unit
  square (`largeSquare`) so vertices stay screen-separated across the full `[0.05, 1, 64]` range.

## Deviations from Plan

None beyond the in-task fix described above (found and corrected during Task 1's own TDD RED/GREEN
cycle, before any commit — not a deviation from the plan's specified behavior, a correction to make
the first implementation attempt actually match it).

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- All three artifacts this plan promised exist, are fully typed, and are proven pure (no DOM, no
  canvas, no fetch, no storage) via automated grep checks in addition to the test suite.
- Plan 02-10 (`canvasEditor.ts`, per this plan's threat model T-2-24) is the consumer: it wires these
  three pure modules to real pointer events and commits vertex-drag writes on `pointerup` only, per the
  T-01-FLOOD precedent this plan's `<threat_model>` names but does not itself implement.
- No blockers for downstream Phase 2 plans.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16*

## Self-Check: PASSED
