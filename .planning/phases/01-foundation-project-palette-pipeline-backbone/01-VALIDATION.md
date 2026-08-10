---
phase: 1
slug: foundation-project-palette-pipeline-backbone
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest >=8.0 (existing) |
| **Config file (backend)** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]` |
| **Framework (frontend)** | Vitest 4.1.x (new this phase) |
| **Config file (frontend)** | `frontend/vitest.config.ts` — none yet, Wave 0 |
| **Quick run command** | `pytest tests/test_store.py tests/test_masks.py tests/test_pipeline.py tests/test_extract.py -x` |
| **Quick run command (frontend)** | `npm --prefix frontend run test -- --run` |
| **Full suite command** | `pytest` + `npm --prefix frontend run test -- --run` |
| **Integration test client** | `fastapi.testclient.TestClient` (httpx-backed) — no uvicorn process needed |
| **Estimated runtime** | ~20 seconds (backend), ~10 seconds (frontend) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command for the side touched (backend and/or frontend)
- **After every plan wave:** Run the full suite; for UI-touching waves, one manual pass against UI-SPEC's Checker Sign-Off table
- **Before `/gsd-verify-work`:** Full suite must be green, and the PROJ-05 manual crash-scenario check run at least once
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Populated by the planner — one row per task in `*-PLAN.md`. Requirement column
> must draw from PROJ-01..05 / PAL-01..04; every task either has an automated
> command or an explicit Wave 0 dependency.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _pending planner_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Requirement → Test Map (from RESEARCH.md)

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROJ-01 | Create project, reopen, pages/palette/edits intact | integration | `pytest tests/test_web/test_project_routes.py -x` | ❌ Wave 0 |
| PROJ-02 | Upload pages, add more over time, list preserved | integration | `pytest tests/test_web/test_page_routes.py -x` | ❌ Wave 0 |
| PROJ-03 | Upload character sheet as reference | integration | `pytest tests/test_web/test_palette_routes.py::test_sheet_upload -x` | ❌ Wave 0 |
| PROJ-04 | See each page's stage; open any page | unit + integration | `pytest tests/test_pipeline.py -x` + `tests/test_web/test_page_routes.py::test_stage_field` | ❌ Wave 0 |
| PROJ-05 | Refresh/crash immediately after an edit loses no work | integration + manual-UAT | `pytest tests/test_web/test_project_routes.py::test_reopen_after_close -x` | ❌ Wave 0 |
| PAL-01 | Swatch upload creates named entries from chips | unit | `pytest tests/test_extract.py -x` | ❌ Wave 0 |
| PAL-02 | Sheet proposals, accept/reject individually | unit + integration | `pytest tests/test_extract.py tests/test_web/test_palette_routes.py -x` | ❌ Wave 0 |
| PAL-03 | Create/rename/recolour/delete by hand | unit + integration | `pytest tests/test_store.py tests/test_web/test_palette_routes.py -x` | ✅ Store layer / ❌ routes |
| PAL-04 | Recolour propagates, no stage re-run | unit — already covered | `pytest tests/test_store.py::test_palette_edit_is_a_single_row_update tests/test_store.py::test_panels_affected_by_is_the_repaint_set` | ✅ exists and passes today |

---

## Wave 0 Requirements

- [ ] `tests/test_pipeline.py` — stubs for PROJ-04 (STAGES shape, `page.stage` transitions)
- [ ] `tests/test_extract.py` — stubs for PAL-01 / PAL-02 (quantize+merge, sheet pre-pass, adaptive count)
- [ ] `tests/test_web/__init__.py` + `conftest.py` — shared `TestClient` and temp-project fixtures
- [ ] `tests/test_web/test_project_routes.py` — stubs for PROJ-01 / PROJ-05
- [ ] `tests/test_web/test_page_routes.py` — stubs for PROJ-02 / PROJ-04
- [ ] `tests/test_web/test_palette_routes.py` — stubs for PROJ-03 / PAL-02 / PAL-03
- [ ] `frontend/vitest.config.ts` + `frontend/package.json` `"test": "vitest"` script — greenfield, none exists
- [ ] `npm install --save-dev vitest@^4.1` inside `frontend/` — framework install
- [ ] `frontend/tests/transform.test.ts` — stubs for the screen↔label-map coordinate transform

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| True crash (process kill) mid-write loses no work | PROJ-05 | A literal process kill mid-write is not reliably scriptable; the automated test covers "close and reopen without clean shutdown", which proves the persistence discipline but not the crash itself | Make an edit, kill the server process without shutdown, restart, confirm the edit is present |
| Visual conformance to UI-SPEC tokens, copy, and interaction states | PROJ-01..05, PAL-01..04 | Colour values, spacing, and stage-strip visual states are human-judged against the design contract, not assertable in pytest/Vitest | Walk UI-SPEC.md's Checker Sign-Off table against the running app |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags (`vitest --run`, never bare `vitest`)
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
