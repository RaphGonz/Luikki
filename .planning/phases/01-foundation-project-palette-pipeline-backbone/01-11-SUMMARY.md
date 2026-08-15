---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 11
subsystem: frontend
tags: [vite, typescript, vitest, hash-router, fetch-client, no-framework]

# Dependency graph
requires:
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Vite/TS/Vitest scaffold and UI-SPEC tokens.css (plan 01-02)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "The 22 Pydantic DTOs in web/schemas.py (plan 01-06)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Project lifecycle routes and error-copy constants (plan 01-07)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Volume/page/pipeline routes (plan 01-08) and palette routes (plan 01-09)"
provides:
  - "frontend/src/api/client.ts — the typed api namespace (projects/volumes/pages/pipeline/palette/references) every later view calls"
  - "frontend/src/api/types.ts — every DTO interface plans 01-12/01-13 need, declared once"
  - "frontend/src/shell/router.ts — Route union, parseRoute/buildHash/navigate/startRouter, all four views registered"
  - "frontend/src/shell/sidebar.ts, toolbar.ts — the persistent shell chrome"
  - "frontend/src/views/pageGrid.ts, pageDetail.ts, palette.ts — stub view seats for plans 01-12/01-13"
  - "frontend/src/components/toast.ts — showToast for plan 01-13's recolour feedback"
  - "frontend/src/views/projectPicker.ts — the working recent-projects/create/browse screen"
