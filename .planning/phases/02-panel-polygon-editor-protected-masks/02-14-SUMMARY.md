---
phase: 02-panel-polygon-editor-protected-masks
plan: 14
subsystem: frontend-editor
tags: [typescript, dialog, go-back, vitest, jsdom, tdd]

# Dependency graph
requires:
  - phase: 02-11
    provides: "POST /stage/confirm, GET /stage/go-back-targets, POST /stage/go-back routes and _go_back_targets(store, page)"
  - phase: 02-13
    provides: "renderPageEditor, the toolbar's documented Go-Back-link no-op seam, the gate-confirm state-application path this plan's Go-Back handler mirrors"
provides:
  - "frontend/src/components/goBackDialog.ts -- openGoBackDialog(mount, targets, onConfirm): () => void, the standing destructive-confirmation dialog 01-UI-SPEC.md §3 specified and left unreachable"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "The dialog holds no copy of its own -- every visible string (heading, body, confirm label, cancel label) is set via textContent directly from the server's GoBackTargetDto, with no template string, pluralisation logic or default copy anywhere in the component (grep-asserted absent: 'This discards', 'Go back and discard', 'Stay on')."
    - "The Go-Back link always re-fetches goBackTargets fresh on click before opening the dialog (01-UI-SPEC.md §3's 'computed at the moment the dialog opens' rule), separately from a lighter-weight refresh at boot and after every gate confirm that only decides the link's hidden state."
    - "A successful Go-Back reuses the exact state-application shape the gate-confirm handler already uses (reload both shape lists from the server, clear both undo stacks, re-derive active layer and read-only state) rather than writing a second path, per this plan's own action text."

key-files:
  created:
    - frontend/src/components/goBackDialog.ts
    - frontend/src/styles/dialog.css
    - frontend/tests/goBackDialog.test.ts
  modified:
    - frontend/src/views/pageEditor.ts

key-decisions:
  - "The confirm callback passed to openGoBackDialog rethrows on failure after reporting the error via the existing toast path, so the dialog's own catch handler (re-enable the confirm button, keep the dialog open) is the single place that decides what a failed Go-Back looks like to the artist -- they can retry without losing their place."
  - "Both panel and protected shape lists are reloaded from the server on every successful Go-Back, not just the target stage's own list -- a Go-Back to Import discards both panels and protected masks in one transition, and the server response is the only source of truth for what remains in either list."

requirements-completed: [PAN-01, PAN-02, PAN-03, PROT-01, PROT-02, PROT-03, PROT-04]

# Metrics
duration: 55min
completed: 2026-08-16
---

# Phase 2 Plan 14: The Go-Back Dialog and Its Wiring Summary

**`openGoBackDialog` ships the destructive-confirmation modal Phase 1 specified in 01-UI-SPEC.md §3 and deliberately left unreachable; the editor toolbar's documented no-op Go-Back link now opens it with live server-computed targets, and a successful confirm returns the artist to a genuinely editable earlier stage via the same state-application path the gate-confirm handler already uses.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 2 auto (Task 1 TDD), 1 checkpoint (this summary records the automated half; human verification is outstanding — see below)
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments

- `frontend/src/components/goBackDialog.ts` (154 lines) — `openGoBackDialog(mount, targets, onConfirm): () => void`.
  - Zero targets renders nothing and returns a no-op teardown.
  - One target renders heading/body/confirm/cancel as exact `textContent` from `GoBackTargetDto`; no target-list markup.
  - Two-or-more targets render a `role="radiogroup"` list of `display_name`-labelled buttons; selecting a target re-renders the heading/body/confirm/cancel to that target's own strings.
  - Focus lands on the cancel button on open (T-2-44); `Escape` and the cancel button both dismiss without calling `onConfirm`; the confirm button carries `destructive`, the cancel button does not.
  - Confirm disables synchronously on click, before any `await`, so a double-click calls `onConfirm` exactly once (T-2-42) — verified with a pending-promise test that asserts the call count before resolving.
  - On `onConfirm` rejection, the dialog re-enables its confirm button and stays open rather than silently closing on a failed destructive action.
  - Docstring states the component's correctness rule and that it is intentionally generic — Phases 3–7 reuse it rather than writing their own.
