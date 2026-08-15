---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 01
subsystem: testing
tags: [pytest, fastapi, scikit-image, httpx, dependency-management, test-scaffolding]

# Dependency graph
requires: []
provides:
  - "pyproject.toml with scikit-image declared, a `web` optional-dependency extra (fastapi, uvicorn, python-multipart), and httpx added to `dev`"
  - "tests/test_pipeline.py — 5 skip-marked stubs for the D-06/D-07/D-10/D-11 stage-chain contract"
  - "tests/test_extract.py — 5 skip-marked stubs for the D-12..D-15 palette extraction contract"
  - "tests/test_web/ package with conftest.py (project_dir, client, blank_client, make_png fixtures) and 19 skip-marked route stubs across test_project_routes.py, test_page_routes.py, test_palette_routes.py"
affects: ["01-04", "01-05", "01-06", "01-07", "01-08", "01-09", "01-10"]

# Tech tracking
tech-stack:
  added: ["fastapi>=0.141", "uvicorn[standard]>=0.52", "python-multipart>=0.0.32", "scikit-image>=0.26", "httpx>=0.28 (dev)"]
  patterns:
    - "Skip-marked test stubs with function-local comiccolor.* imports, so pytest --collect-only never fails on modules that don't exist yet"
    - "Factory fixture (make_png) returning a callable, for building in-memory multipart upload payloads"

key-files:
  created:
    - tests/test_pipeline.py
    - tests/test_extract.py
    - tests/test_web/__init__.py
    - tests/test_web/conftest.py
    - tests/test_web/test_project_routes.py
    - tests/test_web/test_page_routes.py
    - tests/test_web/test_palette_routes.py
  modified:
    - pyproject.toml

key-decisions:
  - "Followed 01-VALIDATION.md's Wave 0 Requirements plan-number mapping over 01-01-PLAN.md's Task 3 action text, which was off by one plan (see Deviations)."

patterns-established:
  - "Wave 0 stub convention: @pytest.mark.skip(reason=\"Wave 0 scaffold — filled by plan 01-NN\"), real docstring, `...` body, comiccolor.* imports inside the function/fixture body only."

requirements-completed: [PROJ-01, PROJ-02, PROJ-03, PROJ-04, PROJ-05, PAL-01, PAL-02, PAL-03]

# Metrics
duration: 20min
completed: 2026-08-15
---

# Phase 1 Plan 1: Dependency Declarations and Wave 0 Test Scaffolding Summary

**Declared scikit-image/fastapi/uvicorn/python-multipart/httpx in pyproject.toml and scaffolded 29 skip-marked stub tests (pipeline, extraction, three web route files) plus the shared TestClient/PNG fixtures every later Phase 1 plan fills in.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-08-15T17:25:00+02:00 (approx)
- **Completed:** 2026-08-15T17:37:36+02:00
- **Tasks:** 3
- **Files modified:** 8 (1 modified, 7 created)