affects: ["01-12", "01-13"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Views are plain functions returning a teardown callback: (mount, params?) => () => void — no component framework, no reactive render model, per 01-UI-SPEC.md's Design System table and CONTEXT.md's discretion note"
    - "All DOM text insertion via textContent, never innerHTML, for every artist- or server-supplied string (T-01-XSS)"
    - "Route is a closed discriminated union with a total parseRoute (unknown/malformed/non-numeric hash always falls back to {kind: picker}) — T-01-HASH"
    - "Same-origin relative /api/... URLs only, grep-asserted zero http(s):// literals — T-01-ORIGIN"
    - "No localStorage/sessionStorage anywhere in the picker — the server-side recents index is the only source, self-healing per D-04"

key-files:
  created:
    - frontend/src/api/types.ts
    - frontend/src/api/client.ts
    - frontend/tests/client.test.ts
    - frontend/src/shell/router.ts
    - frontend/src/shell/sidebar.ts
    - frontend/src/shell/toolbar.ts
    - frontend/src/views/pageGrid.ts
    - frontend/src/views/pageDetail.ts
    - frontend/src/views/palette.ts
    - frontend/src/views/projectPicker.ts
    - frontend/src/components/toast.ts
    - frontend/tests/router.test.ts
    - frontend/tests/projectPicker.test.ts
  modified:
    - frontend/src/main.ts
    - frontend/src/styles/shell.css

key-decisions:
  - "The Route union has no dedicated 'project shell (empty)' kind (the plan specifies exactly picker/volume/page/palette). renderProjectPicker itself checks api.projects.current() on load: if a project is already open it swaps in-place to UI-SPEC §8's shell-empty prompt instead of the recents list, covering both screens without a fifth Route variant or touching router.ts."
  - "Volume create/rename use window.prompt() rather than an inline form, matching the plan's own framing of sidebar volume CRUD as 'minimal per D-03' — the kebab menu plus native prompts is the smallest correct implementation; a richer inline-edit UI is available to revisit later without changing the API surface."

requirements-completed: [PROJ-01, PROJ-05]

# Metrics
duration: ~75min
completed: 2026-08-15
---

# Phase 01 Plan 11: App Shell + Project Picker Summary

**The typed fetch client covering all six route groups, a total hash router with pure parse/build helpers, the token-only three-region shell (240px sidebar / 56px toolbar / full-bleed content), and a working recent-projects picker with create/browse/persistent-error handling — 38 Vitest tests, clean typecheck, and a working `vite build`.**

## Performance

- **Duration:** ~75 min
- **Tasks:** 3
- **Files modified:** 15 (13 created, 2 modified)

## Accomplishments

- `frontend/src/api/client.ts` implements `apiUrl`, `ApiError` (with 422 validation-array flattening and a status-derived fallback that never says "Something went wrong"), and the `api` namespace grouping all six route families (`projects`, `volumes`, `pages`, `pipeline`, `palette`, `references`) against the exact routes/status codes recorded in 01-06 through 01-09's SUMMARY.md and `src/comiccolor/web/schemas.py`.
- `frontend/src/api/types.ts` declares every DTO interface `schemas.py` exposes, field-for-field, including the closed `PipelineStageName` string union (`import`..`export`) sourced from `model/entities.py`'s `PipelineStage` enum.
- `frontend/src/shell/router.ts`'s `parseRoute` is total — an unknown, malformed, non-numeric, or negative id always falls back to `{kind: "picker"}` (T-01-HASH) — and `buildHash(parseRoute(h)) === h` round-trips for every valid hash form.
- `frontend/src/styles/shell.css` is a CSS grid (`.app-shell` → `.app-sidebar` / `.app-toolbar` / `.app-content`) built entirely from `tokens.css` custom properties; `.app-content` carries no padding, max-width or margin, so a Phase 2/3 Konva canvas can mount edge to edge without redesigning the shell (01-UI-SPEC.md §8).
- `frontend/src/shell/sidebar.ts` fetches the project name and Volume→Page tree live, uses the accent colour only for the current-item indicator, and gives every icon-only control (expand/collapse toggle, kebab menu) an `aria-label` naming its action and target, never its glyph.
- `frontend/src/views/projectPicker.ts`'s `recentListModel` is a pure function (most-recent-first, exactly one selected row, current-project-wins-if-open, empty input → empty output) with its own Vitest suite; `renderProjectPicker` renders the recents list as the visual anchor, "Create Project" as a secondary CTA, a "Browse…" fallback wired to the 200/204/503 contract, and a persistent inline error banner rendering `ApiError.detail` verbatim without ever clearing the artist's typed input.
- Full verification: `npm --prefix frontend run typecheck` exits 0, `npm --prefix frontend run test -- --run` exits 0 with 38/38 tests passing across 4 suites (11 baseline transform + 9 client + 12 router + 6 projectPicker), and `npm --prefix frontend run build` writes `frontend/dist/index.html`.

## Task Commits

Each task was committed atomically:

1. **Task 1: The typed API client covering the whole phase's endpoint surface** - `9c2dfb1` (feat)
2. **Task 2: The app shell — router, sidebar, toolbar and the canvas-ready content region** - `291bf7c` (feat)
3. **Task 3: The project picker — recents first, create second, browse as fallback** - `0df7ef5` (feat)

## Files Created/Modified

- `frontend/src/api/types.ts` - all DTO interfaces mirroring `web/schemas.py`, plus `PipelineStageName` and `RGBTuple`
- `frontend/src/api/client.ts` - `apiUrl`, `ApiError`, `api` (all six route groups)
- `frontend/tests/client.test.ts` - DOM-free coverage for `apiUrl` and `ApiError.fromResponse`
- `frontend/src/shell/router.ts` - `Route`, `parseRoute`, `buildHash`, `navigate`, `startRouter`
- `frontend/src/shell/sidebar.ts` - `renderSidebar` (project name, Volume→Page tree, kebab CRUD, Palette entry)
- `frontend/src/shell/toolbar.ts` - `renderToolbar` (56px strip, title + slot)
- `frontend/src/views/pageGrid.ts`, `pageDetail.ts`, `palette.ts` - stub views for plans 01-12/01-13
- `frontend/src/views/projectPicker.ts` - `recentListModel`, `renderProjectPicker`
- `frontend/src/components/toast.ts` - `showToast`
- `frontend/tests/router.test.ts` - `parseRoute`/`buildHash` coverage, including round-trips
- `frontend/tests/projectPicker.test.ts` - `recentListModel` coverage
- `frontend/src/main.ts` (modified) - bootstraps sidebar/toolbar/content and calls `startRouter`
- `frontend/src/styles/shell.css` (modified) - shell grid, sidebar/toolbar/content, project-picker and toast rules, all token-only

## API Surface Signatures (for plans 01-12 and 01-13)

```ts
// frontend/src/api/client.ts
export function apiUrl(path: string, query?: Record<string, string | number | undefined>): string;
export class ApiError extends Error { status: number; detail: string; static fromResponse(res: Response): Promise<ApiError>; }
export const api: {
  projects: { create, open, current, close, recent, browse };
  volumes: { list, create, rename, remove };
  pages: { upload, list, get, remove, imageUrl };
  pipeline: { stages };
  palette: { list, create, update, remove, swatch };
  references: { uploadSheet, accept, discard, sheetImageUrl };
};
```

## Route Union (for plan 01-12's page grid/detail links and plan 01-13's palette entry)

```ts
// frontend/src/shell/router.ts
export type Route =
  | { kind: "picker" }
  | { kind: "volume"; volumeId: number }
  | { kind: "page"; pageId: number }
  | { kind: "palette" };
export function parseRoute(hash: string): Route;
export function buildHash(route: Route): string;
export function navigate(route: Route): void;
export function startRouter(mount: HTMLElement): void;
```

## View-Function Contract (for plans 01-12 and 01-13's real implementations)

```ts
// stubs already registered in router.ts — replace the body only, never the signature
export function renderPageGrid(mount: HTMLElement, params: { volumeId: number }): () => void;
export function renderPageDetail(mount: HTMLElement, params: { pageId: number }): () => void;
export function renderPalette(mount: HTMLElement): () => void;
```

## `showToast` Signature (for plan 01-13's recolour feedback)

```ts
// frontend/src/components/toast.ts
export interface ToastOptions { durationMs?: number; }
export function showToast(message: string, options?: ToastOptions): void;
```

## Decisions Made

- The `Route` union intentionally has no fifth "project shell (empty)" kind, matching the plan's literal specification (`picker`/`volume`/`page`/`palette` only). `renderProjectPicker` resolves this by checking `api.projects.current()` on every load: a 409 (no project open) renders the recents picker, while a 200 (project already open, whether from a fresh page load or the moment this same view just opened/created one) swaps in-place to the UI-SPEC §8 shell-empty prompt. This keeps both screens the plan's Screen Inventory describes without adding router surface plans 01-12/01-13 would need to know about.
- Sidebar volume create/rename use `window.prompt()` rather than a custom inline form. The plan explicitly frames volume CRUD as "minimal per D-03" (kebab menu per row, nothing more elaborate specified); native prompts are the smallest implementation that satisfies create/rename/delete without inventing UI the plan didn't ask for. The API calls underneath (`api.volumes.create/rename/remove`) are the real contract plan 01-12 depends on, so a richer inline-edit UI can replace the prompt calls later without touching the API surface.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created a placeholder `frontend/src/views/projectPicker.ts` in Task 2**
- **Found during:** Task 2, running `npm --prefix frontend run typecheck`
- **Issue:** Task 2's `router.ts` must register the `"picker"` route by importing `renderProjectPicker` from `../views/projectPicker`, but that module is Task 3's own file per the plan's task/file split. Without it, Task 2 cannot typecheck or build — `tsc` failed with `TS2307: Cannot find module '../views/projectPicker'`.
- **Fix:** Created a minimal stub `views/projectPicker.ts` (exporting `renderProjectPicker(mount) => teardown`, rendering a `"Loading…"` placeholder) as part of Task 2's commit, following the exact same stub pattern already used for `pageGrid.ts`/`pageDetail.ts`/`palette.ts`. Task 3 then replaced the stub body with the real implementation without touching `router.ts` or any other file, so the net result matches the plan's intent (`router.ts` never edited again after Task 2) even though `views/projectPicker.ts` was technically first touched one task earlier than its own `<files>` list states.
- **Files modified:** `frontend/src/views/projectPicker.ts` (created in Task 2's commit `291bf7c`, replaced with the real implementation in Task 3's commit `0df7ef5`)
- **Verification:** `npm --prefix frontend run typecheck && npm --prefix frontend run test -- --run && npm --prefix frontend run build` all passed after the fix in both Task 2 and Task 3.
- **Impact:** No scope creep — the stub content matched the other three stub views' pattern exactly, and Task 3 fully replaced it as originally scoped.

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking, resolved by creating a same-pattern stub one task earlier than its literal file-ownership boundary)
**Impact on plan:** None on the shipped behavior or file ownership after Task 3 completes; `router.ts` was still authored once (Task 2) and never touched again, satisfying the plan's stated goal that 01-12/01-13 (and, transitively, this plan's own Task 3) never need to edit it.

