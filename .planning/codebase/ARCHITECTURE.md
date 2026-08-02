<!-- refreshed: 2026-08-02 -->
# Architecture

**Analysis Date:** 2026-08-02

## System Overview

```text
┌──────────────────────────────────────────────────────────────────┐
│                     Entry Point (CLI)                            │
│              `src/comiccolor/cli.py`                             │
│            (p3, ab research spikes)                              │
└────────────────────────┬─────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
┌────────▼──────────┐        ┌──────────▼──────────┐
│  Line Extraction  │        │ Panel Segmentation  │
│  `extract/`       │        │ `segmentation/`     │
│ - LineExtractor   │        │ - segment_panels()  │
│ - MangaLine       │        │ - PanelBox[]        │
│ - Passthrough     │        └─────────────────────┘
└────────┬──────────┘                   │
         │                              │
         └──────────────┬───────────────┘
                        │
              ┌─────────▼─────────┐
              │ Region Segmentation│
              │ `segmentation/`    │
              │ - Segmenter (Proto)│
              │ - TrappedBall      │
              │ - LineFiller       │
              │ - close_line_gaps()│
              └─────────┬──────────┘
                        │
           ┌────────────▼────────────┐
           │   Data Model Layer      │
           │   `model/`              │
           │ - entities.py (§3)      │
           │ - masks.py (label maps) │
           │ - store.py (SQLite)     │
           └────────────┬────────────┘
                        │
              ┌─────────▼──────────┐
              │ Spike/Research     │
              │ `spike/`           │
              │ - p3.py (metrics)  │
              │ - ab.py (compare)  │
              │ - visualise.py     │
              └────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Entry Point | CLI command parsing, orchestrate research spikes | `src/comiccolor/cli.py` |
| Line Extraction | Learned or passthrough line art preprocessing | `src/comiccolor/extract/` |
| Panel Detection | Gutter-based panel bounds via trapped-ball (§1.1) | `src/comiccolor/segmentation/panels.py` |
| Line Preprocessing | Raster I/O, ink fraction, line width estimation | `src/comiccolor/segmentation/preprocess.py` |
| Gap Closure | Optional line closure via morphology (§1.3) | `src/comiccolor/segmentation/closure.py` |
| Region Segmentation | Flood-fill based region labeling (§1.4) | `src/comiccolor/segmentation/segmenter.py`, `trappedball.py` |
| Data Model | §3 domain objects (Series, Volume, Page, Panel, Region, PaletteEntry, Entity) | `src/comiccolor/model/entities.py` |
| Label Maps | Exact region storage (int32 label arrays) and queries | `src/comiccolor/model/masks.py` |
| Persistence | SQLite store for the data model, enforces no-RGB-in-regions invariant | `src/comiccolor/model/store.py` |
| Research Spikes | P3 region-count metrics, AB segmenter comparison | `src/comiccolor/spike/` |

## Pattern Overview

**Overall:** Research-driven pipeline architecture with **swappable components at two seams:**

1. **Line Extraction Seam** (`extract/` implements `LineExtractor` protocol)
   - Allows different learned models (MangaLineExtraction, future Tier 3 domain adapters) or no-op passthrough
   - Sits strictly upstream of segmentation; segmentation receives exact raster, produces exact masks
   - A learned extractor changes which pixels are line; it cannot make regions overlap

2. **Region Segmentation Seam** (`segmentation/segmenter.py` implements `Segmenter` protocol)
   - Both `TrappedBallSegmenter` (our implementation) and `LineFillerSegmenter` (hepesu/LineFiller, MIT) are swappable
   - Both produce identical output (int32 label map, 0 = unassigned)
   - Chosen on A/B results (see `spike/ab.py`), not on counts alone

**Key Characteristics:**

- **Deterministic exactness** — Segmentation (§1.4) and panel detection (§1.1) use flood-fill on line rasters, not learned models. Regions are exact geometric masks, not probabilistic.
- **Separates concerns** — §9 anti-pattern "do not conflate segmentation and labelling": the label map is the inspectable boundary between geometric (deterministic) and semantic (probabilistic, future Cobra).
- **No RGB baking** — Region entities store `palette_entry_id` reference, never RGB. Single-row update changes colour everywhere (§3, §9).
- **Exhaustiveness invariant** — Regions within a panel are mutually exclusive and exhaustive. Enforced structurally: one int32 label map per panel, one Region per unique label value (§3).

## Layers

**Entry Point / CLI:**
- Purpose: Parse research spike commands (p3, ab), orchestrate page loading and segmentation
- Location: `src/comiccolor/cli.py`
- Contains: Argument parsing, page collection from files or directories
- Depends on: `spike/p3`, `spike/ab`, `segmentation/`, `extract/`
- Used by: External (comiccolor CLI binary via pyproject.toml)

**Line Extraction:**
- Purpose: Transform raw page greyscale into a line-only greyscale image. Swappable for domain adapters (§7).
- Location: `src/comiccolor/extract/`
- Contains: Protocol `LineExtractor`, implementations (`MangaLineExtractor`, `PassthroughExtractor`)
- Depends on: Third-party extractors (MangaLineExtraction), OpenCV
- Used by: `spike/p3`, `spike/ab`

**Segmentation (Deterministic):**
- Purpose: Convert line rasters into exact region masks via flood-fill.
- Location: `src/comiccolor/segmentation/`
- Contains:
  - `preprocess.py` — Raster I/O, ink fraction, line width estimation
  - `panels.py` — Gutter detection via trapped-ball on page margins (§1.1)
  - `closure.py` — Gap closure via morphological operations (§1.3)
  - `trappedball.py` — Our trapped-ball region segmentation (§1.4)
  - `segmenter.py` — Protocol and implementations (TrappedBallSegmenter, LineFillerSegmenter)
- Depends on: OpenCV, NumPy, third-party LineFiller (vendored)
- Used by: `spike/p3`, `spike/ab`

**Data Model:**
- Purpose: §3 domain hierarchy and invariants.
- Location: `src/comiccolor/model/entities.py`
- Contains: `Series`, `Volume`, `Page`, `Panel`, `Region`, `PaletteEntry`, `Entity`, `ProtectedMask`, enums
- Enforces: Region.palette_entry_id is the only colour reference; no RGB field on Region
- Used by: `store.py`, spike modules for metadata collection

**Label Maps (Exact Region Storage):**
- Purpose: Store region segmentation as int32 label arrays; provide queries on coverage, region stats.
- Location: `src/comiccolor/model/masks.py`
- Contains: I/O (`save_label_map`, `load_label_map`), queries (`region_stats`, `region_count`, `check_coverage`), relabeling
- Depends on: NumPy, Path I/O
- Used by: `store.py`, spike modules for metric collection

**Persistence:**
- Purpose: SQLite schema enforcing §3 constraints and §9 anti-patterns.
- Location: `src/comiccolor/model/store.py`
- Contains: `Store` class, SCHEMA with foreign keys, CRUD for all entity types
- Enforces: No RGB column on region table; all colours live on palette_entry table only
- Used by: Future Tier 1 UI and export pipelines (not yet integrated)

**Research Spikes:**
- Purpose: Measure segmentation quality (P3: region counts per panel; AB: compare implementations)
- Location: `src/comiccolor/spike/`
- Contains:
  - `p3.py` — Per-panel region-count measurement across extractors/thresholds/closures
  - `ab.py` — Compare our trapped-ball vs. LineFiller on same line raster
  - `visualise.py` — Debug renderers (colourise labels, overlay panels)
- Depends on: All segmentation and extraction layers
- Used by: `cli.py` for research commands

## Data Flow

### Primary Research Flow (P3 Spike)

1. **Load page** (`segmentation/preprocess.py:load_line_art()`) — Greyscale from file
2. **Segment panels** (`segmentation/panels.py:segment_panels()`) → `PanelBox[]` in reading order
3. **For each panel, for each condition** (extractor + threshold + closure):
   a. Extract lines (`extract/<impl>.extract()`) → greyscale line image
   b. Binarize (`spike/p3.py:_binarise()`) → binary line mask (Otsu or fixed threshold)
   c. Optionally close gaps (`segmentation/closure.py:close_line_gaps()`) → repaired line mask
   d. Segment regions (`segmentation/segmenter.py:segment()`) → int32 label map
   e. Collect stats (`model/masks.py:region_stats()`) → area, bbox per label
   f. Check coverage (`model/masks.py:check_coverage()`) → exhaustiveness, leaks
4. **Aggregate and render** (`spike/p3.py:run_p3()`) → JSON report + debug PNGs
5. **Verdict** (`spike/p3.py:verdict()`) — VIABLE (≤150 regions/panel), MARGINAL, or HATCHING DOMINATES

**State Management:**
- Panels detected once per page, shared across all conditions (ensures comparability)
- Extractor output cached per condition (model load is slow)
- Label maps are immutable; queries read from them without modification
- Reports written incrementally to disk (AB spike resumes on interrupt)

### Segmentation Details (§1.4)

**Our TrappedBall implementation** (`trappedball.py`):
- Expanding disc search at multiple radii (default 3, 2, 1)
- Largest fill at each radius becomes a region
- Smaller fills absorbed into adjacent regions at the next radius
- Can produce "shattered thin corridors" — many small bulges become separate regions

**LineFiller alternative** (`segmenter.py:LineFillerSegmenter`):
- Same radii search, but **discards small fills per radius** (method='max' keeps largest, 'mean' keeps ≥median)
- Then **merges post-hoc** (`merge_fill` iterations) to absorb tiny regions
- Produces fewer regions on hatching-dense pages (Moebius: 612 → 364 structural regions, P3 verdict holds)
- Chosen as default (§1.4 spec); both remain swappable

### Panel Segmentation (§1.1)

**Gutter-based trapped-ball**:
1. Invert line mask (white area)
2. Erode with disc sized to minimum gutter width
3. Flood-fill from page margin through surviving area (gutter network + margin)
4. Dilate back → complement gives panel outlines
5. Filter by size, solidity, connectivity
6. Order reading order (RTL or LTR scan)

**Failure modes (honest, not silent)**:
- Gutters with artwork touching both sides merge into one panel
- Full-bleed pages (no gutters) return whole-page panel
- SFX and figures crossing gutters work fine (ball routes around point obstacles; gutter must be truly disconnected)

## Key Abstractions

**Segmenter Protocol:**
- Purpose: Swap region segmentation implementations without changing pipeline
- Examples: `TrappedBallSegmenter` (`trappedball.py`), `LineFillerSegmenter` (`segmenter.py`)
- Pattern: Each implements `name` property and `segment(line_mask, protected=None) → np.ndarray`
- Return value: int32 label map (0 = line/protected, 1..N = regions)

**LineExtractor Protocol:**
- Purpose: Swap line extraction for domain adapters (§7 Tier 3)
- Examples: `PassthroughExtractor`, `MangaLineExtractor`
- Pattern: Each implements `name` property and `extract(grey) → ExtractionResult`
- Return value: `ExtractionResult.lines` is uint8 greyscale, dark = line

**Label Map as Exact Segmentation Store:**
- One int32 array per panel, size = panel bounding box
- Label 0 = line + protected + unassigned
- Labels 1..N = regions (one per unique label)
- Enforces exclusivity (pixel holds one label) and exhaustiveness (query-checkable)

**Region Entity (No RGB Field):**
- `Region.palette_entry_id` → join to `PaletteEntry` for colour
- Never stores RGB directly
- Supports "change colour everywhere" as single-row update

## Entry Points

**CLI Command: p3**
- Location: `src/comiccolor/cli.py:main()` dispatches to `spike/p3.py:run_p3()`
- Triggers: `comiccolor p3 [pages...] [options]`
- Responsibilities:
  - Load pages (files or directory), validate
  - Run multiple segmentation conditions across them
  - Measure regions per panel, structural counts, coverage
  - Write JSON report + debug renders
  - Print human-readable summary

**CLI Command: ab**
- Location: `src/comiccolor/cli.py:main()` dispatches to `spike/ab.py:run_ab()`
- Triggers: `comiccolor ab [pages...] [options]`
- Responsibilities:
  - Run all three segmenters (TrappedBall, LineFiller no-merge, LineFiller merge)
  - Hold line raster fixed, vary only segmenter
  - Measure region counts per implementation
  - Resume on interrupt (partial reports are useful)
  - Write JSON + debug renders

**Future: Tier 1 Pipeline**
- Not yet integrated; spec describes full orchestration
- Will consume data model (§3) and persistence (`store.py`)
- Will integrate Cobra colour proposer (§1.6, §1.7, §1.8)
- Will produce layered export (§1.10)

## Architectural Constraints

- **Segmentation determinism**: TrappedBall and LineFiller must produce bit-for-bit identical results on same input (for A/B testing). Both are deterministic; no randomness.
- **Label map immutability**: Spike code does not modify label maps; only reads and queries. Edits (merge, split) are future (§1.9 region editor).
- **Protected mask handling**: Passed as additional line mask to segmenters; never filled, come back as label 0 (same as line).
- **Exhaustiveness tracking**: Coverage checks done per spike; stored in reports. Future incremental propagation (§6) depends on data model already being exact.
- **No model in segmentation**: Segmentation layer is deterministic geometry only. Learning happens in extraction (§1.2, §1.6, §1.7 future). §9 anti-pattern: do not use SAM for segmentation.

## Anti-Patterns

### Baking RGB into Region

**What happens:** Region entity carries `rgb: tuple[int, int, int]` field.

**Why it's wrong:** Changes "colour this region" to a per-region operation. Changing a character's hair colour now requires updating every region storing that hair tone. No single source of truth. Volume-level palette edits do not propagate.

**Do this instead:** Store only `palette_entry_id` (foreign key). PaletteEntry holds RGB, versioned (see `model/entities.py:PaletteEntry.revision`). One update changes colour everywhere. Required by spec §3 and enforced structurally in `store.py` SCHEMA.

### Using Learned Segmentation (SAM)

**What happens:** Use a class-agnostic instance segmenter to find regions.

**Why it's wrong:** Instance segmentation and region labeling are different problems with different failure modes. SAM is good at instance retrieval but worse than deterministic trapped-ball on clean line art. The real problem is *labeling* regions (assigning palette entries), not finding them. Substituting SAM buys training cost and inference cost but no accuracy gain. (See §9, spec.)

**Do this instead:** Keep segmentation deterministic (exact masks from trapped-ball). Label regions with learned identity matching (future: Cobra reference module in §1.6). Two separate problems, two separate solutions.

### Conflating Segmentation and Labeling

**What happens:** Treat region finding and region identification as one stage. Render diffusion output directly; skip deterministic segmentation.

**Why it's wrong:** Geometric and semantic problems have different error modes and different fixes. If segmentation makes a false boundary, you need morphological fixes. If labeling assigns the wrong palette entry, you need model confidence and review. Merging them makes it impossible to tell which stage failed and makes the pipeline opaque.

**Do this instead:** Keep an inspectable boundary. Segmentation outputs exact label map (§3), which is persisted as the layer file. Labeling (Cobra proposal + mode snapping + triage) happens downstream and can be redone without re-segmenting. (See §9, spec.)

### Silent Colour Snapping

**What happens:** Mode extraction finds a colour that does not match any PaletteEntry. Snap to the nearest one anyway and assign silently.

**Why it's wrong:** A new outfit or unregistered prop gets coerced into an existing palette entry and the artist does not notice. Silent wrong snapping is worse than an empty region.

**Do this instead:** Reject before snapping. If distance > threshold, create a new PaletteEntry with status='flagged' and route to review. Artist sees it in triage. (Spec §1.7.)

## Cross-Cutting Concerns

**Logging:** No structured logging yet. Debug mode (`--no-debug` flag) controls render output. Future: metrics logged per spike (regions/panel, ink fraction, timing).

**Validation:** Panel detection validates size, solidity, frame closure. Segmenter output checked for coverage (exhaustiveness, leaks). Region stats computed to diagnose hatching (texture_share = regions-structural / total_regions).

**Error Handling:** CLI validates input files early. Missing weights for MangaLineExtraction raises FileNotFoundError. Missing LineFiller vendored code raises FileNotFoundError with clear path suggestion. Reports written incrementally so partial data survives crashes (AB spike).

---

*Architecture analysis: 2026-08-02*
