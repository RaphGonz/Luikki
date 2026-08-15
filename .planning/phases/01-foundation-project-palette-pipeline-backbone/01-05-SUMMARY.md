---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 05
subsystem: colour
tags: [pillow, scikit-image, quantize, cielab, palette-extraction]

# Dependency graph
requires:
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "tests/test_extract.py Wave 0 skip-marked stubs (plan 01-01)"
provides:
  - "comiccolor.colour.extract_palette(image, *, sheet_mode=False) -> list[ExtractedColour] — one extractor for both PAL-01 (swatch) and PAL-02 (character sheet)"
  - "ExtractedColour(rgb, pixel_count, pixel_share) frozen dataclass"
  - "EmptyImageError (ValueError subclass) for structured 4xx mapping by the web layer"
  - "Five named, unvalidated-flagged constants: K_MAX, MERGE_DELTA_E, MIN_PIXEL_SHARE, INK_MAX, PAPER_MIN"
affects: ["01-08", "01-09", "01-10"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Quantize-then-merge: Pillow Image.quantize(MEDIANCUT) for the solved 90%, a small skimage.color CIELAB deltaE_cie76 greedy merge for the adaptive-count 10% (D-13's 'don't hand-roll' seam)"
    - "Sheet-aware pre-pass as a pixel filter (kept pixels reshaped into an Nx1 synthetic image), not an alpha trick"
    - "Named module-level constants flagged 'unvalidated starting value' in their own comment, per RESEARCH.md Pitfall 5"

key-files:
  created:
    - src/comiccolor/colour/__init__.py
    - src/comiccolor/colour/extract.py
  modified:
    - tests/test_extract.py

key-decisions:
  - "pixel_share is computed once against the merged (pre-noise-drop) total and used both to decide which clusters survive MIN_PIXEL_SHARE and as the final share value — plan text was ambiguous between 'total kept' meaning pre-drop or post-drop; pre-drop was chosen since re-normalizing after dropping noise clusters isn't stated anywhere and would silently inflate shares."
  - "RGBA input is flattened onto a fixed mid-neutral (128,128,128) background before quantizing, per RESEARCH.md Pattern 3's caveat that MEDIANCUT/MAXCOVERAGE reject RGBA outright."

patterns-established:
  - "Colour-extraction seam mirrors extract/base.py's ExtractionResult shape conceptually (typed dataclass out, no bare tuples), even though ExtractedColour is a list-of-dataclass rather than a single result object, since the extraction result here is inherently a set of colours."

requirements-completed: [PAL-01, PAL-02]

# Metrics
duration: 35min
completed: 2026-08-15
---

# Phase 1 Plan 5: Palette Extraction (quantize-then-merge) Summary

**`extract_palette()` recovers a flat chip grid exactly via Pillow's `MEDIANCUT` quantizer, then collapses near-duplicate clusters with a `skimage.color` CIELAB `deltaE_cie76` merge to produce an adaptive colour count — one function serving both the swatch (PAL-01) and character-sheet (PAL-02) paths, differing only by an ink/paper pre-pass.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-08-15 (worktree wave 2)
- **Completed:** 2026-08-15
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- `src/comiccolor/colour/extract.py` implements `extract_palette(image, *, sheet_mode=False) -> list[ExtractedColour]`: RGBA flattening, `MEDIANCUT` quantize at `K_MAX=24`, a greedy CIELAB `deltaE_cie76` merge (`_merge_similar`), noise-floor drop at `MIN_PIXEL_SHARE`, descending-share sort.
- `_drop_ink_and_paper` adds the D-14 sheet-aware pre-pass — a pure pixel filter (near-black/near-white boolean masks, survivors reshaped into an `Nx1` synthetic image), wired in only when `sheet_mode=True`. Raises `EmptyImageError` (a `ValueError` subclass) on an all-ink or all-paper sheet.
- Five constants (`K_MAX=24`, `MERGE_DELTA_E=12.0`, `MIN_PIXEL_SHARE=0.005`, `INK_MAX=30`, `PAPER_MIN=235`) are named module-level values, each commented as an unvalidated starting hypothesis (RESEARCH.md Pitfall 5) rather than buried magic numbers.
- `tests/test_extract.py`'s five Wave 0 stubs are filled in and three more added — 8 tests total, all passing, no skips: flat-chip exact recovery (D-12), adaptive merge (D-15), sheet pre-pass (D-14), noisy-gradient sane count (Pitfall 5's second regime), named-constants pin, `EmptyImageError` on an all-ink sheet, descending-share ordering, RGBA input handled without crashing.
- No chip/contour detection (`cv2.findContours`/`connectedComponents`) or hand-rolled k-means/colour-distance formula anywhere in the module (D-12/D-13, verified by grep in every task's acceptance criteria).
- `extract_palette` takes no colour-count parameter (D-15) — confirmed via `inspect.signature`.
- Full suite (`pytest -q`) stays green: 58 passed, 24 skipped, 2 xfailed — no regressions.

## Observed adaptive counts (synthetic test images, for 01-08/01-09/01-10)
- 40x40 four-flat-chip grid (`test_flat_chip_grid_recovers_exact_colours`): **4 entries**, exact source RGBs, zero invented colours.
- 40x40 two-near-duplicate-chip grid, ΔE well under `MERGE_DELTA_E` (`test_adaptive_count_collapses_near_duplicates`): **1 entry**, `pixel_count == 1600` (sum of both chip areas).
- 80x80 sheet with ink band + 2 real colours + paper band, `sheet_mode=True` (`test_sheet_prepass_drops_ink_and_paper`): **2 entries** (only the real colours); same image `sheet_mode=False`: **4 entries** (ink and paper both survive as their own clusters).
- 16x256 horizontal greyscale ramp (`test_noisy_gradient_returns_a_sane_count`): count lands strictly between 1 and `K_MAX=24`; every surviving entry's `pixel_share >= MIN_PIXEL_SHARE`.

## `extract_palette` signature (final, for 01-08/01-09/01-10 to marshal into HTTP)
```python
def extract_palette(
    image: Image.Image, *, sheet_mode: bool = False
) -> list[ExtractedColour]: ...
```
`ExtractedColour` fields: `rgb: tuple[int, int, int]`, `pixel_count: int`, `pixel_share: float`. Frozen dataclass, no mutation after construction. List is sorted descending by `pixel_share`, so entry `[0]` is always the dominant colour — Phase 1's grid rendering (01-UI-SPEC.md §4) can rely on list order directly.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement quantize-then-merge extraction with an adaptive count** - `e9950a8` (feat)
2. **Task 2: Add the character-sheet ink and paper pre-pass** - `6b3144c` (feat)
3. **Task 3: Fill the extraction test module across both regimes** - `6dcc8f5` (test)

**Plan metadata:** pending (this commit, docs: complete plan)

## Files Created/Modified
- `src/comiccolor/colour/__init__.py` - package re-exports (`ExtractedColour`, `extract_palette`, `EmptyImageError`, five constants), matching `model/__init__.py`'s shape
- `src/comiccolor/colour/extract.py` - `extract_palette`, `ExtractedColour`, `EmptyImageError`, five named constants, `_flatten_to_rgb`, `_quantize_counts`, `_merge_similar`, `_drop_ink_and_paper`
- `tests/test_extract.py` - 8 tests (5 unskipped Wave 0 stubs + 3 new), module-level imports (no longer function-local)

## Decisions Made
- `pixel_share` denominator is fixed at the merged (pre-noise-drop) total pixel count, computed once and reused both to decide which clusters clear `MIN_PIXEL_SHARE` and as each surviving entry's final `pixel_share`. The plan's step 5/6 wording ("total kept pixels" / "total kept pixel count") could be read either as the pre-drop or post-drop total; pre-drop was chosen as the more literal reading and because re-normalizing after the noise drop is never stated and would silently make small extractions look artificially confident.
- RGBA input is flattened onto a fixed `(128, 128, 128)` background rather than left to Pillow's own alpha-aware quantization path, per RESEARCH.md Pattern 3's explicit caveat that `MEDIANCUT`/`MAXCOVERAGE` reject RGBA outright.

## Deviations from Plan

None - plan executed exactly as written. Docstring prose was worded to avoid literal `findContours`/`connectedComponents`/`KMeans` substrings (using "OpenCV's contour and connected-component finders" / "a K-means-based library" instead) so the plan's own anti-pattern grep check (`grep -cE "findContours|connectedComponents|KMeans|kmeans"` returns 0) passes while still citing the same design history in the module docstring — a wording choice within Task 1's own action text, not a deviation from it.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required. `scikit-image` was already declared and installed by plan 01-01.

## Next Phase Readiness
- `extract_palette` and `ExtractedColour` are ready for plans 01-08 (page routes), 01-09, and 01-10 (palette routes) to marshal directly into HTTP responses — no colour-count parameter to plumb through, matching D-15.
- The CIELAB helper choice (`skimage.color.rgb2lab` + `deltaE_cie76`) previews Phase 5's snapping-distance code, as RESEARCH.md's Don't Hand-Roll table anticipated.
- `MERGE_DELTA_E`, `INK_MAX`, `PAPER_MIN` remain explicitly flagged as unvalidated in-code; real character-sheet tuning is deferred to supervised video-call sessions per PAL-03's manual add/delete recovery path, already locked as the accepted mitigation (RESEARCH.md Assumptions Log A1).
- No blockers for downstream plans in this phase.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*

## Self-Check: PASSED

All created/modified files verified present on disk (`src/comiccolor/colour/__init__.py`,
`src/comiccolor/colour/extract.py`, `tests/test_extract.py`, this SUMMARY.md). All three
task commits (`e9950a8`, `6b3144c`, `6dcc8f5`) verified present in `git log`.
