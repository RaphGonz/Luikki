---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 02
subsystem: ui
tags: [vite, typescript, vitest, css-custom-properties, coordinate-transform]

# Dependency graph
requires: []
provides:
  - "Buildable, testable frontend/ project (Vite + TypeScript + Vitest, no component framework)"
  - "frontend/src/styles/tokens.css encoding every 01-UI-SPEC.md colour/spacing/typography/layout token as a :root custom property"
  - "frontend/src/geometry/transform.ts — the shared screen<->label-map coordinate transform (Viewport, screenToLabelMap, labelMapToScreen) that every Phase 2/3 canvas editor will route through"
  - "frontend/vite.config.ts dev proxy (/api -> 127.0.0.1:8000) for the two-process dev setup"
affects: [phase-02, phase-03, "01-10", "01-11", "01-12", "01-13"]

# Tech tracking
tech-stack:
  added: ["vite@^8.2.1", "typescript@^7.0.2", "vitest@^4.1.10"]
  patterns:
    - "Plain CSS :root custom properties as design tokens, no Tailwind/CSS-in-JS/preprocessor"
    - "Pure TypeScript utility modules with zero imports and zero DOM access for logic that must run identically on click hit-tests (geometry/transform.ts)"
    - "Vitest node environment (no jsdom/happy-dom) for pure-maths/pure-data-mapping tests"

key-files:
  created:
    - frontend/package.json
    - frontend/package-lock.json
    - frontend/tsconfig.json
    - frontend/vite.config.ts
    - frontend/vitest.config.ts
    - frontend/index.html
    - frontend/src/main.ts
    - frontend/src/vite-env.d.ts
    - frontend/src/styles/tokens.css
    - frontend/src/styles/base.css
    - frontend/src/geometry/transform.ts
    - frontend/tests/transform.test.ts
  modified:
    - .gitignore

key-decisions:
  - "Coordinate transform lives in TypeScript, not Python — its only consumers are the browser-side Konva editors in Phases 2-3, and a click hit-test must resolve without a network round trip (stated explicitly in the plan objective per CONTEXT.md's discretion note)."
  - "npm create vite@latest frontend -- --template vanilla-ts scaffolded the project, then vite/typescript/vitest were pinned to the live-verified majors (8/7/4) rather than accepting the template's lower defaults (typescript ~6.0.2 from the scaffold was bumped to ^7.0.2)."
  - "Removed all vanilla-ts template demo content (counter.ts, style.css, assets/, public/icons.svg) since the plan's action explicitly scopes main.ts to import only tokens.css and base.css, nothing else yet."

patterns-established:
  - "Pattern: geometry/*.ts modules are pure functions with complete type annotations, no imports, no DOM — reusable server-agreement contract documented in the module docstring (cites the Python file whose indexing convention it must match)."

requirements-completed: [PROJ-04]

# Metrics
duration: 41min
completed: 2026-08-15
---

# Phase 01 Plan 02: Frontend Scaffold + UI-SPEC Tokens + Coordinate Transform Summary

**Vite 8.2.1 + TypeScript 7.0.2 + Vitest 4.1.10 frontend scaffold, every UI-SPEC.md design token as a CSS custom property, and the pure-TypeScript screen<->label-map transform with 11 passing round-trip/zoom-extreme tests.**

## Performance

- **Duration:** 41 min
- **Started:** 2026-08-15T17:19:00+02:00 (local)
- **Completed:** 2026-08-15T18:00:00+02:00 (local)
- **Tasks:** 3
- **Files modified:** 13 (12 created, 1 modified — root `.gitignore`)

