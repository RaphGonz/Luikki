---
phase: 1
slug: foundation-project-palette-pipeline-backbone
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-10
updated: 2026-08-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` § Validation Architecture.
> Per-task map populated by the planner from the 13 `01-NN-PLAN.md` files.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest >=8.0 (existing) |
| **Config file (backend)** | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]` |
| **Framework (frontend)** | Vitest 4.1.x (new this phase, installed by plan 01-02) |
| **Config file (frontend)** | `frontend/vitest.config.ts` — created by plan 01-02 |
| **Quick run command** | `.venv/Scripts/python.exe -m pytest tests/test_store.py tests/test_masks.py tests/test_pipeline.py tests/test_extract.py -x` |
| **Quick run command (frontend)** | `npm --prefix frontend run test -- --run` |
| **Full suite command** | `.venv/Scripts/python.exe -m pytest` + `npm --prefix frontend run test -- --run` |
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

Threat refs are defined in each plan's `<threat_model>` block. Wave 0 dependencies are
satisfied by plans 01-01 (Python) and 01-02 (frontend).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01-01 | 1 | PROJ-01..05 | T-01-SC | Only registry-audited, `Approved` packages are installed | smoke | `pip install -e ".[dev,web]"` + import check | ✅ pyproject.toml | ⬜ pending |
| 01-01-T2 | 01-01 | 1 | PROJ-04, PAL-01, PAL-02 | — | — | scaffold | `pytest tests/test_pipeline.py tests/test_extract.py -q` | 🆕 created here | ⬜ pending |
| 01-01-T3 | 01-01 | 1 | PROJ-01..03, PROJ-05, PAL-02, PAL-03 | — | — | scaffold | `pytest tests/test_web -q` | 🆕 created here | ⬜ pending |
| 01-02-T1 | 01-02 | 1 | PROJ-04 | T-01-SC | Version majors asserted against live-verified numbers; lockfile committed | build | `npm --prefix frontend run build && npm --prefix frontend run typecheck` | 🆕 created here | ⬜ pending |
| 01-02-T2 | 01-02 | 1 | PROJ-04 | T-01-02 | Pure module, no DOM, no imports | unit | `npm --prefix frontend run typecheck` | 🆕 created here | ⬜ pending |
| 01-02-T3 | 01-02 | 1 | PROJ-04 | — | — | unit | `npm --prefix frontend run test -- --run` | 🆕 created here | ⬜ pending |
| 01-03-T1 | 01-03 | 1 | PROJ-01, PROJ-04 | T-01-SQLI, T-01-STATE | 100% parameterized SQL; bad states unrepresentable by schema | unit | `pytest tests/test_store.py -q` | ✅ tests/test_store.py | ⬜ pending |
| 01-03-T2 | 01-03 | 1 | PROJ-02, PROJ-04, PAL-04 | T-01-SQLI | Parameterized SQL in every added method | unit | `pytest tests/test_store.py -q` | ✅ | ⬜ pending |
| 01-03-T3 | 01-03 | 1 | PROJ-05 | T-01-DUR | WAL + busy_timeout + truncating checkpoint; synchronous commits | unit | `pytest tests/test_store.py -q` | ✅ | ⬜ pending |
| 01-04-T1 | 01-04 | 2 | PROJ-04 | T-01-INV | Fail-loud invariant assertion, not a report a caller can ignore | unit | `pytest tests/test_masks.py -q` | ✅ tests/test_masks.py | ⬜ pending |
| 01-04-T2 | 01-04 | 2 | PROJ-04 | T-01-GATE | Registry declares only; never advances a page past a gate | unit | `python -c "from comiccolor.pipeline import STAGES; ..."` | 🆕 | ⬜ pending |
| 01-04-T3 | 01-04 | 2 | PROJ-04 | T-01-STAGE | No dynamic dispatch; unknown/unimplemented stages raise | unit | `pytest tests/test_pipeline.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-05-T1 | 01-05 | 2 | PAL-01 | T-01-CONST | Thresholds are named constants flagged unvalidated | unit | `pytest tests/test_extract.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-05-T2 | 01-05 | 2 | PAL-02 | T-01-MEM | Bounded kept-pixel array; fixed K_MAX | unit | `pytest tests/test_extract.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-05-T3 | 01-05 | 2 | PAL-01, PAL-02 | T-01-IMG | Degenerate input raises `EmptyImageError`, mapped to 400 | unit | `pytest tests/test_extract.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-06-T1 | 01-06 | 3 | PROJ-01..03, PROJ-05 | T-01-INPUT | Pydantic models with enum stages, 0..255 RGB, bounded strings | unit | `python -c "from comiccolor.web import schemas; ..."` | 🆕 | ⬜ pending |
| 01-06-T2 | 01-06 | 3 | PROJ-02, PROJ-03, PROJ-05 | T-01-PATH, T-01-IMG, T-01-DB | Server-generated filenames; `verify()` before processing; per-request Store | unit | `python -c "from comiccolor.web.uploads import save_upload, decode_image; ..."` | 🆕 | ⬜ pending |
| 01-06-T3 | 01-06 | 3 | PROJ-01, PROJ-05 | T-01-DB, T-01-NET | 409 with no project open; loopback-only bind | integration | `pytest tests/test_web -q` | ✅ (Wave 0) | ⬜ pending |
| 01-07-T1 | 01-07 | 4 | PROJ-01 | T-01-OPEN, T-01-CREATE | Every client path validated before a database is opened | integration | `pytest tests/test_web/test_project_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-07-T2 | 01-07 | 4 | PROJ-01, PROJ-05 | T-01-DUR, T-01-BROWSE | Checkpoint on close; lazy tkinter with 503 fallback | integration | `pytest tests/test_web/test_project_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-07-T3 | 01-07 | 4 | PROJ-01, PROJ-05 | T-01-OPEN, T-01-DUR | Reopen-after-close and copy-the-folder both asserted | integration | `pytest tests/test_web/test_project_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-08-T1 | 01-08 | 4 | PROJ-04 | T-01-IDOR | Stage list read from the registry, never restated | integration | `pytest tests/test_web/test_page_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-08-T2 | 01-08 | 4 | PROJ-02, PROJ-04 | T-01-PATH, T-01-IMG, T-01-SERVE | UUID filenames; per-file rejection; containment-asserted file serving | integration | `pytest tests/test_web/test_page_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-08-T3 | 01-08 | 4 | PROJ-02, PROJ-04 | T-01-PATH, T-01-IMG | Traversal filename and non-image upload both asserted | integration | `pytest tests/test_web/test_page_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-09-T1 | 01-09 | 4 | PAL-03, PAL-04 | T-01-RGB, T-01-STAGE | RGB range-constrained; no pipeline import; no SQL in the router | integration | `pytest tests/test_web/test_palette_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-09-T2 | 01-09 | 4 | PAL-01 | T-01-IMG, T-01-PATH | Decode-validate before extraction; server-generated swatch filename | integration | `pytest tests/test_web/test_palette_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-09-T3 | 01-09 | 4 | PAL-01, PAL-03, PAL-04 | T-01-STAGE | Recolour asserted to leave every page stage unchanged | integration | `pytest tests/test_web/test_palette_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-10-T1 | 01-10 | 5 | PROJ-03, PAL-02 | T-01-SHEETID, T-01-PATH, T-01-IMG | 32-hex sheet-id whitelist before any path construction | integration | `pytest tests/test_web/test_palette_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-10-T2 | 01-10 | 5 | PAL-02 | T-01-EPHEM, T-01-INPUT | Client sends indices only; server re-derives colours | integration | `pytest tests/test_web/test_palette_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-10-T3 | 01-10 | 5 | PROJ-03, PAL-02 | T-01-SHEETID | Traversal sheet ids asserted to 404 with `project.db` intact | integration | `pytest tests/test_web/test_palette_routes.py -q` | ✅ (Wave 0) | ⬜ pending |
| 01-11-T1 | 01-11 | 5 | PROJ-01, PROJ-05 | T-01-ORIGIN | Same-origin relative URLs only; no configurable base | unit | `npm --prefix frontend run test -- --run` | 🆕 | ⬜ pending |
| 01-11-T2 | 01-11 | 5 | PROJ-01 | T-01-HASH, T-01-XSS | Total `parseRoute`; `textContent` only | unit | `npm --prefix frontend run test -- --run` | 🆕 | ⬜ pending |
| 01-11-T3 | 01-11 | 5 | PROJ-01, PROJ-05 | T-01-NOSAVE, T-01-STORAGE | No Save button; no browser-stored project paths | unit | `npm --prefix frontend run test -- --run` | 🆕 | ⬜ pending |
| 01-12-T1 | 01-12 | 6 | PROJ-04 | T-01-STAGEUI | `has_runner` ignored so no internal state leaks to the artist | unit | `npm --prefix frontend run test -- --run` | 🆕 | ⬜ pending |
| 01-12-T2 | 01-12 | 6 | PROJ-02 | T-01-PARTIAL, T-01-XSS, T-01-SRC | Mixed batch keeps good uploads; server-built image URLs | unit | `npm --prefix frontend run test -- --run` | 🆕 | ⬜ pending |
| 01-12-T3 | 01-12 | 6 | PROJ-04 | T-01-GOBACK | No Go-Back control ships without a computable cost sentence | build | `npm --prefix frontend run build` | 🆕 | ⬜ pending |
| 01-13-T1 | 01-13 | 6 | PAL-01, PAL-03, PAL-04 | T-01-STAGE, T-01-FLOOD, T-01-XSS | Screen never references a stage; picker commits on blur | unit | `npm --prefix frontend run test -- --run` | 🆕 | ⬜ pending |
| 01-13-T2 | 01-13 | 6 | PAL-02 | T-01-EPHEM, T-01-DESTRUCT, T-01-XSS | Indices not colours; ceremony proportional to cost | unit | `npm --prefix frontend run test -- --run` | 🆕 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Requirement → Test Map (from RESEARCH.md)

| Req ID | Behavior | Test Type | Automated Command | Owning Plans | File Exists? |
|--------|----------|-----------|-------------------|--------------|-------------|
| PROJ-01 | Create project, reopen, pages/palette/edits intact | integration | `pytest tests/test_web/test_project_routes.py -x` | 01-03, 01-06, 01-07, 01-11 | 🆕 Wave 0 (01-01) |
| PROJ-02 | Upload pages, add more over time, list preserved | integration | `pytest tests/test_web/test_page_routes.py -x` | 01-06, 01-08, 01-12 | 🆕 Wave 0 (01-01) |
| PROJ-03 | Upload character sheet as reference | integration | `pytest tests/test_web/test_palette_routes.py::test_sheet_upload_returns_unpersisted_proposals -x` | 01-06, 01-10, 01-13 | 🆕 Wave 0 (01-01) |
| PROJ-04 | See each page's stage; open any page | unit + integration | `pytest tests/test_pipeline.py -x` + `tests/test_web/test_page_routes.py::test_stage_field_is_panels_after_upload` | 01-03, 01-04, 01-08, 01-12 | 🆕 Wave 0 (01-01) |
| PROJ-05 | Refresh/crash immediately after an edit loses no work | integration + manual-UAT | `pytest tests/test_web/test_project_routes.py::test_reopen_after_close_keeps_pages_and_palette -x` | 01-03, 01-06, 01-07, 01-11 | 🆕 Wave 0 (01-01) |
| PAL-01 | Swatch upload creates named entries from chips | unit + integration | `pytest tests/test_extract.py tests/test_web/test_palette_routes.py -x` | 01-05, 01-09, 01-13 | 🆕 Wave 0 (01-01) |
| PAL-02 | Sheet proposals, accept/reject individually | unit + integration | `pytest tests/test_extract.py tests/test_web/test_palette_routes.py -x` | 01-05, 01-10, 01-13 | 🆕 Wave 0 (01-01) |
| PAL-03 | Create/rename/recolour/delete by hand | unit + integration | `pytest tests/test_store.py tests/test_web/test_palette_routes.py -x` | 01-09, 01-13 | ✅ Store layer / 🆕 routes |
| PAL-04 | Recolour propagates, no stage re-run | unit — already covered, plus route-level | `pytest tests/test_store.py::test_palette_edit_is_a_single_row_update tests/test_store.py::test_panels_affected_by_is_the_repaint_set` | 01-03, 01-09, 01-13 | ✅ exists and passes today |

---

## Wave 0 Requirements

Closed by plans 01-01 (Python) and 01-02 (frontend), both in Wave 1.

- [ ] `tests/test_pipeline.py` — 5 skip-marked stubs for PROJ-04 → filled by 01-04 (plan 01-01 T2)
- [ ] `tests/test_extract.py` — 5 skip-marked stubs for PAL-01 / PAL-02 → filled by 01-05 (plan 01-01 T2)
- [ ] `tests/test_web/__init__.py` + `conftest.py` — `project_dir`, `client`, `blank_client`, `make_png` fixtures (plan 01-01 T3; made real by 01-06 T3)
- [ ] `tests/test_web/test_project_routes.py` — 6 stubs for PROJ-01 / PROJ-05 → filled by 01-07
- [ ] `tests/test_web/test_page_routes.py` — 6 stubs for PROJ-02 / PROJ-04 → filled by 01-08
- [ ] `tests/test_web/test_palette_routes.py` — 7 stubs; 3 filled by 01-09, 4 by 01-10
- [ ] `frontend/vitest.config.ts` + `frontend/package.json` `"test": "vitest"` script (plan 01-02 T1)
- [ ] `npm install --save-dev vitest@^4.1` inside `frontend/` (plan 01-02 T1)
- [ ] `frontend/tests/transform.test.ts` — delivered as a **complete** suite rather than a stub, since the module it covers has no dependencies (plan 01-02 T3)

**Stub convention:** every stub is `@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-NN")`
with all `comiccolor.*` imports inside the function body, so `pytest --collect-only` never fails
on a module that does not exist yet. Each implementation plan removes its own skip markers.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions | Plan carrying the `<human-check>` |
|----------|-------------|------------|-------------------|-----------------------------------|
| True crash (process kill) mid-write loses no work | PROJ-05 | A literal process kill mid-write is not reliably scriptable; the automated test covers close-and-reopen without a clean shutdown | Make an edit, kill the server process without shutdown, restart, confirm the edit is present | 01-07 |
| A copied project folder is complete | PROJ-01, D-04 | Verifies the WAL checkpoint in the real supervised-session workflow | Create, edit, close, quit, copy the folder elsewhere, reopen from the copy | 01-07 |
| Real studio page and real broken file upload behaviour | PROJ-02 | Real-world files (large TIFFs, half-downloaded JPEGs) are the failure mode Pitfall 4 exists for | Drop both; confirm the good page appears and the bad one shows the exact error copy | 01-08 |
| Swatch exactness and recolour non-event | PAL-01, PAL-04, D-09 | Colour judgement by eye against the artist's own artwork | Drop a real swatch; recolour an entry; confirm the toast and the absence of any dialog or stage change | 01-09, 01-13 |
| Character-sheet proposal quality | PAL-02, D-14 | The ink/paper thresholds are unvalidated starting values (Assumptions Log A1) needing real sheets to tune | Drop a real character sheet; confirm proposals are the character's colours, not paper and ink | 01-10, 01-13 |
| Visual conformance to UI-SPEC tokens, copy, and interaction states | PROJ-01..05, PAL-01..04 | Colour values, spacing, and stage-strip visual states are human-judged against the design contract | Walk UI-SPEC.md's Checker Sign-Off table against the running app | 01-11, 01-12, 01-13 |

`workflow.human_verify_mode` is `end-of-phase`, so these are `<verify><human-check>` blocks
inside the plans rather than blocking `checkpoint:human-verify` tasks.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — 38/38 tasks carry an `<automated>` command
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references — plans 01-01 and 01-02, both Wave 1
- [x] No watch-mode flags — every frontend command is `npm --prefix frontend run test -- --run`; `test:watch` exists as a separate explicit opt-in
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-populated 2026-08-10 — pending execution