## Accomplishments
- `pyproject.toml` now declares `scikit-image>=0.26` as a core dependency (settling the undeclared-transitive-import debt RESEARCH.md's Runtime State Inventory flagged), a `web` extra (`fastapi>=0.141`, `uvicorn[standard]>=0.52`, `python-multipart>=0.0.32`), and `httpx>=0.28` in `dev`.
- Installed into the shared project venv (`.venv`) with `pip install -e ".[dev,web]"`; confirmed FastAPI 0.141.1 with `app.frontend()` available (`hasattr(FastAPI(), "frontend")` is `True`), so plan 01-06 can use the new SPA-serving API directly instead of the `StaticFiles(html=True)` fallback.
- `tests/test_pipeline.py` and `tests/test_extract.py` scaffolded with 5 skip-marked stubs each, citing D-06/D-07/D-10/D-11 and D-12..D-15 respectively.
- `tests/test_web/` package scaffolded: `conftest.py` with four working fixtures (`project_dir`, `client`, `blank_client`, `make_png`), plus 19 skip-marked stubs across `test_project_routes.py` (6), `test_page_routes.py` (6), `test_palette_routes.py` (7).
- Full suite: `pytest -q` exits 0 with 38 passed, 29 skipped (10 pipeline/extract + 19 web), 2 xfailed. `pytest --collect-only -q` collects 69 tests with zero `ImportError`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Declare the phase's Python dependencies** - `fd8fca6` (feat)
2. **Task 2: Scaffold the pipeline and extraction test modules** - `1cac320` (test)
3. **Task 3: Scaffold the web route test package and its shared fixtures** - `c2be4f2` (test)

**Plan metadata:** pending (this commit, docs: complete plan)

## Files Created/Modified
- `pyproject.toml` - added scikit-image core dep, `web` extra, extended `dev` extra with httpx
- `tests/test_pipeline.py` - 5 skip-marked stubs for the stage-chain contract (filled by 01-04)
- `tests/test_extract.py` - 5 skip-marked stubs for the palette extraction contract (filled by 01-05)
- `tests/test_web/__init__.py` - empty package marker
- `tests/test_web/conftest.py` - `project_dir`, `client`, `blank_client`, `make_png` fixtures; `comiccolor.web` imports deferred to fixture bodies
- `tests/test_web/test_project_routes.py` - 6 skip-marked stubs for PROJ-01/PROJ-05 (filled by 01-07)
- `tests/test_web/test_page_routes.py` - 6 skip-marked stubs for PROJ-02/PROJ-04 (filled by 01-08)
- `tests/test_web/test_palette_routes.py` - 7 skip-marked stubs: 3 for PAL-01/PAL-03/PAL-04 (filled by 01-09), 4 for PROJ-03/PAL-02 (filled by 01-10)

## Decisions Made
- Used the VALIDATION.md-consistent plan numbers in every skip-reason string (01-07/01-08/01-09/01-10) rather than 01-01-PLAN.md's Task 3 action text (01-06/01-07/01-08/01-09) — see Deviations below for why.
- `make_png`'s chip layout tiles colours into a roughly-square grid (`ceil(sqrt(n))` columns) rather than a fixed 2x2/1xN shape, so it works for any `len(colours)` future plans pass in, not just the 4-chip case RESEARCH.md's worked example uses.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the plan-number mapping in Wave 0 stub skip-reasons**
- **Found during:** Task 3 (scaffolding `tests/test_web/*`)
- **Issue:** 01-01-PLAN.md's Task 3 action text says `test_project_routes.py` stubs are "filled by plan 01-06," `test_page_routes.py` by "01-07," and `test_palette_routes.py` by "01-08"/"01-09" — each one plan off from the actual owning plan. Cross-checked against 01-VALIDATION.md's Wave 0 Requirements section (`filled by 01-07` / `01-08` / `01-09` + `01-10`) and the `files_modified`/`must_haves.artifacts` frontmatter of plans 01-06 through 01-10 themselves: 01-06 only builds `create_app`/`deps`/`schemas`/routers scaffolding and makes the fixtures real (its `must_haves` never mentions unskipping a stub), while 01-07's `must_haves.artifacts` explicitly says `tests/test_web/test_project_routes.py` provides "PROJ-01 and PROJ-05 route coverage (6 stubs from plan 01-01 filled in)," 01-09's says "3 of the 7 stubs from plan 01-01 filled in," and 01-10's says "the 4 remaining stubs." VALIDATION.md and the downstream plans' own frontmatter agree with each other and disagree with 01-01-PLAN.md's prose.
- **Fix:** Wrote skip-reason strings using the VALIDATION.md/downstream-plan-consistent numbers (01-07 for project routes, 01-08 for page routes, 01-09/01-10 split for palette routes) so 01-VALIDATION.md's Wave 0 Requirements checklist and every later plan's own frontmatter stay reconcilable with what actually ships in `tests/test_web/`.
- **Files modified:** `tests/test_web/test_project_routes.py`, `tests/test_web/test_page_routes.py`, `tests/test_web/test_palette_routes.py`
- **Verification:** Read frontmatter (`files_modified`, `must_haves.artifacts`) of 01-06 through 01-10-PLAN.md directly; all four downstream plans corroborate the VALIDATION.md numbering.
- **Committed in:** c2be4f2 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Corrects a documentation inconsistency between two authored planning artifacts before it could propagate into skip-reason strings that later plans grep for. No scope creep; no behavior change to test outcomes (all 29 new tests still skip and collect identically either way).

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required. The new `web` and `dev` extras were installed directly into the existing project venv (`.venv`) as part of Task 1's automated verification.

## Next Phase Readiness
- `pytest --collect-only -q` passes with zero `ImportError` across the whole `tests/` tree — every later plan in this phase can add real test bodies without inventing file names, fixture names or docstrings first.
- FastAPI 0.141.1 confirmed to ship `app.frontend()` — plan 01-06 can use it directly.
- `tests/test_web/conftest.py`'s `client`/`blank_client` fixtures will start failing (not erroring) the moment `comiccolor.web.app.create_app` doesn't exist yet if any *non-skipped* test tries to use them before 01-06 lands; none of Wave 0's stubs do, since every stub body is `...` under `@pytest.mark.skip`.
- No blockers for plans 01-02 through 01-05, all of which are independent of this plan's file set.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*

## Self-Check: PASSED

All created files verified present on disk (pyproject.toml, tests/test_pipeline.py,
tests/test_extract.py, tests/test_web/__init__.py, tests/test_web/conftest.py,
tests/test_web/test_project_routes.py, tests/test_web/test_page_routes.py,
tests/test_web/test_palette_routes.py, this SUMMARY.md). All four task commits
(fd8fca6, 1cac320, c2be4f2, 2d926b4) verified present in git log.