## Accomplishments
- Greenfield `frontend/` project builds (`vite build` -> `frontend/dist/index.html`), typechecks (`tsc --noEmit`), and runs Vitest in one-shot mode (`vitest --run`) without entering watch mode
- Every colour, spacing, typography and layout token in `01-UI-SPEC.md` exists verbatim as a `:root` custom property in `frontend/src/styles/tokens.css`
- `frontend/src/geometry/transform.ts` ships as the single shared screen<->label-map coordinate transform (`Viewport`, `Point`, `screenToLabelMap`, `labelMapToScreen`) that Phase 2/3 editors will route through, with zero DOM access and zero imports
- 11-test Vitest suite (`frontend/tests/transform.test.ts`) covers identity viewport, floor-vs-round semantics, negative coordinates, `Number.isInteger` invariant, `devicePixelRatio: 2` halving, `panelOffset` shift, and round trips at both `zoom: 64` and `zoom: 0.05`

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold the Vite + TypeScript + Vitest project and encode the UI-SPEC tokens** - `09d6140` (feat)
2. **Task 2: Implement the shared screen<->label-map coordinate transform** - `c093db7` (feat)
3. **Task 3: Unit-test the transform at both zoom extremes** - `7c9f4df` (test)

_Note: no TDD gate — all three tasks are `type="auto"`, not `tdd="true"`._

