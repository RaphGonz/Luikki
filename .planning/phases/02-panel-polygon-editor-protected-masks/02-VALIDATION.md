---
phase: 2
slug: panel-polygon-editor-protected-masks
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-16
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `02-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest 8.0+ (existing, `pyproject.toml` `[tool.pytest.ini_options]`) |
| **Framework (frontend)** | vitest ^4.1.10 (existing, `frontend/vitest.config.ts`) |
| **Config file** | `pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["src"]`) · `frontend/vitest.config.ts` (currently `environment: "node"` — Wave 0 adds a `jsdom` path) |
| **Quick run command** | `pytest tests/test_panels.py tests/test_bubbles.py -x` · `npm run test -- editor` (from `frontend/`) |
| **Full suite command** | `pytest tests/` · `npm run test` (from `frontend/`) |
| **Estimated runtime** | ~30 seconds (backend) · ~10 seconds (frontend) |

---

## Sampling Rate

- **After every task commit:** Run the targeted quick-run command scoped to the file(s) touched.
- **After every plan wave:** Run `pytest tests/` AND `npm run test` — both full suites green.
- **Before `/gsd-verify-work`:** Full suite must be green, plus a manual UAT pass against a real page with a panel-boundary-crossing bubble/SFX (success criterion 4's "not only on a clean test page" cannot be satisfied by synthetic fixtures alone).
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | PAN-01 | — | N/A | unit | `pytest tests/test_panels.py -x` | ✅ / ❌ W0 (new `box_to_polygon` cases) | ⬜ pending |
| TBD | TBD | TBD | PAN-02 | T-2-xx | Polygon writes validated against page bounds before persistence | unit | `pytest tests/test_web/test_panel_routes.py -x` + `npm run test -- polygonState` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PAN-03 | T-2-xx | Create/delete scoped to a validated page_id | unit + integration | `pytest tests/test_web/test_panel_routes.py::test_create_and_delete_panel -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PROT-01 | — | N/A | unit | `pytest tests/test_bubbles.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PROT-02 | T-2-xx | Hand-drawn mask vertices bounds-checked | unit | `pytest tests/test_web/test_protected_routes.py::test_create_mask_by_hand -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PROT-03 | — | N/A | unit + frontend | `pytest tests/test_web/test_protected_routes.py::test_reshape_and_delete -x` + `npm run test -- polygonState` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | PROT-04 | — | Protected pixels never enter a fill or colour stage | unit | `pytest tests/test_trappedball.py::test_protected_pixels_stay_unassigned -x` + new boundary-crossing case | ✅ file / ❌ W0 case | ⬜ pending |
| TBD | TBD | TBD | Success criterion 2 (zoom-invariant) | — | N/A | unit | `npm run test -- transform` + `npm run test -- hitTest` | ✅ transform / ❌ W0 hitTest | ⬜ pending |

*Task IDs are filled by the planner; rows above are the requirement-level contract every plan must satisfy.*

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_bubbles.py` — new file, covers PROT-01 (`detect_bubbles`, `mask_to_polygon`)
- [ ] `tests/test_web/test_panel_routes.py` — new file, covers PAN-02/PAN-03 route-level behavior
- [ ] `tests/test_web/test_protected_routes.py` — new file, covers PROT-02/PROT-03 route-level behavior
- [ ] `tests/test_panels.py` — extend with `box_to_polygon` / reading-order coverage (PAN-01)
- [ ] `tests/test_trappedball.py` — extend with an explicit panel-boundary/SFX-crossing protected-pixel case (PROT-04)
- [ ] `frontend/tests/editor/polygonState.test.ts` — new file, pure reducer coverage (PAN-02/PAN-03/PROT-02/PROT-03)
- [ ] `frontend/tests/editor/hitTest.test.ts` — new file, distance-based hit-testing against `transform.ts` at extreme zoom (success criterion 2)
- [ ] `frontend/tests/editor/undoStack.test.ts` — new file, 20-op cap and inverse-replay correctness (UI-SPEC §6)
- [ ] `frontend/vitest.config.ts` — add a `jsdom`-environment path (per-file `// @vitest-environment jsdom` docblocks or a second config) for DOM-structure/ARIA assertions on the new editor components
- [ ] `npm install --save-dev jsdom` — DOM-structure tests only; do **not** install the native `canvas` package (Cairo bindings, Windows-hostile, and dependency-adjacent to D-26)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Canvas rendering fidelity (polygon strokes, vertex handles, dashed vs solid mask state) | PAN-02, PROT-03 | jsdom does not implement real `<canvas>` 2D rendering; the native `canvas` package is rejected (see Wave 0) | Load a real page in the editor, zoom to extremes, confirm handles and strokes render at correct positions and mask state styling matches UI-SPEC §6 |
| Protection survives every fill/colour stage and reaches PSD export untouched | PROT-04 | End-to-end across segmentation + export; requires a real page where art or an SFX crosses a panel boundary | Run the full pipeline on a boundary-crossing page, open the exported PSD, confirm protected regions are pixel-identical to the input ink |
| Correction persistence across zoom levels in a real browser | Success criterion 2 | Real devicePixelRatio and browser event coordinates cannot be faithfully simulated in jsdom | Drag a vertex at 100% zoom, zoom to 800%, confirm the vertex is where it was placed; repeat inverting the order |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
