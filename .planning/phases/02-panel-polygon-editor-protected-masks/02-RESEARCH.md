# Phase 2: Panel Polygon Editor & Protected Masks - Research

**Researched:** 2026-08-16
**Domain:** Deterministic CV (OpenCV) for panel/bubble geometry, hand-rolled HTML5 Canvas 2D editor, SQLite schema evolution, forward-only pipeline stage wiring
**Confidence:** MEDIUM-HIGH — backend geometry (D-17/D-18/D-22/D-23) builds directly on code already read in this session; frontend canvas patterns are well-established web platform APIs (HIGH) but this project's specific hand-rolled implementation has no direct precedent to point at (MEDIUM); the bubble-detection algorithm's real-world precision on the project's actual pages is unverified (LOW, flagged).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-17: Panels arrive as a 4-vertex box seed, never a traced contour.** `segment_panels()` already has the component shape in hand and keeps only the bounding box; tracing it with `findContours` + `approxPolyDP` was considered and rejected. On a *borderless* panel `_gutter_network` cannot be blocked by a frame, so the surviving component is the ink silhouette of the drawing itself — tracing yields a polygon shaped like the character, not the panel. `Panel.polygon` (`entities.py:116`) already exists and is unused; seed it with the four box corners.
- **D-18: Lower `PanelParams.min_solidity` so borderless panels are proposed at all.** `panels.py:97`'s floor silently discards ink-silhouette components today. Lower it, propose a bounding box around whatever survives, and let the artist delete false proposals. Over-propose and let the artist remove noise, rather than under-propose and make them draw from scratch.
- **D-19: Correction is by vertex editing — move, add, delete — plus draw-from-scratch and delete-panel.** This is PAN-02/PAN-03 and it is the load-bearing mechanism, not a fallback.
- **D-20: `ProtectedMask` moves from panel scope to page scope, clipped per panel at use.** Store against `page_id`; each stage clips the page mask to the panel it is working on. One bubble stays one object. Phase 2 is the only phase in which protected masks exist so far, so no downstream consumer breaks.
- **D-21: Protection means "never coloured", not "content preserved".** Export is colour patches only. A protected area never receives a palette entry, so no patch is ever emitted there. PROT-04 verifies as one flat property — no emitted colour patch overlaps a protected mask — not as an integrity invariant threaded through four phases. `Segmenter.segment(line_mask, protected=...)` already returns protected pixels as label 0.
- **D-22: A bubble is text surrounded by white — detect the text, then fill.** Algorithm: (1) detect glyphs, (2) flood-fill the enclosing white outward from the text as seed, (3) cap by maximum area, (4) discard when the text sits on a large white fill or on a coloured area.
- **D-23: This needs text *detection*, not OCR.** Connected-component analysis in OpenCV: small dark blobs of similar height, aligned on a baseline, sitting on locally uniform light ground. Read `Rabbit1010/Speech-Bubble-Aware-Automatic-Comic-Colorization` before implementing — direct precedent for the pipeline shape (not the detector choice).
- **D-24: SFX lettering gets no automatic proposal this phase.** User's explicit call. PROT-02 hand-drawing still covers it fully.
- **D-25: No learned bubble detector, and none is bundled.** Surveyed and rejected on licence (GPL-3.0/Manga109 encumbrance/OpenRAIL conflict), not on quality. If ever added, it belongs behind an optional seam, distributing no restricted weights.
- **D-26: Hand-rolled 2D canvas — no Konva, no runtime frontend dependency.** STACK.md's own Konva recommendation is deliberately rejected: Konva's stage scale/position model would fork `frontend/src/geometry/transform.ts`, the single coordinate authority success criterion 2 depends on. Vertex hit-testing is a distance check against `transform.ts`; drag handles are a few hundred lines. Phase 1's zero-runtime-dependency frontend stays intact.
- **Scope reduction:** automatic *proposal* of SFX lettering is deferred to a later version (D-24). PROT-01 and roadmap criterion 4 are read as "speech bubbles" (not "speech bubbles and SFX") for the automatic half.

### Claude's Discretion (decided in 02-UI-SPEC.md)

- **Screen and gate structure** — decided: one screen, two sequential tool modes, two sequential confirmation gates (not two routed screens). `page.stage` (`"panels"`/`"protected"`) drives the toolbar's tool-mode control, kind-selector, and primary CTA.
- **Reading order configurability** — decided: stays a backend parameter to `_reading_order()`, defaulting left-to-right, exposed only as a non-interactive toolbar readout this phase. Not a per-project setting yet.
- **Undo inside the panel editor** — decided: minimal, session-only, undo-only (no redo), 20-op cap per tool mode, cleared on tool-mode switch or gate confirm. Phase 3 formally owns the real history model; do not pre-build it.

### Deferred Ideas (OUT OF SCOPE)