## Issues Encountered

- `frontend/node_modules` was absent in this fresh worktree (expected per the environment note) — ran `npm --prefix frontend install` once before Task 1's verification, which resolved cleanly against the committed `package-lock.json` from plan 01-02.

## User Setup Required

None — no external service configuration required.

## Known Stubs

Intentional, plan-scoped stubs (not violations — each is the seat plan 01-12 or 01-13 fills):

| File | What it renders | Filled by |
|---|---|---|
| `frontend/src/views/pageGrid.ts` | `"Coming in plan 01-12 (volume {id})"` placeholder | Plan 01-12 (PROJ-02, PROJ-04) |
| `frontend/src/views/pageDetail.ts` | `"Coming in plan 01-12 (page {id})"` placeholder | Plan 01-12 (PROJ-04) |
| `frontend/src/views/palette.ts` | `"Coming in plan 01-13"` placeholder | Plan 01-13 (PAL-01..04) |

All three are registered in `router.ts` now (per the plan's explicit goal) so neither later plan needs to touch the router.

## Next Phase Readiness

- `api/client.ts`, `api/types.ts`, `shell/router.ts` and `components/toast.ts` are stable, fully-typed, tested contracts — plans 01-12 and 01-13 build directly against the signatures recorded above and should not need to touch `main.ts`, `router.ts` or `client.ts`.
- `views/pageGrid.ts`, `pageDetail.ts` are ready for plan 01-12 to fill in-place; `views/palette.ts` is ready for plan 01-13.
- The project picker is a real, working screen end to end against the live backend routes from plans 01-06/01-07 (create/open/current/close/recent/browse) — no mocked data anywhere.
- No blockers for plans 01-12 or 01-13.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*

## Self-Check: PASSED

All 15 files listed in the plan's `files_modified` frontmatter (plus the
Task-2-created `views/projectPicker.ts` stub later replaced by Task 3) are
present on disk. All three task commits (`9c2dfb1`, `291bf7c`, `0df7ef5`)
are present in `git log --oneline --all`.
