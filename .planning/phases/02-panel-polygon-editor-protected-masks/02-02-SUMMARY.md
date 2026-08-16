---
phase: 02-panel-polygon-editor-protected-masks
plan: 02
subsystem: segmentation
tags: [panels, protected-masks, prot-04, trapped-ball, tdd]

# Dependency graph
requires: ["02-01: tests/conftest.py boundary_crossing_page builder"]
provides:
  - "src/comiccolor/segmentation/panels.py — box_to_polygon(box) -> 4-vertex clockwise polygon; PanelParams.min_solidity=0.25; PanelParams.reading=\"ltr\""
  - "src/comiccolor/segmentation/protected.py — rasterize_protected_for_panel(polygons, panel_x, panel_y, panel_w, panel_h) -> bool array; protected_bbox_and_area(polygon, page_w, page_h) -> (area, bbox)"
  - "src/comiccolor/segmentation/trappedball.py — expand_under_lines(labels, line_mask, protected=None) now takes an optional protected= to stop it painting protected-but-inked pixels"
affects: ["02-03", "02-04", "02-05", "02-08", "02-09", "02-11"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Page-space polygon, clip at use — protected.py never persists a panel-local copy; the panel-local array is derived on demand via cv2.fillPoly, which clips to the destination bounds for free (no manual intersection arithmetic)."
    - "box_to_polygon seeds Panel.polygon from the box's four corners, never traces the ink silhouette — findContours is explicitly forbidden in the docstring for the borderless-panel reason (D-17)."

key-files:
  created:
    - src/comiccolor/segmentation/protected.py
    - tests/test_protected_raster.py
  modified:
    - src/comiccolor/segmentation/panels.py
    - src/comiccolor/segmentation/trappedball.py
    - tests/test_panels.py
    - tests/test_trappedball.py

key-decisions:
  - "D-17/D-18/D-20/D-21 implemented as specified in 02-CONTEXT.md; no reinterpretation."
  - "[Rule 1 - Bug] expand_under_lines gained an optional protected= parameter after the new boundary-crossing test caught it painting a protected pixel that also happened to be an ink pixel (a bubble drawn across a panel's frame border). See Deviations below."

requirements-completed: [PAN-01, PROT-04]

# Metrics
duration: 45min
completed: 2026-08-16
---

# Phase 2 Plan 2: Panel Polygons, Protected-Mask Rasterisation, and the Boundary-Crossing Proof Summary

**Panels now seed a four-vertex page-space polygon and default to left-to-right reading; one new function clips a page-scoped protected polygon into any panel's local frame; and a new test proves protected pixels survive segmentation — including `expand_under_lines` — on a page where the protected region crosses a panel boundary, catching a real leak in `expand_under_lines` along the way.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 3 (all `type="auto" tdd="true"`)
- **Files modified:** 6 (4 modified, 2 created)

## Accomplishments

- `src/comiccolor/segmentation/panels.py`:
  - `box_to_polygon(box: PanelBox) -> list[tuple[int, int]]` returns the four
    corners top-left, top-right, bottom-right, bottom-left (clockwise from
    top-left), page-pixel space. Docstring states `findContours` must never
    be called here and explains why (D-17): on a borderless panel the
    surviving gutter-network component is the ink silhouette of the drawing
    itself, so tracing it yields a polygon shaped like the character, not
    the panel.
  - `PanelParams.min_solidity` lowered `0.55 -> 0.25` (D-18), with an inline
    comment recording that this is a floor that silently *discards*
    components and instructing the next contributor not to raise it back.
  - `PanelParams.reading` default changed `"rtl" -> "ltr"` (UI-SPEC §7);
    `"rtl"` remains reachable by passing it explicitly, and both directions
    have test coverage.
- `src/comiccolor/segmentation/protected.py` (new):
  - `rasterize_protected_for_panel(polygons, panel_x, panel_y, panel_w, panel_h) -> np.ndarray`
    clips page-space polygons into a panel-local boolean array via
    `cv2.fillPoly`, which clips to the destination array's bounds — no
    manual intersection arithmetic needed for a polygon straddling two
    panels. Polygons with fewer than 3 vertices are skipped, never raised.
  - `protected_bbox_and_area(polygon, page_w, page_h) -> (area, (x, y, w, h))`
    is the one definition of both values the store needs on write.
  - Module docstring states D-20 (page-scoped storage, clip-at-use) and D-21
    (protection means "never coloured", not "content preserved" — no
    `assert_invariant`-style fail-loud chain belongs on top of this).
- `tests/test_trappedball.py`: new
  `test_protected_pixels_stay_unassigned_across_a_panel_boundary` builds
  `boundary_crossing_page()`'s two panels, derives the straddling bubble's
  page-space polygon from the fixture's own known geometry
  (`cv2.ellipse2Poly` on the same centre/axes the fixture drew its outline
  with), and for each panel: asserts the clipped protected array is
  non-empty (no vacuous pass), then that neither `trapped_ball_segment`'s
  raw labels nor `expand_under_lines`'s output carry a label on a protected
  pixel.

## Task Commits

Each task was committed atomically, RED then GREEN per the TDD gate:

1. **Task 1 — box_to_polygon, min_solidity floor, ltr default**
   - `f828da6` (test): failing tests for the three behaviors
   - `4de93fd` (feat): implementation, all 11 tests in `test_panels.py` green
2. **Task 2 — rasterize_protected_for_panel / protected_bbox_and_area**
   - `2ba6cdf` (test): failing tests, including the boundary-crossing case
   - `b6b0961` (feat): implementation, all 7 tests in `test_protected_raster.py` green
3. **Task 3 — PROT-04 evidence on a boundary-crossing page**
   - `8745349` (fix): test + the `expand_under_lines` bug it caught, committed together (see Deviations)

**Plan metadata:** pending (this commit, docs: complete plan)

## Files Created/Modified

- `src/comiccolor/segmentation/panels.py` — `box_to_polygon`, `min_solidity=0.25`, `reading="ltr"`
- `src/comiccolor/segmentation/protected.py` — new, `rasterize_protected_for_panel`, `protected_bbox_and_area`
- `src/comiccolor/segmentation/trappedball.py` — `expand_under_lines` gained `protected: np.ndarray | None = None`
- `tests/test_panels.py` — 3 new tests
- `tests/test_protected_raster.py` — new, 7 tests
- `tests/test_trappedball.py` — 1 new test, `expand_under_lines` call sites updated

## Decisions Made

- Implemented D-17, D-18, D-20, D-21 exactly as locked in `02-CONTEXT.md`; no
  re-derivation.
- `protected_bbox_and_area`'s bbox convention follows `cv2.fillPoly`'s own
  inclusive-boundary rasterisation (a rectangle with corners at x=20 and
  x=80 covers pixel columns 20..80 inclusive, width 61, not 60) rather than
  a half-open convention — this matches `rasterize_protected_for_panel`'s
  behavior exactly, since both go through the same `cv2.fillPoly` call, and
  keeps "one definition of area and bbox" true in practice, not just in
  the docstring.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `expand_under_lines` painted a protected pixel that also happened to be ink**
- **Found during:** Task 3, writing `test_protected_pixels_stay_unassigned_across_a_panel_boundary`
- **Issue:** `expand_under_lines(labels, line_mask)` computed its expansion
  target as `line_mask & (labels == UNASSIGNED)`, with no reference to
  `protected` at all. The existing test
  (`test_expand_under_lines_covers_ink_but_not_protected`) never caught this
  because its protected region sat entirely off the box's frame lines, so
  `line_mask` alone happened to exclude it. `boundary_crossing_page()`'s
  bubble is centred on the gutter and its axes reach past both panel
  edges — meaning its filled polygon overlaps the panel's own frame border,
  which *is* an ink pixel. Those pixels are simultaneously "line" and
  "protected", and the old code painted them with the nearest region's
  label, violating D-21 (protection must win that conflict; expansion is a
  line-art fix, not a colouring right).
- **Fix:** Added an optional `protected: np.ndarray | None = None` parameter
  to `expand_under_lines`. When supplied, the expansion target excludes
  protected pixels unconditionally: `target &= ~protected`. Default `None`
  preserves the exact prior behavior for the one other call site
  (`test_expand_under_lines_covers_ink_but_not_protected`, unchanged) and any
  future caller that has not yet been updated to pass it.
- **Files modified:** `src/comiccolor/segmentation/trappedball.py`,
  `tests/test_trappedball.py` (new test passes `protected=panel_protected`)
- **Commit:** `8745349`

## Issues Encountered

None beyond the auto-fixed issue above.

## User Setup Required

None.

## Next Phase Readiness

- `Panel.polygon` (already on the entity per Wave 1's read of `entities.py`)
  is ready to be seeded with `box_to_polygon(box)` by whichever plan first
  persists a segmented panel — that wiring itself is out of this plan's
  scope (`entities.py`/`store.py` for D-20's `panel_id -> page_id` move on
  `ProtectedMask` is likewise a later plan's responsibility, per the plan's
  stated `files_modified` list).
- `expand_under_lines`'s new `protected=` parameter is optional and
  backward-compatible; any pipeline stage that runs it against a page with
  real protected masks should pass `protected=` going forward — flagging
  this so a later planner does not have to rediscover the leak this plan
  just closed.
- No blockers for downstream Phase 2 plans.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16*

## Self-Check: PASSED
