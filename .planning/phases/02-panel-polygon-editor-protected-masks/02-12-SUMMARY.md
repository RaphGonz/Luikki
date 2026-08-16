---
phase: 02-panel-polygon-editor-protected-masks
plan: 12
subsystem: frontend-api
tags: [typescript, fetch-client, router, dto]

# Dependency graph
requires:
  - phase: 02-05
    provides: "PanelResponse/PanelListResponse, ProtectedMaskResponse/ProtectedMaskListResponse, StageConfirmResponse, GoBackTargetResponse/GoBackRequest schemas"
  - phase: 02-08
    provides: "panel.py routes: list/create/moveVertex/setPolygon/remove"
  - phase: 02-09
    provides: "protected.py routes: list/create/moveVertex/setPolygon/remove"
provides:
  - "VertexDto/PanelDto/PanelListDto, ProtectedKindDto/ProtectedMaskDto/ProtectedMaskListDto, StageConfirmDto/GoBackTargetDto in frontend/src/api/types.ts"
  - "api.panels.*, api.protected.*, and api.pages.confirmStage/goBackTargets/goBack in frontend/src/api/client.ts"
  - "The pageEditor route (#/page/{id}/edit) in frontend/src/shell/router.ts, plus a placeholder views/pageEditor.ts"
affects: [02-13, 02-14]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Namespace-per-resource client methods (api.panels, api.protected) added to the existing api object, no new request helper"
    - "Every mutation on panels/protected resolves to the DTO shape the server's response_model actually returns (list for panels, single object for protected, void for 204s) rather than a uniform shape"

key-files:
  created:
    - frontend/src/views/pageEditor.ts
  modified:
    - frontend/src/api/types.ts
    - frontend/src/api/client.ts
    - frontend/src/shell/router.ts
    - frontend/tests/client.test.ts
    - frontend/tests/router.test.ts

decisions:
  - "api.protected.create/moveVertex/setPolygon resolve to a single ProtectedMaskDto, not a list — the real protected.py routes (read directly from the merged worktree) return ProtectedMaskResponse, not ProtectedMaskListResponse, unlike the panel routes which do return the whole list. The plan's 'mirror the same shapes' instruction is read as 'mirror the server contract exactly' (the plan's own must-haves truth), which took precedence over the looser prose."
  - "The three stage-gate paths (/stage/confirm, /stage/go-back-targets, /stage/go-back) were sourced from 02-11-PLAN.md's task actions rather than a merged page.py, since plan 02-11 (parallel sibling wave-4 executor) had not landed in this worktree at execution time. Paths, methods and response_model types match that plan's specified contract exactly (StageConfirmResponse for confirm and go-back, list[GoBackTargetResponse] for go-back-targets)."

metrics:
  duration_minutes: 25
  tasks_completed: 2
  files_changed: 6
  completed_date: "2026-08-16"
---

# Phase 02 Plan 12: Frontend API Client and Page-Editor Route Summary

Typed fetch client covering all thirteen Phase 2 endpoints (panels, protected masks, stage gates), plus the `#/page/{id}/edit` route the editor screen will mount on.

## What Was Built

**Task 1 — DTOs and client methods.** Added to `frontend/src/api/types.ts`: `VertexDto` (`[number, number]`), `PanelDto`/`PanelListDto`, `ProtectedKindDto`/`ProtectedMaskDto`/`ProtectedMaskListDto`, `StageConfirmDto`, `GoBackTargetDto` — field names and types read directly from `src/comiccolor/web/schemas.py`'s `PanelResponse`, `ProtectedMaskResponse`, `StageConfirmResponse` and `GoBackTargetResponse`.

Added to `frontend/src/api/client.ts`: an `api.panels` namespace (`list/create/moveVertex/setPolygon/remove`, all resolving to `PanelListDto` since every panel route — including delete — returns the server-recomputed whole list) and an `api.protected` namespace (`list` resolves `ProtectedMaskListDto`; `create/moveVertex/setPolygon` resolve the single `ProtectedMaskDto` the real routes actually return; `remove` resolves `void` for the 204). Added `confirmStage`, `goBackTargets`, `goBack` to the existing `api.pages` namespace. No new request helper, retry or interceptor — every method goes through the existing `apiUrl`/`request`/`jsonRequest` seam.