- **SFX lettering auto-proposal** — deferred to a later version (D-24).
- **DeepPanel** (Apache-2.0) — not adoptable now: no trained weights in the Python repo, needs TensorFlow in a torch-based project, groups panels a colourist needs kept apart.
- **Learned bubble detectors** (`kitsumed/yolov8m_seg-speech-bubble`, `dmMaze/comic-text-detector`, `huyvux3005/manga109-segmentation-bubble`, Roboflow `pers-kdqu3/manga-speech-bubble-detection-1rbgq`) — surveyed and rejected on licence (GPL-3.0 or Manga109 research-only terms), not quality.
- **Roadmap/requirements amendment** — PROT-01 and roadmap criterion 4 should be reworded for the SFX deferral as a deliberate act, not done inside discuss-phase or this research.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|---------------------|
| PAN-01 | App detects panels on a page and presents them as polygons in reading order | Pattern 1 (box-to-polygon seeding, D-17/D-18); `_reading_order()` already implemented in `panels.py`, unchanged |
| PAN-02 | User can drag, add and delete a polygon's vertices to correct a detected panel | Pattern 5 (commit-on-release), hitTest/polygonState module structure, `screenToLabelMap`/`labelMapToScreen` (existing) |
| PAN-03 | User can draw a panel the detector missed, and delete one it invented | Same editor interaction vocabulary as PAN-02 (D-19); no-confirmation delete pattern (D-19/§5) |
| PROT-01 | App detects speech bubbles (SFX deferred, D-24) and proposes them as protected masks | Pattern 2 (text-seeded flood fill, D-22/D-23), Pattern 3 (contour tracing to editable polygon) |
| PROT-02 | User can draw a protected mask by hand where detection missed one | Same hand-rolled canvas editor as panels (D-26), shared `polygonState.ts`/`hitTest.ts` |
| PROT-03 | User can reshape or delete a proposed protected mask | "Touched" state field (`ProtectedMask.touched`), same vertex-edit vocabulary as PAN-02 |
| PROT-04 | Protected regions are excluded from every fill and colour stage and reach export untouched | Pattern 4 (rasterize-at-use, D-21), existing `Segmenter.segment(protected=...)` mechanism, Pitfall 4 (page-space vs panel-local coordinates) |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Deployment**: single machine, local web app — no auth/multi-user concerns apply to this phase's routes (matches Phase 1's existing `get_current_project_path`/`get_store` model, reused unchanged).
- **Tech stack**: Python 3.11+, numpy/opencv/scipy/pillow, SQLite, pytest — this phase introduces zero new backend dependencies (confirmed above) and stays entirely within the pinned stack.
- **Data model**: Regions store `palette_entry_id`, never RGB — not touched by this phase (Regions aren't created until Phase 3's zone editor), but the same "no colour baked into geometry" spirit applies to `ProtectedMask`, which stores no colour either.
- **Evaluation**: Real ink layers, never extracted lines — bubble detection (D-22/D-23) and panel detection (D-17/D-18) must be validated against real page ink at UAT time, not synthetic/extracted-line test fixtures, consistent with the project's existing evaluation stance.
- **Naming/code style conventions** (from the codebase-conventions section of the project's technical CLAUDE.md): snake_case functions/variables, complete type hints with `X | None` union syntax, dataclasses for data structures, Protocol classes for swappable interfaces (the bubble proposer should follow `Segmenter`'s existing protocol shape per CONTEXT.md's own "Established Patterns" note), docstrings explaining WHY with `§` section references, `SystemExit`/specific exceptions for CLI errors, no `__all__` lists at module level.
- **GSD workflow enforcement** (from the user's global CLAUDE.md): all implementation work for this phase must go through `/gsd-execute-phase` once planned — this research document does not itself authorize any file edits.

## Summary

Phase 2 has almost no open design questions — 02-CONTEXT.md (D-17..D-26) and 02-UI-SPEC.md already pin the algorithm, the data model shape, and the interaction contract in detail. What remains is HOW: wiring `Panel.polygon` (unused since Phase 1) into `segment_panels()`'s output, moving `ProtectedMask` from `panel_id` to `page_id` in both the dataclass and the SQLite schema, implementing D-22's text→flood-fill bubble detector on top of tools already vendored (`trappedball.py`'s disc erosion, OpenCV connected components), and hand-building a `<canvas>` 2D vertex editor against `frontend/src/geometry/transform.ts` with no third-party canvas library (D-26 explicitly overrides research's own Konva recommendation).

The one real design gap CONTEXT.md and 02-UI-SPEC.md leave implicit: **a detected bubble mask is a raster blob (from flood fill), but the editor's interaction contract requires it be a vertex polygon** ("Same interaction vocabulary as panels — move/add/delete vertex..."). Unlike D-17's panel decision (which explicitly rejects contour tracing because a box is the right target shape), a protected mask's shape genuinely *is* its traced outline — there is no equivalent "borderless" failure mode here, because a bubble's white-fill boundary is exactly what should be protected. So `cv2.findContours` + `cv2.approxPolyDP` on the detector's binary mask, to produce an editable vertex list, is the correct and necessary step this phase — the planner should treat it as new work, not something D-17 already forbids by extension.

The other real gap: Phase 1's frontend test harness (`vitest.config.ts`, `environment: "node"`, zero DOM tests — WR-14, already flagged as a blocker in STATE.md) cannot exercise a `<canvas>` element at all. `jsdom`'s `HTMLCanvasElement.getContext('2d')` returns `null` by default; making it return a real 2D context requires the `canvas` npm package, which needs native Cairo bindings — a real risk on this project's single Windows dev machine (PITFALLS.md Pitfall 16) and a new *runtime-adjacent* dependency that sits uncomfortably next to D-26's "three audited dev packages" framing. The recommended path is below (Validation Architecture section): test the pure geometry/reducer logic and DOM wiring (event listeners attached, ARIA labels present, toolbar state) under `jsdom`, and leave actual canvas pixel correctness to manual UAT, exactly as Phase 1 already does for the page image element.

**Primary recommendation:** Implement panel polygons as box-seeded 4-vertex lists (D-17/D-18) and protected masks as contour-traced, `approxPolyDP`-simplified vertex lists (new, not directly named by CONTEXT.md but required by 02-UI-SPEC.md's shared interaction vocabulary); persist both as polygon vertex JSON (mirroring `Panel.polygon`'s existing column shape); rasterize with `cv2.fillPoly` at use time for the segmenter's `protected=` boolean array; build the editor as one hand-rolled `<canvas>` 2D-context component driven entirely through `screenToLabelMap`/`labelMapToScreen`, using `requestAnimationFrame` redraw-on-mutation (never redraw-per-mousemove-write, per T-01-FLOOD) and Pointer Events (not mouse events) for stylus/mouse parity.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Panel box detection (`segment_panels`) | API/Backend | — | Deterministic CV, already exists in `segmentation/panels.py`; no client-side geometry computation |
| Panel polygon persistence (vertex edits) | API/Backend | Browser/Client | Client renders and hit-tests locally (D-26); server is system of record via synchronous per-mutation writes (PROJ-05) |
| Vertex drag/add/delete interaction | Browser/Client | — | Pure client-side canvas interaction; only commits (not every frame) reach the API |
| Coordinate transform (screen↔label-map) | Browser/Client | — | `transform.ts`, already built, pure math, no DOM/network |
| Bubble text detection + flood fill | API/Backend | — | OpenCV connected-components + flood fill, deterministic, server-side (matches `panels.py`/`trappedball.py` precedent) |
| Bubble mask → editable polygon (contour trace) | API/Backend | — | `cv2.findContours`/`approxPolyDP` runs once, server-side, at detection time — result ships to client as vertices, not a raster |
| Protected-mask rasterization for segmentation exclusion | API/Backend | — | `cv2.fillPoly` from stored polygon → boolean array consumed by `Segmenter.segment(protected=...)` |
| Protected-mask clip-at-use (page→panel) | API/Backend | — | D-20/D-21: clipping happens per stage that reads protected masks, not stored per-panel |
| Reading-order sort (`_reading_order`) | API/Backend | — | Already implemented, pure function, stays server-side per D-26 discretion call |
| In-editor undo stack (session-only) | Browser/Client | — | D-19/§6: client-only, cleared on tool-mode switch or gate confirm, never persisted |
| Label-map exhaustiveness invariant | API/Backend | — | `masks.py:assert_invariant` — not applicable to protection per D-21, but panels still bound the fillable area |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| opencv-python-headless | >=4.10 (5.0.0 installed, [VERIFIED: local `python -c "import cv2; print(cv2.__version__)"` → `5.0.0`]) | `findContours`, `approxPolyDP`, `fillPoly`, `MSER_create`, `connectedComponentsWithStats`, morphology — every geometric operation this phase needs | Already the project's sole CV dependency; nothing new to add |
| numpy | >=2.0 (existing pin) | Boolean mask arithmetic, polygon vertex arrays | Existing dependency |
| No new frontend runtime package | — | Canvas editor built on native `<canvas>` 2D context + Pointer Events | D-26 is explicit and binding: no Konva, no canvas library, zero new runtime dependency |

**No new packages are introduced by this phase** — backend uses only opencv/numpy/scipy already pinned in `pyproject.toml`; frontend stays at zero runtime dependencies (D-26). The Package Legitimacy Audit below is a formality confirming this, not a gate on anything new.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `cv2.MSER_create()` | bundled in opencv-python-headless (no separate `opencv-contrib` needed — [VERIFIED: local check, `hasattr(cv2, 'MSER_create')` → `True` on the installed 5.0.0 build]) | Optional alternative/supplement to plain connected-components for glyph candidate detection in D-23's text step | Only if plain `connectedComponentsWithStats` height/baseline/uniformity filtering (as D-23 specifies) proves too noisy in practice — MSER is a documented fallback, not the primary path D-23 names |
| `scipy.ndimage` | >=1.14 (existing pin) | Already used in `trappedball.py`'s `expand_under_lines`; not newly needed by Phase 2 but available if bubble hole-filling needs `binary_fill_holes` | Optional, D-22's flood-fill-outward from text is the specified mechanism; scipy fill-holes is an alternative shape only if flood fill from an ambiguous seed proves unreliable |

**Note on `cv2.text` / `cv2.ximgproc`:** these modules (which would carry proper scene-text-detection classes like EAST wrappers) are **not present** in this project's `opencv-python-headless` build — [VERIFIED: local check, `hasattr(cv2, 'text')` → `False`, `hasattr(cv2, 'ximgproc')` → `False`]. This is irrelevant to D-22/D-23's design (which deliberately avoids any learned text detector, per D-25's licence stance), but rules out ever reaching for `cv2.text.TextDetectorCNN` as a shortcut without first vendoring `opencv-contrib-python` and re-litigating D-25.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Contour tracing + `approxPolyDP` for bubble polygons | Store bubble masks as raw raster only, render as a non-editable overlay | Rejected by 02-UI-SPEC.md §3, which requires the same vertex-edit vocabulary as panels ("move/add/delete vertex... reused verbatim") |
| Hand-rolled `<canvas>` editor | Konva.js 9.x (STACK.md's own HIGH-confidence recommendation) | Explicitly rejected by D-26 — a second coordinate-space model would fork `transform.ts`'s single source of truth |
| `cv2.findContours` for panel polygons | Keep panels as 4-vertex box seeds (D-17, chosen) | D-17 already settled this: tracing destroys the borderless-panel case, which the project's Franco-Belgian test material actively exercises |
| Deterministic text-then-flood bubble detection (D-22) | A learned bubble segmentation model (surveyed in `<deferred>`: `kitsumed/yolov8m_seg-speech-bubble`, `dmMaze/comic-text-detector`, Roboflow) | All surveyed options are GPL-3.0/non-permissive or Manga109-encumbered; conflicts with OpenRAIL++-M distribution per D-25's licence analysis |

**Installation:** none — no new packages this phase.

**Version verification:** OpenCV verified locally against the actual project virtualenv (`python -c "import cv2; print(cv2.__version__)"` → `5.0.0`, well above the `>=4.10` pin; all APIs named above — `findContours`, `approxPolyDP`, `fillPoly`, `MSER_create`, `connectedComponentsWithStats` — confirmed present via `hasattr` on this exact installed build, not assumed from training data).

## Package Legitimacy Audit

Not applicable — this phase adds no new packages to either `pyproject.toml` or `frontend/package.json`. Backend work uses `opencv-python-headless`, `numpy`, `scipy` (all already pinned and installed); frontend work adds zero runtime dependencies per D-26, and no new devDependencies beyond what Phase 1 already installed (`typescript`, `vite`, `vitest`) unless the Validation Architecture section's jsdom recommendation is adopted (see below — flagged there, not silently added here).

**Packages removed due to slopcheck [SLOP] verdict:** none (nothing evaluated — no new packages).
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
Artist's browser                              FastAPI backend
┌─────────────────────────────┐               ┌──────────────────────────────┐
│  Page editor (one screen)    │               │  routers/panel.py (new)      │
│  ┌─────────────────────────┐ │  GET page     │  routers/protected.py (new)  │
│  │ <canvas> raster layer   │◄┼───────────────┤                              │
│  │ (page image, full-bleed)│ │               │  panel: box → polygon seed   │
│  ├─────────────────────────┤ │  GET panels   │  (D-17/D-18: segment_panels  │
│  │ polygon overlay layer   │◄┼───────────────┤   + PanelParams tuning)      │
│  │ (Panels OR Protected,   │ │               │                              │
│  │  D-26 hand-rolled draw) │ │  GET protected│  protected: text-detect →    │
│  ├─────────────────────────┤ │◄──────────────┤  flood-fill → area-cap →     │
│  │ handles + hover ghosts  │ │               │  findContours+approxPolyDP   │
│  └─────────────────────────┘ │  PATCH vertex │  (D-22/D-23, new pipeline)   │
│           │ pointerdown/move/up│ (on mouseup) │                              │
│           ▼                   ├──────────────►  Store.update_panel_polygon  │
│  transform.ts                 │               │  Store.update_protected_    │
│  screenToLabelMap /            │               │    mask_polygon (new)       │
│  labelMapToScreen (shared,     │  POST confirm │                              │
│  zoom-invariant, D-26)         ├──────────────►  page.stage transition       │
│                                 │  gate         │  (panels→protected→zones)  │
│  undo stack (session, client)  │               │                              │
└─────────────────────────────┘               │  Segmenter.segment(          │
                                                │    line_mask, protected=)    │
                                                │  ← protected rasterized via  │
                                                │    cv2.fillPoly at use time, │
                                                │    clipped page→panel (D-20/│
                                                │    D-21)                     │
                                                └──────────────────────────────┘
```

### Recommended Project Structure

```
src/comiccolor/
├── segmentation/
│   ├── panels.py              # existing: segment_panels() gains polygon seeding (D-17/D-18)
│   └── bubbles.py             # NEW: detect_bubbles() — D-22/D-23 text→flood→contour pipeline
├── model/
│   ├── entities.py            # Panel.polygon already exists; ProtectedMask gains page_id, polygon, touched
│   └── store.py               # SCHEMA migration: protected_mask.panel_id → page_id; polygon column; touched column
├── pipeline/
│   └── stages.py              # panels/protected Stage.runner filled in (currently None, D-11)
└── web/
    ├── routers/
    │   ├── panel.py            # NEW: panel CRUD (list/create/patch-vertex/delete), gate confirm
    │   └── protected.py        # NEW: protected-mask CRUD, gate confirm, bubble-detection trigger
    └── schemas.py              # NEW request/response models for both routers

frontend/src/
├── geometry/
│   └── transform.ts           # existing, unchanged, single coordinate authority (D-26)
├── editor/                    # NEW
│   ├── canvasEditor.ts        # mount/draw loop, layer z-order, pan/zoom (§9/§10 of UI-SPEC)
│   ├── polygonState.ts        # pure reducer: vertex move/add/delete, draw-in-progress state
│   ├── hitTest.ts             # pure: distance-based vertex/edge hit-testing against transform.ts
│   └── undoStack.ts           # pure: 20-op session stack, inverse-replay (§6 of UI-SPEC)
└── views/
    └── pageEditor.ts          # NEW: the one-screen, two-tool-mode, two-gate screen (§1 of UI-SPEC)
```

### Pattern 1: Box-to-polygon seeding for panels (D-17)

**What:** `segment_panels()` already computes `PanelBox(x, y, width, height)`. Seed `Panel.polygon` with the four corners in a fixed winding order.
**When to use:** Every panel detection run, before persistence.
**Example:**
```python
# src/comiccolor/segmentation/panels.py — extend PanelBox or the call site
def box_to_polygon(box: PanelBox) -> list[tuple[int, int]]:
    """D-17: seed with the box corners, clockwise from top-left.
    Never call findContours here — see the module's rejected-alternatives note."""
    return [
        (box.x, box.y),
        (box.x + box.width, box.y),
        (box.x + box.width, box.y + box.height),
        (box.x, box.y + box.height),
    ]
```

### Pattern 2: Text-seeded flood fill for bubble detection (D-22/D-23)

**What:** Detect glyph-like connected components (small, similar height, baseline-aligned, sitting on locally uniform light ground), then flood-fill the enclosing white outward from the text as seed, capped by max area.
**When to use:** Bubble-detection runner, triggered on Panels-gate confirm (per 02-UI-SPEC.md §4).
**Example:**
```python
# src/comiccolor/segmentation/bubbles.py (new module)
import cv2
import numpy as np

def _glyph_candidates(grey: np.ndarray, line_mask: np.ndarray) -> np.ndarray:
    """Small dark blobs of similar height, roughly baseline-aligned.
    D-23: connected-component filters reject hatching (irregular height,
    no baseline) without needing OCR or a learned detector."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        line_mask.astype(np.uint8), connectivity=8
    )
    heights = stats[1:, cv2.CC_STAT_HEIGHT]
    if heights.size == 0:
        return np.zeros_like(line_mask)
    median_h = float(np.median(heights))
    glyph_mask = np.zeros_like(line_mask)
    for i in range(1, count):
        h = stats[i, cv2.CC_STAT_HEIGHT]
        w = stats[i, cv2.CC_STAT_WIDTH]
        area = stats[i, cv2.CC_STAT_AREA]
        # height within a band of the page's dominant small-glyph height;
        # reject long straight runs (panel frames, speed lines) by aspect ratio
        if 0.4 * median_h <= h <= 2.5 * median_h and w < 4 * h and area > 2:
            glyph_mask |= labels == i
    return glyph_mask

def detect_bubbles(
    grey: np.ndarray,
    line_mask: np.ndarray,
    max_area_frac: float = 0.35,
) -> list[np.ndarray]:
    """Returns one boolean mask per detected bubble.

    Discards a fill that reaches the area cap (D-22 point 3: an unclosed
    bubble leaking along a gutter) and any candidate whose seed sits on
    already-dark/coloured ground (D-22 point 4: lettering on artwork)."""
    glyphs = _glyph_candidates(grey, line_mask)
    if not glyphs.any():
        return []

    count, glyph_labels = cv2.connectedComponents(glyphs.astype(np.uint8), connectivity=8)
    height, width = grey.shape
    max_area = max_area_frac * height * width
    bubbles: list[np.ndarray] = []

    # Cluster nearby glyphs (dilate to merge same-bubble text lines) before
    # flood-filling — a bubble is filled once from its whole text block, not
    # once per character, or every glyph reopens the same fill redundantly.
    clustered = cv2.dilate(glyphs.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    cluster_count, cluster_labels = cv2.connectedComponents(clustered.astype(np.uint8), connectivity=8)

    for cluster_id in range(1, cluster_count):
        seed_mask = (cluster_labels == cluster_id) & glyphs
        ys, xs = np.nonzero(seed_mask)
        if ys.size == 0:
            continue
        seed = (int(xs[0]), int(ys[0]))

        # D-22 point 4: discard text sitting on already-large-white or
        # coloured ground — check the immediate surround, not the seed pixel
        # itself (the seed pixel is ink, by construction).
        flood_mask = np.zeros((height + 2, width + 2), np.uint8)
        fill_target = (~line_mask).astype(np.uint8) * 255
        cv2.floodFill(
            fill_target, flood_mask, seed, 128,
            loDiff=0, upDiff=0, flags=4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8),
        )
        filled = flood_mask[1:-1, 1:-1].astype(bool)
        area = int(filled.sum())
        if area == 0 or area > max_area:
            continue  # unclosed bubble or no white to fill at all
        bubbles.append(filled)

    return bubbles
```
*(Illustrative — the planner should verify `cv2.floodFill`'s mask/seed semantics against the installed 5.0.0 build directly before shipping; flood-fill mask conventions have changed across OpenCV major versions historically and this snippet is [ASSUMED] on the exact flag combination, not verified against a real page in this research session.)*

### Pattern 3: Contour tracing for editable bubble polygons

**What:** A detected bubble is a raster mask; the editor needs vertices. Trace and simplify.
**When to use:** Immediately after `detect_bubbles()`, before persisting `ProtectedMask.polygon`.
**Example:**
```python
def mask_to_polygon(mask: np.ndarray, epsilon_frac: float = 0.01) -> list[tuple[int, int]]:
    """Outer contour, simplified to a manageable vertex count for hand-editing.
    epsilon_frac ~1% of perimeter is a conventional starting point for
    approxPolyDP on organic (non-CAD) shapes — tune against real bubble
    outlines, this default is [ASSUMED], not tuned on project data."""
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return []
    largest = max(contours, key=cv2.contourArea)
    epsilon = epsilon_frac * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    return [(int(p[0][0]), int(p[0][1])) for p in approx]
```

### Pattern 4: Rasterize-at-use for the segmenter's `protected=` array (D-21)

**What:** Polygons are the stored/edited representation; the segmenter needs a boolean array. Convert only at the point of use, clipped page→panel.
**Example:**
```python
def rasterize_protected_for_panel(
    masks: list[list[tuple[int, int]]],  # page-space polygons
    panel_x: int, panel_y: int, panel_w: int, panel_h: int,
) -> np.ndarray:
    """D-20/D-21: protected masks are stored at page scope; each stage
    clips to the panel it is working on. Translate to panel-local
    coordinates before filling — never store a second, panel-scoped copy."""
    out = np.zeros((panel_h, panel_w), dtype=np.uint8)
    for polygon in masks:
        local = np.array(
            [[x - panel_x, y - panel_y] for x, y in polygon], dtype=np.int32
        )
        cv2.fillPoly(out, [local], 1)
    return out.astype(bool)
```

### Pattern 5: Commit-on-release, not commit-on-move (T-01-FLOOD precedent)

**What:** Vertex drag renders every frame locally; the API write fires once, on `pointerup`.
**When to use:** Every mutating interaction in the canvas editor — mirrors `swatchCard.ts`'s `picker.addEventListener('change'/'blur', commitRecolour)` pattern exactly, one layer down (canvas instead of a native input).
**Example:**
```typescript
// frontend/src/editor/canvasEditor.ts — sketch, not final shape
canvas.addEventListener("pointerdown", (e) => {
  const hit = hitTestVertex(screenToLabelMap({ x: e.offsetX, y: e.offsetY }, viewport), state);
  if (hit) dragState = { vertexId: hit.id, originalPos: hit.pos };
});
canvas.addEventListener("pointermove", (e) => {
  if (!dragState) return;
  const p = screenToLabelMap({ x: e.offsetX, y: e.offsetY }, viewport);
  state = movePolygonVertexLocally(state, dragState.vertexId, p); // pure, no fetch
  requestAnimationFrame(() => draw(ctx, state, viewport));
});
canvas.addEventListener("pointerup", async () => {
  if (!dragState) return;
  await api.panels.updateVertex(panelId, dragState.vertexId, currentVertexPos(state, dragState.vertexId));
  pushUndo({ kind: "move", vertexId: dragState.vertexId, from: dragState.originalPos });
  dragState = null;
});
```

### Anti-Patterns to Avoid

- **Writing on every `pointermove`:** floods the write path exactly like T-01-FLOOD in Phase 1's colour picker — commit only on `pointerup`/`change`.
- **Introducing a second coordinate-transform implementation:** any temptation to let a canvas library (or a "simpler" ad hoc scale/pan calc) compute screen↔page math independently of `transform.ts` violates D-26 and breaks success criterion 2 by construction.
- **Tracing panel contours with `findContours`:** already rejected by D-17 for the specific, evidenced reason that it destroys borderless panels; do not revisit inside this phase.
- **Treating protection as a content-preservation invariant:** D-21 is explicit — protection means "never receives a palette entry," not "line content survives untouched to export." Do not build an `assert_invariant`-style fail-loud chain for this; a flat "no colour patch overlaps a protected mask" check is correct and sufficient.
- **Storing a second panel-scoped copy of a protected mask:** D-20 moved `ProtectedMask` to page scope specifically to make a bubble spanning two panels one row, not two. Clip at use, in memory, per stage.
- **Confirmation dialogs on delete:** D-19/§5 is explicit that delete is routine, not destructive-confirmed, for panels and protected masks alike — undo (§6) is the safety net, not a modal.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Polygon rasterization | Custom scanline fill | `cv2.fillPoly` | Already vendored, handles self-intersection/winding correctly, used nowhere else yet but zero new dependency cost |
| Contour extraction | Custom boundary trace | `cv2.findContours` + `cv2.approxPolyDP` | Standard, well-tested OpenCV primitives; hand-rolling risks subtle boundary-pixel bugs exactly where PROT-04's "reaches export untouched" claim depends on correctness |
| Text/glyph candidate filtering | A tiny bespoke classifier | `cv2.connectedComponentsWithStats` height/aspect/baseline filters (D-23's own specified shape) | D-23 already names the exact three filters (height similarity, baseline alignment, uniform light ground) — this is a filter pipeline, not a model, and should stay that way |
| Screen↔page coordinate math | Any per-editor reimplementation | `frontend/src/geometry/transform.ts` | D-26 makes this non-negotiable; it is also already unit-tested at 64x/0.05x zoom |
| Undo/redo | Reach for a generic undo library | The narrowly-scoped 20-op inverse-replay stack specified in UI-SPEC §6 | Explicitly descoped from Phase 3's real history model; a library here would be over-engineering for a session-only, undo-only, 20-op cap |

**Key insight:** every "don't hand-roll" item above is actually "don't reach for a new dependency OR a bespoke reimplementation — use the OpenCV primitive or the Phase-1-built module that already exists." This phase's whole shape is assembling existing, already-vendored/-built primitives into two new pipelines (panel polygon, bubble detection) and one new UI surface, not introducing new machinery.

## Common Pitfalls

### Pitfall 1: `approxPolyDP` epsilon tuned wrong shatters or over-smooths bubble outlines

**What goes wrong:** Too small an epsilon produces a bubble polygon with 40+ vertices (unusable to hand-edit, defeats 02-UI-SPEC.md's "tens of vertices, not thousands" framing carried over from D-26's panel-editor sizing assumption); too large an epsilon rounds a bubble's tail/pointer off entirely, changing where the artist would expect to click to select it.
**Why it happens:** `approxPolyDP`'s epsilon is a pixel-distance tolerance, not a vertex-count target, and the "right" value depends on the bubble's absolute pixel size at the page's actual resolution.
**How to avoid:** Scale epsilon as a fraction of contour perimeter (`epsilon_frac * cv2.arcLength(...)`, not a fixed pixel constant), and validate against a handful of real detected bubbles at real page resolution before shipping a default.
**Warning signs:** UAT session where the artist says a bubble "looks jaggy" (epsilon too small) or "lost its tail" (too large).

### Pitfall 2: `cv2.floodFill`'s mask-only flag semantics differ from a naive read of the docs

**What goes wrong:** `cv2.floodFill` with `FLOODFILL_MASK_ONLY` requires a mask 2px larger than the image on every side, and the fill-value-in-high-byte trick (`255 << 8`) for controlling mask fill value is a real but easy-to-get-wrong convention.
**Why it happens:** The OpenCV Python binding's `floodFill` signature is a thin wrapper over a C++ API whose flag-bit-packing convention is not obvious from the Python type signature alone.
**How to avoid:** Write and run a small, real test against the installed 5.0.0 build before trusting the Pattern 2 code sketch above — this research flagged that snippet `[ASSUMED]` for exactly this reason. Prefer testing the flood-fill helper in isolation (`tests/test_bubbles.py`) before wiring it into the full detection pipeline.
**Warning signs:** A bubble mask comes back as the *inverse* of what's expected (whole page filled except the bubble, or vice versa) — a classic symptom of a mis-set mask/fill-value flag.

### Pitfall 3: `jsdom`'s `<canvas>` has no real 2D rendering context

**What goes wrong:** `element.getContext('2d')` returns `null` under plain `jsdom` (Phase 1's `environment: "node"` config doesn't even run jsdom at all — WR-14). Any test that calls `.getContext('2d')` and then draws will throw on the `null` dereference, not silently no-op.
**Why it happens:** `jsdom` deliberately does not implement Canvas 2D rendering; the `canvas` npm package (native Cairo bindings) is the standard way to get real pixel output in a Node test environment, but it requires a native build toolchain — a real friction point on the project's single Windows dev machine (PITFALLS.md Pitfall 16's general Windows-path/tooling caution applies here too).
**How to avoid:** Do not attempt to unit-test actual canvas pixel output. Structure the editor so all *decision* logic (hit-testing, vertex mutation, undo-stack transitions, viewport math) lives in pure, DOM-free, canvas-free TypeScript modules (`hitTest.ts`, `polygonState.ts`, `undoStack.ts` in the structure above) that are fully unit-testable under the existing `node` environment exactly like `transform.ts` already is. Reserve `jsdom` (added as a Wave 0 dev-dependency, not `canvas`) only for asserting DOM structure — element presence, ARIA labels, event listener attachment — never actual rendered pixels. Canvas visual correctness is a manual UAT concern, same as Phase 1's `<img>` element was never pixel-tested.
**Warning signs:** A test file that imports `canvasEditor.ts` directly and calls `getContext('2d')` inside a `node`-environment vitest run — this will fail immediately and is a sign the module boundary between pure logic and canvas rendering was not kept clean.

### Pitfall 4: Protected-mask polygon coordinates must stay page-space, panels stay panel-relative-in-appearance-but-page-space-in-storage

**What goes wrong:** `Panel.x, Panel.y, Panel.width, Panel.height` are page-pixel coordinates (per `entities.py`'s own docstring: "Panel bounds in page pixel coordinates"), and `Panel.polygon` should be seeded in the same page-pixel space, not panel-local space — but the *label map* (`masks.py`) is panel-local, offset by `panelOffset` in `transform.ts`. Mixing these up produces polygons that render correctly at the panel's own zoom but drift the moment a protected mask (page-space) needs to be compared against a panel's label map (panel-local).
**Why it happens:** Two different local coordinate systems are legitimately in play — page space (panels, protected masks) and label-map space (regions within one panel) — and D-20's whole point is that protected masks live in the *page*-space one specifically so a mask can span two panels.
**How to avoid:** Panel and ProtectedMask polygons are always stored in page-pixel space (matching `Panel.x/y/width/height`'s existing convention). Only `rasterize_protected_for_panel` (Pattern 4) or an equivalent panel-clipping step converts to panel-local coordinates, and only at the moment of segmentation use — never persisted that way.
**Warning signs:** A protected mask that renders correctly in the editor (page space, matches `transform.ts`'s `panelOffset: {x:0,y:0}` page-level view) but excludes the wrong pixels once a panel actually segments — check the clip step's origin subtraction first.

### Pitfall 5: SQLite schema migration for `protected_mask.panel_id → page_id` has no existing rows to break, but the column rename needs care anyway

**What goes wrong:** `protected_mask` currently has `panel_id NOT NULL REFERENCES panel(id) ON DELETE CASCADE`. Naively adding a `page_id` column and leaving `panel_id` in place (or dropping it incorrectly) can produce a schema where old code paths silently keep writing to the wrong column, or where `ON DELETE CASCADE` from `page` never fires because the foreign key still points at `panel`.
**Why it happens:** No production data exists yet (Phase 2 hasn't shipped), so this is a pure schema-design decision, not a data migration — but `Store.__init__`'s `CREATE TABLE IF NOT EXISTS` means a stale dev database on the researcher's/planner's own machine (if `comiccolor serve` was ever run against a Phase-1-era project) *will* have the old schema and silently keep it, since `IF NOT EXISTS` never alters an existing table.
**How to avoid:** Since Phase 2 is "the only phase in which protected masks exist so far" (D-20's own words — no downstream consumer breaks), the cleanest path is editing the `CREATE TABLE protected_mask` statement directly in `SCHEMA` (not an `ALTER TABLE` migration) to declare `page_id` from the start, add `polygon TEXT NOT NULL DEFAULT '[]'` and a `touched` column (boolean or enum per UI-SPEC §3's "planner should add" note), and document that any local dev database created before this phase must be deleted and recreated (there is no artist-facing data to preserve yet — v1 has not shipped).
**Warning signs:** `sqlite3.OperationalError: no such column: page_id` on a machine that ran `comiccolor serve` against Phase 1 code — the fix is deleting the stale `project.db`, not writing a migration for data that was never real.

### Pitfall 6: Bubble detection running synchronously on the confirm-click blocks the UI with no feedback path already built

**What goes wrong:** 02-UI-SPEC.md §4 requires "Bubble detection failed — you can still draw protected masks by hand" as a non-blocking inline banner, and a "Detecting speech bubbles…" spinner state between the Panels-confirm click and the Protected canvas becoming interactive. If the runner is wired as a plain synchronous FastAPI route call, a slow or failing detection has to be handled entirely in that one request/response cycle.
**Why it happens:** Phase 1's precedent (`run_import`) is a fast, always-succeeds operation; bubble detection is neither guaranteed fast (page-dependent glyph density) nor guaranteed to succeed cleanly (D-22's own failure modes: unclosed bubbles, ambiguous seeds).
**How to avoid:** Wrap the detection call in a try/except at the route level that still transitions `page.stage` forward (per D-06/D-07's forward-only model — a failed *proposal* is not a failed *stage transition*, since PROT-01 is "detects... and proposes," and PROT-02's hand-drawing is the guaranteed fallback per CONTEXT.md's own framing) and returns a response shape the frontend can render as the inline banner rather than a blocking error. This does not need a background job queue (unlike Phase 4's Cobra worker) — page-scale OpenCV operations are expected to complete within a normal HTTP request, matching Phase 1's existing synchronous-`def`-route convention.
**Warning signs:** An artist's screen stuck on "Detecting speech bubbles…" with no way to proceed — the failure path must always leave the artist able to reach Protected tool mode and draw by hand, per PROT-02's guarantee.

## Code Examples

### Panel and ProtectedMask entity/schema changes

```python
# src/comiccolor/model/entities.py — ProtectedMask, D-20/UI-SPEC §3
@dataclass
class ProtectedMask:
    """§1.2. Frame as protection, not detection.

    D-20: page-scoped, not panel-scoped -- a bubble straddling two panels
    is one row, clipped per panel only at use (see rasterize_protected_
    for_panel in segmentation). D-21: protection means "never coloured,"
    not "content preserved" -- there is no integrity invariant here.
    """
    page_id: int
    kind: ProtectedKind
    polygon: list[tuple[int, int]] = field(default_factory=list)
    id: int | None = None
    # UI-SPEC §3 "touched state": flips false->true the moment the artist
    # reshapes a detector-proposed mask or draws a new one by hand. Dashed
    # outline while False, solid while True. Detector output starts False;
    # a hand-drawn mask starts True.
    touched: bool = False
    area: int = 0
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
```

```sql
-- src/comiccolor/model/store.py SCHEMA — protected_mask, rewritten (no ALTER
-- needed, no shipped data exists yet per D-20's own note)
CREATE TABLE IF NOT EXISTS protected_mask (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id   INTEGER NOT NULL REFERENCES page(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    polygon   TEXT NOT NULL DEFAULT '[]',
    touched   INTEGER NOT NULL DEFAULT 0,
    area      INTEGER NOT NULL DEFAULT 0,
    bbox_x    INTEGER NOT NULL DEFAULT 0,
    bbox_y    INTEGER NOT NULL DEFAULT 0,
    bbox_w    INTEGER NOT NULL DEFAULT 0,
    bbox_h    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_protected_page ON protected_mask(page_id);
```

### Route pattern for panel vertex mutation (mirrors `palette.py`'s PATCH shape)

```python
# src/comiccolor/web/routers/panel.py (new) — sketch matching existing conventions
@router.patch("/{panel_id}/vertex/{vertex_index}", response_model=PanelResponse)
def move_vertex(
    panel_id: int, vertex_index: int, body: VertexUpdateRequest,
    store: Store = Depends(get_store),
) -> PanelResponse:
    panel = store.panel_by_id(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=PANEL_NOT_FOUND_DETAIL)
    if not (0 <= vertex_index < len(panel.polygon)):
        raise HTTPException(status_code=400, detail="Vertex index out of range.")
    store.update_panel_vertex(panel_id, vertex_index, (body.x, body.y))
    updated = store.panel_by_id(panel_id)
    return _panel_response(updated)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `Panel.polygon` field unused, `x/y/width/height` box only | `Panel.polygon` seeded and consumed | This phase | PAN-01/02/03 become implementable; box fields stay for backward-compat bbox queries |
| `ProtectedMask.panel_id`, raster `mask_path` | `ProtectedMask.page_id`, `polygon` vertex list | This phase (D-20, this research) | Enables cross-panel bubbles and vertex editing in one shared editing model with panels |
| `pipeline/stages.py` `panels`/`protected` `runner=None` | Both filled with real runners | This phase (D-11's declared-but-unimplemented state resolved) | First two of eight stages become fully live |

**Deprecated/outdated:** The `mask_path: str` raster-PNG representation on `ProtectedMask` (Phase 1's placeholder shape) is superseded by `polygon: list[tuple[int,int]]`, matching `Panel.polygon`'s existing pattern — do not resurrect the PNG-path shape; it cannot be hand-edited as vertices.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | `cv2.floodFill`'s `FLOODFILL_MASK_ONLY` flag/mask-size/fill-value convention as sketched in Pattern 2 | Code Examples / Pattern 2, Pitfall 2 | Low — caught immediately by a real unit test against the installed OpenCV build before any page-level integration; explicitly flagged for verification, not shipped as fact |
| A2 | `epsilon_frac=0.01` (1% of perimeter) is a reasonable default for `approxPolyDP` on bubble contours | Pattern 3, Pitfall 1 | Medium — a wrong default produces visibly bad polygons in UAT; cheap to tune empirically against 2-3 real detected bubbles before shipping, no architectural risk |
| A3 | `max_area_frac=0.35` for the bubble flood-fill area cap is a workable starting bound | Pattern 2 | Medium — too low silently discards large legitimate bubbles; too high lets an unclosed bubble leak across a gutter (the exact failure D-22 point 3 exists to prevent). Needs validation against real project pages, not shipped as a spec value |
| A4 | Bubble-detection runner can stay a synchronous FastAPI `def` route (no background job queue) at page scale | Pitfall 6 | Low-Medium — if real pages prove slow enough to feel unresponsive, the fix is a loading-state UX tweak (already specified in UI-SPEC), not an architecture change; Phase 4's Cobra worker is the precedent for when a real queue becomes necessary and this is not that scale |
| A5 | Adding `jsdom` as a dev-dependency (for DOM-structure tests only, not canvas pixel tests) is compatible with D-26/Phase 1's "three audited dev packages" framing | Common Pitfalls / Pitfall 3 | Low — `jsdom` is a devDependency, not a runtime dependency, and does not touch D-26's "no Konva, no runtime frontend dependency" constraint, but the planner should treat this as a deliberate small addition to flag, not something to silently skip past |

## Open Questions

1. **Does `_reading_order()`'s tier-based grouping need to re-run live as the artist adds/deletes panels in the editor, or only recompute server-side on each mutation?**
   - What we know: `_reading_order` is a pure function operating on a full box list; UI-SPEC §2 says "Numbering badges always reflect current reading order live as polygons are added/deleted/reordered by position."
   - What's unclear: whether "live" means the client recomputes tiering locally after every edit (requiring `_reading_order`'s logic to be ported to TypeScript, a second implementation) or the client waits for each PATCH/POST/DELETE response to carry updated `reading_order` values for all panels.
   - Recommendation: server recomputes and returns full updated panel list (with `reading_order`) on every mutating panel request — avoids porting geometry logic to TypeScript and avoids a second source of truth, at the cost of one extra round-trip's worth of badge-renumbering latency, which is imperceptible for tens of panels.

2. **What triggers bubble re-detection on Go-Back from Protected to Panels?**
   - What we know: 02-UI-SPEC.md §8 states going back from Protected to Panels "re-runs bubble detection for the whole page," discarding existing protected masks.
   - What's unclear: whether hand-drawn (touched) masks are also discarded on this Go-Back, or only detector-proposed-untouched ones — the example sentence says "discards 4 protected masks," implying all of them, but this seems harsh if the artist hand-drew SFX masks that have nothing to do with panel geometry.
   - Recommendation: treat this as the literal, simple behavior D-08/§8 already describes (discard all protected masks for the page on this Go-Back, matching Phase 1's general "going back is costed and explicit" framing) — the alternative (partial preservation) adds real complexity for a destructive action the artist already sees a specific numeric warning for before confirming.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| opencv-python-headless | Panel/bubble geometry (all of D-17/D-18/D-22/D-23) | ✓ | 5.0.0 [VERIFIED: local import check] | — |
| numpy | Mask/array arithmetic | ✓ | pinned >=2.0 | — |
| Node.js / npm | Frontend build/test | ✓ (Phase 1 already builds/tests successfully per STATE.md: "144 py + 61 fe tests green") | not independently re-checked this session; inherited from Phase 1's working build | — |
| `canvas` npm package (native Cairo) | Real pixel-level canvas test rendering | Not installed, not recommended | — | Test pure logic + DOM structure only (Pitfall 3); do not add this package |

**Missing dependencies with no fallback:** none — every dependency this phase needs is already installed and verified.

**Missing dependencies with fallback:** `canvas` (native Cairo bindings) is deliberately not installed; the fallback (pure-logic + DOM-structure testing under `jsdom`, manual UAT for pixel correctness) is the recommended path, not a workaround for a missing tool.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest 8.0+ (existing, `pyproject.toml` `[tool.pytest.ini_options]`) |
| Backend config file | `pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["src"]`) |
| Frontend framework | vitest ^4.1.10 (existing, `frontend/vitest.config.ts`) |
| Frontend config file | `frontend/vitest.config.ts` — currently `environment: "node"` project-wide; **Wave 0 gap:** needs a `jsdom`-environment path for new DOM-structure tests (see Pitfall 3) |
| Quick run command (backend) | `pytest tests/test_panels.py tests/test_bubbles.py -x` |
| Quick run command (frontend) | `npm run test -- editor` (once `frontend/tests/editor/` exists) |
| Full suite command (backend) | `pytest tests/` |
| Full suite command (frontend) | `npm run test` (from `frontend/`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| PAN-01 | Panels detected, presented as polygons in reading order | unit | `pytest tests/test_panels.py::test_finds_every_panel_in_a_grid -x` (existing coverage of `segment_panels`) + new `pytest tests/test_panels.py::test_boxes_seed_four_vertex_polygons -x` | ✅ existing test file / ❌ new test, Wave 0 |
| PAN-02 | Drag/add/delete a polygon's vertices | unit (backend mutation) + unit (frontend reducer) | `pytest tests/test_web/test_panel_routes.py -x` + `npm run test -- polygonState` | ❌ Wave 0 (both) |
| PAN-03 | Draw a panel from scratch, delete an invented one | unit + integration | `pytest tests/test_web/test_panel_routes.py::test_create_and_delete_panel -x` | ❌ Wave 0 |
| PROT-01 | Bubbles detected and proposed as protected masks | unit | `pytest tests/test_bubbles.py -x` | ❌ Wave 0 — new module, no test file yet |
| PROT-02 | Hand-draw a protected mask where detection missed | unit | `pytest tests/test_web/test_protected_routes.py::test_create_mask_by_hand -x` | ❌ Wave 0 |
| PROT-03 | Reshape or delete a proposed mask | unit + frontend | `pytest tests/test_web/test_protected_routes.py::test_reshape_and_delete -x` + `npm run test -- polygonState` | ❌ Wave 0 |
| PROT-04 | Protected regions excluded from every fill/colour stage, incl. panel-boundary/SFX-crossing cases | unit (segmenter contract) | `pytest tests/test_trappedball.py::test_protected_pixels_stay_unassigned -x` (extend existing file) + new cross-panel-boundary case | ✅ existing file / ❌ new boundary-crossing test case, Wave 0 |
| Success criterion 2 (zoom-invariant correction) | Corrections hold at every zoom level via the shared transform | unit | `npm run test -- transform` (existing, extend with polygon-specific round-trip cases) + `npm run test -- hitTest` (new) | ✅ existing `transform.test.ts` / ❌ new `hitTest.test.ts`, Wave 0 |

### Sampling Rate

- **Per task commit:** targeted quick-run commands above, scoped to the file(s) touched.
- **Per wave merge:** `pytest tests/` (backend) + `npm run test` (frontend) — both full suites green.
- **Phase gate:** Full suite green before `/gsd-verify-work`; additionally, a manual UAT pass against a real page with a panel-boundary-crossing bubble/SFX (success criterion 4's explicit "not only on a clean test page" requirement cannot be satisfied by synthetic unit-test fixtures alone).

### Wave 0 Gaps

- [ ] `tests/test_bubbles.py` — new file, covers PROT-01 (`detect_bubbles`, `mask_to_polygon`)
- [ ] `tests/test_web/test_panel_routes.py` — new file, covers PAN-02/PAN-03 route-level behavior
- [ ] `tests/test_web/test_protected_routes.py` — new file, covers PROT-02/PROT-03 route-level behavior
- [ ] `tests/test_panels.py` — extend existing file with `box_to_polygon` coverage (PAN-01)
- [ ] `tests/test_trappedball.py` — extend with an explicit panel-boundary/SFX-crossing protected-pixel case (PROT-04's "not only a clean test page" requirement, at least at the unit level — full UAT still needed)
- [ ] `frontend/tests/editor/polygonState.test.ts` — new file, pure reducer coverage (PAN-02/PAN-03/PROT-02/PROT-03)
- [ ] `frontend/tests/editor/hitTest.test.ts` — new file, distance-based hit-testing against `transform.ts` at extreme zoom (success criterion 2)
- [ ] `frontend/tests/editor/undoStack.test.ts` — new file, 20-op cap, inverse-replay correctness (UI-SPEC §6)
- [ ] `frontend/vitest.config.ts` — needs a `jsdom`-environment test path added (either per-file `// @vitest-environment jsdom` docblocks or a second config) for any test asserting DOM structure/ARIA on the new editor components — WR-10..14's deferred frontend-robustness gap becomes directly relevant the moment this phase's canvas mounts real DOM
- [ ] Framework install: `npm install --save-dev jsdom` — for DOM-structure tests only (see Pitfall 3; do not install `canvas`)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | No | Single-machine, no auth in v1 (unchanged from Phase 1) |
| V3 Session Management | No | Same as V2 |
| V4 Access Control | Partial | Existing `get_owned_volume`/`_get_owned_page`-style ownership checks (Phase 1 pattern) must extend to `_get_owned_panel`/`_get_owned_protected_mask` — every new route must verify the referenced panel/page belongs to the currently open project, mirroring `page.py`'s existing `PAGE_NOT_FOUND_DETAIL` pattern rather than trusting a client-supplied id |
| V5 Input Validation | Yes | Pydantic-constrained request bodies (mirroring `schemas.py`'s `RGBTuple`/`NonEmptyStr` pattern): vertex coordinates should be bounded to sane page-pixel ranges (reject negative or absurdly large values before they reach `cv2.fillPoly`, which can allocate/crash on pathological input); polygon vertex-count should have a sane upper bound to prevent a malformed request from producing an unbounded-cost rasterization |
| V6 Cryptography | No | Not applicable to this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| Vertex coordinates crafted to be far outside page bounds, causing `cv2.fillPoly`/`cv2.floodFill` to allocate huge or pathological arrays | Denial of Service | Bound vertex coordinates to `[0, page.width]` / `[0, page.height]` (with a small margin) in the Pydantic request model, rejecting out-of-range values before they reach OpenCV — same pattern as `schemas.py`'s existing `RGBChannel = Annotated[int, Field(ge=0, le=255)]` |
| Panel/protected-mask id from another (hypothetical future multi-tab) project session reused across the process-global `current_project_path` | Tampering / Information Disclosure | Inherited, accepted residual risk from Phase 1 (T-01-TABS) — not newly introduced by this phase; no new mitigation needed beyond what Phase 1 already accepted |
| Excessive polygon vertex count (thousands) submitted via a hand-crafted request, bypassing the client's own UI constraints | Denial of Service | Cap `polygon` list length server-side in the Pydantic model (e.g. a few hundred vertices max) — the UI never produces this many, so a request that does is either a bug or hostile input, and the honest response either way is a 400 |

## Sources

### Primary (HIGH confidence)
- `src/comiccolor/segmentation/panels.py`, `trappedball.py`, `segmenter.py`, `model/entities.py`, `model/masks.py`, `model/store.py`, `pipeline/stages.py` — read directly this session, ComicColor's own codebase
- `frontend/src/geometry/transform.ts`, `frontend/tests/transform.test.ts`, `frontend/src/components/swatchCard.ts`, `frontend/vitest.config.ts` — read directly this session
- Local `python -c "import cv2; ..."` checks against the installed opencv-python-headless 5.0.0 build — [VERIFIED] tool-run, not training-data assumption
- `.planning/phases/02-panel-polygon-editor-protected-masks/02-CONTEXT.md`, `02-UI-SPEC.md` — locked project decisions, read in full this session

### Secondary (MEDIUM confidence)
- `github.com/Rabbit1010/Speech-Bubble-Aware-Automatic-Comic-Colorization` (fetched via tokenade this session) — confirms the "scene text detection → bounding-box clustering → flood fill → hole fill" pipeline shape D-22/D-23 cite as precedent; their implementation uses EAST (a learned detector), which this project deliberately does NOT adopt per D-23/D-25 — cited for pipeline *shape* only, not for the detector choice
- `.planning/research/STACK.md`, `.planning/research/PITFALLS.md` (queried via tokenade this session) — Phase 1's own research, explaining the Konva recommendation D-26 overrides and the coordinate-transform pitfall (Pitfall 7) this phase's editor must respect

### Tertiary (LOW confidence)
- General web search results on HTML5 canvas polygon editing patterns (Konva's own custom-hit-region docs, Stack Overflow "erase and redraw" pattern) — standard, uncontroversial platform knowledge, not independently verified against this project's exact requirements beyond confirming the pattern is conventional
- Pattern 2's `cv2.floodFill` flag semantics — explicitly flagged `[ASSUMED]` in the Assumptions Log; must be verified against the real installed build before shipping

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages, every API verified present on the actual installed OpenCV build
- Architecture: HIGH — directly derived from CONTEXT.md's locked decisions and the actual read source files, not speculative
- Pitfalls: MEDIUM-HIGH — the jsdom/canvas testing gap and schema-migration notes are grounded in this project's actual state (STATE.md's WR-14 blocker, the actual current schema); the flood-fill flag semantics and epsilon-tuning pitfalls are grounded in general OpenCV knowledge but not verified against this project's real page images this session

**Research date:** 2026-08-16
**Valid until:** 2026-09-15 (30 days — stable domain: OpenCV API surface and the web platform's Canvas/Pointer Events APIs do not move quickly; the locked CONTEXT.md decisions this research builds on are the more likely thing to change, via a future discuss-phase revision)