- `frontend/src/styles/dialog.css` (94 lines) — scrim + centred `--color-surface-secondary` panel at z-index 100, target-list, body, actions, cancel and `destructive` confirm button styling. Tokens only, no colour literal.
- `frontend/tests/goBackDialog.test.ts` (194 lines, `@vitest-environment jsdom` first line) — 13 tests covering all seven `<behavior>` clauses: empty-list no-op, verbatim copy for one target, no target-list markup for one target, destructive/non-destructive button classes, focus-on-open, Escape dismiss, cancel dismiss, exactly-once confirm on double-click, re-open-on-failure, multi-target list rendering and labelling, selection changing the rendered sentence, and confirming the currently-selected (not first) target.
- `frontend/src/views/pageEditor.ts` — replaced the documented no-op Go-Back click handler:
  - `refreshGoBackTargets()` fetches `api.pages.goBackTargets(pageId)` and sets `goBackLink.hidden` from the result's emptiness; called once at the end of `boot()` (non-blocking) and again after every successful gate confirm (both the Panels→Protected and Protected→Done branches).
  - The link's click handler re-fetches targets fresh (rather than reusing the cached list) before opening `openGoBackDialog`, honouring 01-UI-SPEC.md §3's "computed from real data at the moment the dialog opens" rule; an empty fresh result opens nothing.
  - `handleGoBackConfirm(stage)` calls `api.pages.goBack(pageId, stage)`, then reloads both `api.panels.list` and `api.protected.list` from the server, clears both undo stacks (documented: their queued ops reference row ids a Go-Back just deleted, so replaying an inverse would 404 — UI-SPEC §6's tool-mode-session scoping applied to this trigger), and re-derives `activeTool`/`setReadOnly` for both layers exactly as `boot()` does, so the stage being returned to becomes editable again.
  - The dialog is mounted into a dedicated `dialogMount` div appended to `root`, so `teardown()` removing `root` also removes any dialog left open; `dismissGoBackDialog` is additionally called explicitly in `teardown()` to detach its `Escape` listener before that.

## Task Commits

Each task was committed atomically, following the TDD gate sequence for Task 1:

1. **Task 1 RED** — `test(02-14): add failing test for the Go-Back destructive-confirmation dialog` (`ab50f03`) — 13 tests against a not-yet-existing module; confirmed failing via unresolved import, not a false-positive pass.
2. **Task 1 GREEN** — `feat(02-14): the Go-Back destructive-confirmation dialog` (`14a5e28`) — `goBackDialog.ts` + `dialog.css`; all 13 tests pass. No REFACTOR commit needed — the GREEN implementation needed no cleanup pass.
3. **Task 2** — `feat(02-14): wire Go-Back into the editor toolbar` (`ee5488a`) — `pageEditor.ts` wiring.

**Plan metadata:** this commit (docs: complete plan) — not yet made; pending the checkpoint below.

## Files Created/Modified

- `frontend/src/components/goBackDialog.ts` (new)
- `frontend/src/styles/dialog.css` (new)
- `frontend/tests/goBackDialog.test.ts` (new)
- `frontend/src/views/pageEditor.ts` (modified)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] The literal acceptance-criteria grep for `innerHTML` matched the component's own docstring**
- **Found during:** Task 1, verifying acceptance criteria after the GREEN commit.
- **Issue:** The docstring's XSS-control sentence originally read `` `innerHTML` is never used`` — the plan's acceptance criterion `grep -n "innerHTML" frontend/src/components/goBackDialog.ts` returns no matches would fail on this literal substring even though no `innerHTML` assignment exists in the file.
- **Fix:** Reworded to "raw-markup insertion is never used", preserving the same meaning without the literal grep-matched string.
- **Files modified:** `frontend/src/components/goBackDialog.ts`
- **Commit:** `14a5e28` (amended before commit, not a separate commit)

**2. [Rule 1 - Bug] The initial target-list implementation rendered hidden markup instead of omitting it**
- **Found during:** Task 1, first test run — "does not render a target list for a single target" failed because the list `<div>` was appended with `hidden` set rather than left out of the DOM.
- **Fix:** The target list is now only appended to the panel when `targets.length > 1`, matching the acceptance criteria's literal DOM-absence check.
- **Files modified:** `frontend/src/components/goBackDialog.ts`
- **Commit:** `14a5e28`

None beyond the above two, both found and fixed before the GREEN commit.

## Known Stubs

None. The dialog and its wiring are both fully live — no placeholder handlers remain on the Go-Back link.

## Threat Flags

None beyond what this plan's own `<threat_model>` already named and this implementation satisfies: T-2-41 (no copy of its own to tamper with — grep-asserted), T-2-08 (only `GoBackTargetDto` fields reach the DOM), T-2-09 (`textContent` only, no raw-markup insertion), T-2-42 (double-click guard, tested with a pending-promise), T-2-43 (both undo stacks cleared on a successful Go-Back), T-2-44 (focus on cancel, destructive-coloured confirm labelled with the concrete verb and cost).

