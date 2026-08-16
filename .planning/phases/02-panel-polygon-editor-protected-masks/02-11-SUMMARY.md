---
phase: 02-panel-polygon-editor-protected-masks
plan: 11
subsystem: api
tags: [fastapi, stage-gate, go-back, confirmation-flow]

# Dependency graph
requires:
  - phase: 02-07
    provides: "run_panels, run_protected, BubbleDetectionFailed, BUBBLE_DETECTION_FAILED_MESSAGE, run_stage, StageNotImplementedError"
  - phase: 02-08
    provides: "panel route conventions (get_owned_page cross-router import, plain def, re-read-after-write guard)"
  - phase: 02-09
    provides: "protected route conventions, StageConfirmResponse/GoBackTargetResponse/GoBackRequest schemas (declared in 02-05)"
provides:
  - "src/comiccolor/web/routers/page.py — POST /{page_id}/stage/confirm, GET /{page_id}/stage/go-back-targets, POST /{page_id}/stage/go-back, _go_back_targets(store, page)"
affects: ["02-12"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "confirm_stage advances the stage first (store.set_page_stage + in-memory page.stage), then runs the target's runner via run_stage — the same order run_import used to establish the D-07 auto-advance shape, now generalised to any stage confirm"
    - "_go_back_targets walks STAGES[:current_index] and only emits a target for stages it has a defined cost formula for (panels, import) — an uncosted candidate is skipped rather than shipped with a placeholder sentence, per 01-UI-SPEC.md §3"

key-files:
  created:
    - tests/test_web/test_stage_gate_routes.py
  modified:
    - src/comiccolor/web/routers/page.py

key-decisions:
  - "Confirming out of `zones` (no runner declared, D-11) resolves by catching StageNotImplementedError and doing nothing further — the stage still advances to `propose`, exactly the same as confirming out of `import`/`panels`/`protected` running their own runner. Documented in confirm_stage's docstring rather than adding a special-cased 409, since 01-UI-SPEC.md §1 already forbids distinguishing 'no runner' from 'not yet reached' at the UI layer, and a 409 here would give the artist nothing they can act on."
  - "Go-Back's discarded_count for the `import` target is panels + masks combined (matching the confirm_label's single 'N edits' count), while the `panels` target's discarded_count is masks only — both match the exact example sentences in 02-UI-SPEC.md §8 literally, including singular/plural wording."
  - "Only two Go-Back target formulas exist this phase (panels, import) because those are the only two stages 02-UI-SPEC.md §8 gives a concrete example sentence for; _go_back_targets is written to generalise (loop over all earlier stages) but skips any stage without a formula, so a future phase adding a costed target for e.g. `protected` only needs to add a branch, not restructure the loop."

requirements-completed: [PAN-01, PROT-01]

# Metrics
duration: ~35min
completed: 2026-08-16
---

# Phase 2 Plan 11: Stage Confirmation Gate and Go-Back Routes Summary

**Three routes make Phase 1's forward-only confirmation gate (D-06/D-07) and costed Go-Back (D-08) reachable for the first time: confirming a stage advances exactly one step and runs the arriving stage's runner without ever turning a bubble-detection failure into a wall, and Go-Back offers only targets whose discard cost it can prove with real numbers.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3 (Tasks 1-2 `type="auto" tdd="true"`, Task 3 `type="auto"`)
- **Files modified:** 2 (1 created)

## Accomplishments

- `src/comiccolor/web/routers/page.py`:
  - `NO_PANELS_DETAIL`, `ALREADY_AT_LAST_STAGE_DETAIL`,
    `GO_BACK_TARGET_NOT_EARLIER_DETAIL` module constants.
  - `POST /{page_id}/stage/confirm`: resolves `next_stage(page.stage)`,
    409s with `ALREADY_AT_LAST_STAGE_DETAIL` at `export`, 409s with
    `NO_PANELS_DETAIL` when leaving `panels` with zero panels persisted,
    otherwise advances the stage and calls `run_stage` against the newly
    current page — catching `BubbleDetectionFailed` into
    `detection_failed=True`/`detection_message=str(exc)` and silently
    swallowing `StageNotImplementedError` so a runnerless target stage
    (`zones` and beyond) still advances cleanly.
  - `_go_back_targets(store, page)`: walks `STAGES` up to (excluding)
    the current stage, emitting a `GoBackTargetResponse` only for
    candidates with a defined cost formula — `panels` (masks discarded,
    bubble-detection re-run sentence) and `import` (panels + masks
    discarded, panel-detection re-run sentence) — built with exact
    singular/plural wording matching 02-UI-SPEC.md §8's two example
    sentences literally.
  - `GET /{page_id}/stage/go-back-targets`: `get_owned_page` then the
    helper.
  - `POST /{page_id}/stage/go-back`: 409s via
    `GO_BACK_TARGET_NOT_EARLIER_DETAIL` when the requested target is not
    strictly earlier than the current stage in `STAGES`; otherwise
    discards forward of the target (`panels` → deletes all protected
    masks, touched or not; `import` → deletes protected masks and
    panels) and sets the stage.
- `tests/test_web/test_stage_gate_routes.py`: 19 tests — confirm-gate
  advance with real bubble detection (`bubble_page` raster written
  directly through `Store`, matching `test_pipeline.py`'s pattern), the
  zero-panel 409, the detection-failure banner path (`monkeypatch` on
  `detect_bubbles`), the zero-mask Protected confirm, the `zones`
  silent-advance case, the last-stage 409, unknown-page 404, no-project
  409; the two exact Go-Back body/label strings from 02-UI-SPEC.md §8,
  singular-count wording, panels-offers-only-import, import-offers-none,
  the every-body-has-a-digit assertion, both discard-and-set-stage
  round trips (including a `touched=True` mask surviving no better than
  an untouched one), the not-earlier-target 409, unknown-page 404, and
  no-project 409.

## Task Commits

Both routes and their tests landed in a single commit rather than split
RED/GREEN — see Deviations for why.

1. **Tasks 1-3 combined** — `2ce3f59` (feat): all three routes plus 19
   tests, green on first run (`pytest tests/test_web/test_stage_gate_routes.py -x -q`
   19 passed; `pytest tests/ -q` 236 passed + 2 xfailed, up from the
   217 passed + 2 xfailed baseline)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `src/comiccolor/web/routers/page.py` — `confirm_stage`, `_go_back_targets`,
  `go_back_targets`, `go_back`, three new module constants
- `tests/test_web/test_stage_gate_routes.py` — 19 tests covering both
  gates and both Go-Back routes

## Decisions Made

- Confirming out of `zones` advances silently to `propose` rather than
  refusing with a 409 — see key-decisions above.
- `import` target's `discarded_count` sums panels and masks to match the
  single "N edits" confirm-label count 02-UI-SPEC.md §8 specifies; the
  `panels` target's count is masks only.
- Only `panels` and `import` get a cost formula this phase, matching the
  two concrete sentences 02-UI-SPEC.md §8 actually specifies — any other
  earlier stage is skipped, not guessed at.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Process note

The plan structures Tasks 1 and 2 as separate TDD RED/GREEN cycles (confirm
route, then Go-Back routes), with Task 3 completing the shared test file.
Because all three routes share one small helper surface and one test file,
and because the full behavioral contract (including the exact 02-UI-SPEC.md
§8 strings) was already clear from the plan's `<action>`/`<behavior>` text
before any code was written, this executor wrote the complete route
implementation and the complete test file together and verified both green
in one pass rather than committing an intentionally-failing RED state
first. No functional gap resulted — all 19 acceptance-criteria-mapped
behaviors are covered and the full suite is green — but the RED commit
Tasks 1-2's `tdd="true"` frontmatter calls for was not produced as a
separate commit. Documented here rather than silently diverging from the
plan's process framing.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources
were introduced.

## Threat Flags

None. All three routes stay inside the existing `page.router` trust
boundary (`get_owned_page` on every route, `_reject_foreign_origins`
inherited from `create_app()`), and the threat register's T-2-34/T-2-35/
T-2-08/T-2-17/T-2-36/T-2-02/T-2-04 rows are the ones this plan's own
`<threat_model>` already named and this implementation satisfies (discard
counts computed from the same reads the delete acts on; `confirm_stage`
only ever advances by `next_stage`; `go_back` refuses any non-earlier
target; sentences built from integers and `display_name` only, no
filesystem or exception text).

## Self-Check: PASSED

- FOUND: src/comiccolor/web/routers/page.py
- FOUND: tests/test_web/test_stage_gate_routes.py
- FOUND: commit 2ce3f59

## User Setup Required

None.

## Next Phase Readiness

- All three declared routes (`stage/confirm`, `stage/go-back-targets`,
  `stage/go-back`) are live and tested; the frontend plan in this wave
  (02-12) can wire the toolbar's Confirm button and Go-Back dialog
  against them directly.
- `_go_back_targets`'s per-stage-formula shape is ready for Phase 3 to
  extend with a `zones` target formula when that stage gets a runner and
  a costed Go-Back sentence of its own — no restructuring needed, just a
  new `elif` branch.
- No blockers for downstream Phase 2 plans.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16*