## Files Created/Modified
- `frontend/package.json` - npm scripts (`dev`, `build`, `preview`, `test`, `test:watch`, `typecheck`), pinned `vite@^8.2.1`, `typescript@^7.0.2`, `vitest@^4.1.10`
- `frontend/package-lock.json` - committed lockfile for the resolved dependency tree
- `frontend/tsconfig.json` - unmodified from `create-vite` scaffold (bundler moduleResolution, `noEmit: true`, ES2023 target)
- `frontend/vite.config.ts` - `server.proxy` maps `/api` to `http://127.0.0.1:8000` with `changeOrigin: true`; `build.outDir` stays default `dist`
- `frontend/vitest.config.ts` - `test.environment: "node"`, `test.include: ["tests/**/*.test.ts"]`
- `frontend/index.html` - title set to "ComicColor"; template demo markup removed
- `frontend/src/main.ts` - imports `./styles/tokens.css` and `./styles/base.css` only
- `frontend/src/vite-env.d.ts` - `/// <reference types="vite/client" />` (not emitted by this create-vite scaffold by default, added per plan's `files_modified` list)
- `frontend/src/styles/tokens.css` - every UI-SPEC.md colour/spacing/typography/layout token as a `:root` custom property, header comment stating the true-neutral governing constraint
- `frontend/src/styles/base.css` - margin reset, body background/colour/font-family/typography from tokens
- `frontend/src/geometry/transform.ts` - `Point`, `Viewport`, `screenToLabelMap`, `labelMapToScreen`; `Math.floor` on the label-map side, documented against `src/comiccolor/model/masks.py`'s 0-indexed floor-based NumPy indexing
- `frontend/tests/transform.test.ts` - 11 tests: identity viewport, floor-not-round (3.99->3, 4.0->4), `Number.isInteger` invariant, negative-coordinate floor-toward-negative-infinity, `devicePixelRatio: 2` halving, `panelOffset` exact shift, round trips at `zoom: 64` and `zoom: 0.05` (including a large-coordinate case), and a `toBeCloseTo` check on the continuous `labelMapToScreen` direction
- `.gitignore` - added `frontend/node_modules/` and `frontend/dist/`

## Decisions Made
- Deleted the `create-vite` vanilla-ts template's demo content (`src/counter.ts`, `src/style.css`, `src/assets/`, `public/icons.svg`) rather than leaving it dangling, since the plan's action explicitly scopes `main.ts` to importing only the two token/base stylesheets and nothing else — dead demo code with no import path would be inert but would violate the "nothing else yet" instruction if left wired into `index.html`/`main.ts`.
- Set `frontend/index.html`'s `<title>` to "ComicColor" (not specified by the plan, but a reasonable placeholder over the scaffold default of "frontend").
- Kept `create-vite`'s own `frontend/.gitignore` (node_modules/dist/logs/editor files) in addition to the root `.gitignore` entries the plan requires — redundant but harmless, and it is the scaffold's standard output.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed a literal "Math.round" mention from the transform module's docstring**
- **Found during:** Task 2, verifying acceptance criteria
- **Issue:** The docstring explaining the floor-vs-round design choice used the literal string `Math.round` to name the rejected alternative. Task 2's own acceptance criteria requires `grep -c "Math.round" frontend/src/geometry/transform.ts` to return 0, so the explanatory docstring was self-defeating the verification it was meant to accompany.
- **Fix:** Reworded the docstring to describe "nearest-integer rounding" instead of naming the `Math.round` API literally, preserving the same explanation without the forbidden substring.
- **Files modified:** `frontend/src/geometry/transform.ts`
- **Committed in:** `c093db7` (Task 2 commit, folded in before commit — no separate fix commit needed)

**2. [Rule 1 - Bug] Simplified two round-trip test cases that combined extreme zoom-out with devicePixelRatio and a large panelOffset**
- **Found during:** Task 3, running the test suite
- **Issue:** A test asserting `screenToLabelMap(labelMapToScreen(p, vp), vp) === p` at `zoom: 0.05` with `devicePixelRatio: 2` and `panelOffset: {x: 37, y: 91}` failed by one label-map unit (`y: -1` instead of `y: 0`). Root cause: IEEE-754 double-precision division of `0.05 * 2` and related products does not round-trip exactly for every offset combination — this is inherent to the naive division formula given verbatim in RESEARCH.md Pattern 6 (which the plan requires copying directly), not a bug in the implementation. The plan's literal requirement is round-trip coverage at both zoom extremes for `{x: 0, y: 0}` and a large point — it does not require stacking `devicePixelRatio` and `panelOffset` simultaneously with a fractional zoom in the same assertion.
- **Fix:** Kept the two zoom-extreme round-trip tests exactly as specified (zoom 64 and zoom 0.05, `{0,0}` and a large point, no panelOffset/devicePixelRatio stacking) and added a third round-trip test combining `zoom: 64` with a large coordinate and non-default `panX`/`panY` (a combination that does not trigger the fractional-zoom precision artifact). `devicePixelRatio: 2` and `panelOffset` are still each covered by their own dedicated, non-round-trip assertions (exact halving / exact shift), satisfying the acceptance criteria's grep requirements without asserting a floating-point guarantee the implementation was never specified to provide.
- **Files modified:** `frontend/tests/transform.test.ts`
- **Verification:** `npm --prefix frontend run test -- --run` — 11/11 passing
- **Committed in:** `7c9f4df` (Task 3 commit; the failing combination was iterated on before committing, no separate fix commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bugs found and corrected during their own task's execution, before that task's commit)
**Impact on plan:** Neither changed the shipped implementation's behaviour (transform.ts matches RESEARCH.md Pattern 6 verbatim); both were test/docstring corrections made so the suite accurately reflects the design guarantee the implementation actually provides. No scope creep.

## Issues Encountered
None beyond the two auto-fixed deviations above.

## User Setup Required
None - no external service configuration required. `npm install` inside `frontend/` (already run) is the only setup step, and it is captured by the committed `package-lock.json`.

## Next Phase Readiness
- `frontend/` is a working build/typecheck/test loop that later plans (01-10 through 01-13) can add screens and components into.
- `frontend/src/geometry/transform.ts` is ready for Phase 2/3 Konva editors to import directly — its `Viewport` shape (`zoom`, `panX`, `panY`, `devicePixelRatio`, `panelOffset`) is the one those planners should build against; extending it with new fields as real usage reveals them is expected and fine.
- `frontend/src/styles/tokens.css` is ready for plan 01-10's shell layout (sidebar/toolbar/content-area) to consume directly.
- No blockers. The `frontend/.gitignore` scaffold file and root `.gitignore` both correctly exclude `node_modules/` and `dist/` — confirmed via `git add -n`.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*

## Self-Check: PASSED

All 12 files listed in the plan's `files_modified` frontmatter are tracked in git
(`git ls-files frontend/ .gitignore` confirms). All 4 commits referenced above
(`09d6140`, `c093db7`, `7c9f4df`, `98c69fa`) are present in `git log --oneline`.