## Verification

- `cd frontend && npm run test -- goBackDialog` — 13/13 passed.
- `cd frontend && npm run test` — 154/154 passed (15 test files), full suite green.
- `cd frontend && npm run typecheck` — exits 0.
- `cd frontend && npm run build` — exits 0 (53.61 kB JS / 22.45 kB CSS gzipped to 15.22 kB / 3.36 kB).
- `python -m pytest tests/ -q` — 236 passed, 2 xfailed (pre-existing, unrelated to this plan — the bare `pytest`/`comiccolor` executables on this machine's PATH resolve to a stale editable install pointing at a deleted worktree path from a prior parallel-agent session; invoking via `python -m pytest` / `.venv/Scripts/comiccolor.exe` from this repo resolves correctly and is what was used throughout this plan's verification and for starting the server below).
- `grep -n "innerHTML" frontend/src/components/goBackDialog.ts` — no matches.
- `grep -nE "This discards|Go back and discard|Stay on" frontend/src/components/goBackDialog.ts` — no matches.
- `grep -n "openGoBackDialog\|goBackTargets\|api.pages.goBack" frontend/src/views/pageEditor.ts` — 4 matches.
- `grep -n "clearStack" frontend/src/views/pageEditor.ts` — present in the tool-mode-switch, gate-confirm, and Go-Back-success handlers (6 occurrences across those three call sites).
- `.venv/Scripts/comiccolor.exe serve --host 127.0.0.1 --port 8000` starts cleanly (`Application startup complete`, `GET / HTTP/1.1 200 OK`) — left running in the background at `http://127.0.0.1:8000` for the human verification steps below, so no CLI command is required of the developer.

## Issues Encountered

**Environment note (not a plan defect):** the `comiccolor` and `pytest` executables on this machine's global `PATH` are stale — `pip show -f comiccolor` reports an editable install pointing at `C:\Users\raphg\Desktop\ComicColor\.claude\worktrees\agent-aa7cd80aa590145b5`, a worktree directory that no longer exists (left over from a prior parallel-agent session). Both were invoked via the repo's own `.venv` (`.venv/Scripts/comiccolor.exe`, `python -m pytest`) instead, which resolves against this checkout correctly. Flagging this so it doesn't cause confusion in a future session — `pip install -e .` from this repo root with the correct venv active would refresh the stale pointer, but that's outside this plan's file list and not attempted here.

## User Setup Required

None for the automated portion. The server is already running in the background at `http://127.0.0.1:8000` for the checkpoint below.

## Human Verification — Outstanding (Task 3, checkpoint:human-verify)

Both full suites are green and the server is confirmed starting cleanly (see Verification above). The following four sections from the plan's `<how-to-verify>` are **not yet checked** — they require a real browser and real ink, which no automated test in this repository can substitute for (02-VALIDATION.md's Manual-Only Verifications table). Nothing below has been performed by the executor.

**A. Real-page detection quality (PAN-01, PROT-01, D-18)** — upload a real ink page (ideally with a borderless "case sans bordure" panel), open it at `#/page/{id}/edit`, confirm panels appear as numbered polygons in reading order and the borderless panel is proposed (over-proposal acceptable, D-18); delete any false proposals with a single click and confirm no dialog appears (D-19).

**B. Zoom-invariance (success criterion 2)** — at ~100% zoom, drag one vertex to a distinctive spot; zoom to ~800% and confirm it held; reverse the order (drag at 800%, confirm it held at fit-to-screen); repeat once on a non-1 `devicePixelRatio` display if available.

**C. Boundary-crossing protection (PROT-04, success criterion 4)** — confirm the Panels gate; confirm bubbles are proposed or the failure banner appears; find or create art/SFX crossing a panel boundary; draw a protected SFX mask spanning both panels; confirm it renders as one continuous overlay, never split at the boundary; reshape a vertex and confirm dashed→solid; confirm the Protected gate; confirm the protected region is excluded from segmentation output on both panels.

**D. Go-Back (D-08)** — use the Go-Back link to return from Protected to Panels; confirm the dialog states the exact number of masks it will discard, matching what was actually drawn; confirm discarding removes all of them including the hand-drawn SFX mask; confirm panel polygons are editable again afterward.

**Result:** not recorded — awaiting the developer's own observations per section, verbatim, as required by this task's acceptance criteria. This summary will need a follow-up update (or the developer's own note) once verification is complete; the phase should not be marked complete until sections A–D are recorded here.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16 (automated portion only — human checkpoint outstanding)*

## Self-Check: PASSED