Extended `frontend/tests/client.test.ts` with a `stubFetch` helper (`vi.stubGlobal("fetch", ...)` returning a real `Response`) and one URL/method/body assertion per new method — 15 new tests covering all 13 methods (panels' 5, protected's 5, pages' 3, with `remove` covered for both panels and protected).

**Task 2 — the page-editor route.** Added `{ kind: "pageEditor"; pageId: number }` to `Route` in `frontend/src/shell/router.ts`. `parseRoute` recognises a third path segment `"edit"` after a valid `page` id and returns `pageEditor`; a malformed id (`#/page/abc/edit`) falls through to the same picker fallback every other route already uses (T-01-HASH), unchanged. `buildHash` and `dispatch` got the new case; TypeScript's exhaustiveness check on the `Route` union would flag either being missed.

Because `views/pageEditor.ts` did not exist yet in this worktree (plan 02-13 not yet run), created a minimal placeholder: mounts an empty `<div class="page-editor-placeholder">` and returns a no-op teardown, with a comment that 02-13 replaces it wholesale.

## Deviations from Plan

### Auto-fixed / clarified during execution

**1. [Not a Rule 1-4 deviation — plan ambiguity resolved by the plan's own precedence rule] `api.protected.create/moveVertex/setPolygon` return a single DTO, not a list**
- **Found during:** Task 1, reading `src/comiccolor/web/routers/protected.py`
- **Issue:** The plan's `<behavior>` prose said protected methods "mirror the same shapes" as panels (which return the whole list on every mutation). The actual merged `protected.py` routes have `response_model=ProtectedMaskResponse` (a single object) for create/moveVertex/setPolygon — only `list` returns `ProtectedMaskListResponse`.
- **Resolution:** Followed the plan's own must-haves truth — "The DTO types mirror the server's response models field for field" — and the `<read_first>` instruction to read `protected.py` for "the exact paths, methods and status codes." Typed the three single-object methods as `Promise<ProtectedMaskDto>`.
- **Files modified:** `frontend/src/api/client.ts`
- **Commit:** 626d8f6

**2. [Rule 3 — auto-fix blocking issue] Stage-gate route paths sourced from 02-11-PLAN.md, not a merged page.py**
- **Found during:** Task 1, confirming the three stage-gate paths
- **Issue:** `src/comiccolor/web/routers/page.py` has no `/stage/confirm`, `/stage/go-back-targets` or `/stage/go-back` routes yet — plan 02-11 (a parallel sibling wave-4 executor building those exact routes) had not merged into this worktree at execution time, contrary to the environment note that server routes were already merged (that note covered only panel.py and protected.py, which were correct).
- **Resolution:** Read `02-11-PLAN.md`'s task actions directly, which specify the exact route decorators, paths and `response_model` types (`StageConfirmResponse` for confirm and go-back, `list[GoBackTargetResponse]` for go-back-targets, `GoBackRequest{target}` as the go-back body). Built the client methods against that specified contract. No blocking to the current task resulted since `schemas.py`'s response models (which the DTOs mirror) were already present and unambiguous.
- **Files modified:** `frontend/src/api/client.ts`, `frontend/src/api/types.ts`
- **Commit:** 626d8f6

No other deviations — Task 2 executed exactly as written, including the placeholder-only scope for `views/pageEditor.ts`.

## Known Stubs

- `frontend/src/views/pageEditor.ts` — intentional placeholder per Task 2's explicit instruction ("this plan owns routing and the client only... plan 02-13 replaces it wholesale"). Renders an empty container, no data wiring. Not a defect; documented in the module's own docstring.

## Verification

- `cd frontend && npx vitest run tests/client.test.ts` — 22/22 pass
- `cd frontend && npx vitest run tests/router.test.ts` — 15/15 pass
- `cd frontend && npx vitest run` (whole suite) — 133/133 pass
- `cd frontend && npm run typecheck` — exits 0
- `cd frontend && npm run build` — exits 0
- All plan-specified grep acceptance criteria confirmed manually (panels:/protected: count ≥ 2, confirmStage/goBackTargets/goBack ≥ 3 matches, touched present in types.ts, no panel_id in types.ts)

## Self-Check: PASSED

Verified files exist and commits are present (see below).
