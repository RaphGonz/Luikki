---
phase: 02-panel-polygon-editor-protected-masks
plan: 04
subsystem: segmentation
tags: [opencv, connected-components, flood-fill, contour-tracing, bubble-detection]

# Dependency graph
requires:
  - phase: 02-panel-polygon-editor-protected-masks
    provides: "tests/conftest.py's bubble_page/glyph_row synthetic page builders (plan 02-01)"
provides:
  - "comiccolor.segmentation.bubbles: BubbleParams, detect_bubbles(grey, line_mask, params=None), mask_to_polygon(mask, epsilon_frac=0.01)"
  - "D-22/D-23 text-seeded flood-fill bubble detector, verified FLOODFILL_MASK_ONLY flag semantics against the installed OpenCV 5.0.0 build"
affects: ["02-07 (protected stage runner consumes detect_bubbles/mask_to_polygon)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Text-seeded flood fill for bubble detection: connected-component glyph filtering (height band + aspect ratio), dilate-based clustering, seed-adjacent-to-cluster flood fill, area-cap and ground-brightness discard"
    - "Contour trace + approxPolyDP with perimeter-relative epsilon to convert a raster detection mask into an editable vertex polygon"

key-files:
  created:
    - src/comiccolor/segmentation/bubbles.py
    - tests/test_bubbles.py
  modified: []

key-decisions:
  - "Verified cv2.floodFill's FLOODFILL_MASK_ONLY flag/mask-size/fill-value convention directly against the installed OpenCV 5.0.0 build before writing any detector code (Task 1) — the research sketch's flag combination (4 | FLOODFILL_MASK_ONLY | (255 << 8)) proved correct on the first attempt, no inversion, so it became the implemented contract unchanged."
  - "Added BubbleParams.min_ground_brightness (not in the plan's enumerated field list) to give D-22 point 4's 'lettering sitting on artwork' discard a named, commented threshold rather than a bare literal, per the plan's own closing rule that every threshold comparison must read a BubbleParams field."
  - "Hatching rejection (D-23) is enforced jointly by the height/aspect glyph filters and the area cap, not by the glyph filters alone — a hatching-only page's median height is computed from the hatching itself, so height-band filtering doesn't discriminate it in isolation; what actually discards it is that hatching sits in open (non-enclosed) white, so its flood fill exceeds max_area_frac. Test asserts the net behavior (zero bubbles), matching the plan's stated acceptance criterion."

patterns-established:
  - "Bubble detector module mirrors panels.py's shape: §-referenced docstring stating design rationale, @dataclass params with a per-field inline comment naming the tradeoff, pure functions on numpy arrays, single-purpose private helpers."

requirements-completed: [PROT-01]

# Metrics
duration: 25min
completed: 2026-08-16
---

# Phase 2 Plan 4: Bubble Detector (D-22/D-23 Text-Seeded Flood Fill) Summary

**`comiccolor.segmentation.bubbles.detect_bubbles` — connected-component glyph detection, dilate-clustered seeding, area-capped flood fill, and ground-brightness discard, traced into editable polygons via `mask_to_polygon`; zero new dependencies.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 (TDD: RED then GREEN)
- **Files modified:** 2 (both created)

## Accomplishments

- Verified `cv2.floodFill`'s `FLOODFILL_MASK_ONLY` flag/mask-size/fill-value semantics against the real installed OpenCV 5.0.0 build (`4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)`, mask 2px larger on every side, crop `[1:-1, 1:-1]`) — matched the research sketch exactly, no inversion, on the first isolated test.
- `detect_bubbles(grey, line_mask, params=None)`: glyph candidates via `connectedComponentsWithStats` height-band + aspect-ratio filtering (D-23, no OCR), dilate-based clustering with a lonely-blob floor (`min_glyphs_per_cluster`), seed-adjacent-to-cluster flood fill, area cap (D-22 point 3) and ground-brightness discard (D-22 point 4), de-duplicated across clusters, hard-capped at `max_bubbles`.
- `mask_to_polygon(mask, epsilon_frac=0.01)`: `findContours` + perimeter-relative `approxPolyDP`, returns `[]` for no contour or a sub-3-vertex trace.
- One closed bubble with a glyph row yields exactly one mask, not one per glyph. Hatching, an unclosed outline, and lettering on artwork all yield zero.
- No new dependency — `cv2`/`numpy` only, confirmed by import-list grep.

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin down cv2.floodFill's mask semantics, then write the detector's test surface** - `ba919e3` (test)
2. **Task 2: bubbles.py — glyph candidates, seeded flood fill, area cap, contour trace** - `d2ba3f7` (feat)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified

- `tests/test_bubbles.py` - PROT-01 behavioural contract: floodFill semantics, one-bubble-per-cluster, hatching rejection, unclosed-outline area-cap discard, lettering-on-artwork discard, polygon vertex-bound checks, empty-mask handling
- `src/comiccolor/segmentation/bubbles.py` - `BubbleParams`, `detect_bubbles`, `mask_to_polygon`, `_glyph_candidates`, `_glyph_clusters`

## Decisions Made

- Verified the flood-fill flag convention against the installed build before writing detector code (Task 1's own gate) — it matched the research sketch exactly, so no correction was needed, but the verification test stays in the suite as the standing regression guard 02-RESEARCH.md Pitfall 2 calls for.
- Added `BubbleParams.min_ground_brightness` beyond the plan's enumerated field list — required by the plan's own action text ("reject when the filled region's mean brightness is below a mid-grey threshold") and by its closing rule that no function body carry a magic-number threshold. Documented as a deviation below (Rule 2).
- Kept the module's docstring claim about D-23's height/aspect filters rejecting hatching as written in the plan; the test suite verifies the net behavior (hatching produces zero bubbles) rather than asserting the glyph-filter step alone rejects every hatching component, since in practice the area cap is what discards an unenclosed hatching patch. See deviation note below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `BubbleParams.min_ground_brightness` field**
- **Found during:** Task 2 (bubbles.py implementation)
- **Issue:** The plan's `<action>` text requires `detect_bubbles` to "reject when the filled region's mean brightness is below a mid-grey threshold" (D-22 point 4), but `BubbleParams`'s enumerated field list in the plan does not include a brightness threshold field. Implementing the comparison as a bare literal would violate the plan's own closing sentence: "Every threshold comparison reads a `BubbleParams` field. No magic numbers in function bodies."
- **Fix:** Added `min_ground_brightness: float = 127.0` to `BubbleParams` with an inline comment naming it as the natural 8-bit midpoint, not tuned against real pages.
- **Files modified:** `src/comiccolor/segmentation/bubbles.py`
- **Verification:** `test_lettering_on_artwork_is_discarded` exercises this exact branch and passes; `grep -n "class BubbleParams" src/comiccolor/segmentation/bubbles.py` confirms the field lives on the dataclass, not inline.
- **Committed in:** `d2ba3f7` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical, Rule 2)
**Impact on plan:** Necessary to satisfy the plan's own "no magic numbers" convention while implementing a discard branch the plan explicitly requires. No scope creep — no new dependency, no new public API beyond what the plan specified.

## Issues Encountered

None — the floodFill flag combination sketched in 02-RESEARCH.md Pattern 2 was verified correct against the installed build on the first attempt (see `test_floodfill_mask_only_semantics_on_this_opencv_build`), so no flag correction was required going into Task 2.

## User Setup Required

None — no external service configuration required, no new dependency.

## Next Phase Readiness

- `detect_bubbles`/`mask_to_polygon` are ready for the `protected` stage runner (plan 02-07) to call: `detect_bubbles(grey, line_mask)` returns page-space boolean masks, `mask_to_polygon(mask)` traces each into a page-space vertex list matching `ProtectedMask.polygon`'s shape (D-20).
- `pytest tests/ -q` is green: 175 passed, 2 xfailed (168 baseline + 7 new `test_bubbles.py` tests, no regressions).
- No blockers for downstream Phase 2 plans. `max_area_frac`, `epsilon_frac`, and the new `min_ground_brightness` are flagged `[ASSUMED]`/un-tuned in the module and should be validated against real project pages at UAT time, per the plan's own framing — not a blocker, a known tuning surface.

---
*Phase: 02-panel-polygon-editor-protected-masks*
*Completed: 2026-08-16*
