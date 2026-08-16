# Phase 2: Panel Polygon Editor & Protected Masks - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-16
**Phase:** 2-panel-polygon-editor-protected-masks
**Areas discussed:** Polygon fidelity, Protected mask scope, Detector ambition, Canvas dependency

---

## Polygon fidelity

### Q1 — How should a detected panel arrive on the artist's canvas?

| Option | Description | Selected |
|--------|-------------|----------|
| Traced contour, simplified | `findContours` + `approxPolyDP` on the component that already exists; tilted/L-shaped panels arrive usable, tolerance becomes a tuning parameter | |
| 4-vertex box seed | Seed `Panel.polygon` with the four `PanelBox` corners; every non-rectangular panel is hand-corrected | ✓ |
| Box seed now, contour behind a flag | Ship the seed, implement tracing behind a parameter, decide on the live call | |

**User's choice:** 4-vertex box seed, plus explicit emphasis on add/remove/modify corners.

**Notes:** The user raised borderless panels ("cases without borders") unprompted as the
common case that would not be detected properly. That observation decided the question.
`_gutter_network` defines panel area as everything the page margin cannot reach — on a
framed panel the frame blocks the margin, but on a borderless panel nothing does, so the
surviving component is the ink silhouette of the drawing. A traced polygon would follow
the character's outline rather than the panel. Tracing therefore helps only the
tilted-framed case and destroys the borderless one. The user's framing also matches the
roadmap goal's own words: the editable mask is the answer, not a better detector.

### Q2 — What should happen to a borderless panel, whose component is the ink silhouette?

| Option | Description | Selected |
|--------|-------------|----------|
| Box it anyway — relax `min_solidity` | Propose a rectangle around the silhouette instead of discarding it; artist deletes false proposals | ✓ |
| Keep dropping it — artist draws it | Zero false positives; borderless pages get no help at all | |
| Box it, but mark it low-confidence | Distinguish low-solidity seeds visually; needs a confidence notion nothing else in Phase 2 uses | |

**User's choice:** *"let's raise min_solidity and let the user modify the corners, add some
etc. and they will remove the noise themselves"* — over-propose, artist removes noise.

**Notes:** Direction corrected during discussion. `panels.py:97` is
`if area / float(w * h) < params.min_solidity: continue` — a floor, so *raising* it rejects
more. The user's stated intent ("they will remove the noise themselves") requires
**lowering** it. Intent recorded, not the literal wording.

---

## Protected mask scope

### Q1 — A speech bubble or SFX glyph straddles two panels. How should it be stored?

| Option | Description | Selected |
|--------|-------------|----------|
| Page-scoped masks, clipped per panel at use | Move `ProtectedMask` from `panel_id` to `page_id`; stages clip to the panel they work on | ✓ |
| Keep per-panel, split a crossing mask | One row per intersected panel; no schema change, but one bubble becomes two rows | |
| Store polygons, rasterise on demand | Editing and panel-independence free; but freehand strokes are natively rasters | |

**User's choice:** Page-scoped masks, clipped per panel at use.

### Q2 — What guarantees PROT-04, that protected regions reach export untouched?

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-loud assertion, same shape as Phase 1's invariant | Raise at every stage boundary touching a label map | |
| Trust the segmenter seam, verify at export | Holds by construction; regression surfaces only in Phase 7 | |
| Assertion plus a visible artist-facing indicator | Strongest, adds a rendering contract every later phase honours | |

**User's choice:** None of the above — the user rejected the question's premise, correctly.

**Notes:** *"it is way simpler than that: what will be exported is color patches, not the
lines. The lines are only a guideline for the coloring process. Masking the seams, cases
and bubbles is only to remove them from the coloring process."* This collapses PROT-04
from an integrity invariant threaded through four phases to a single flat property — no
emitted colour patch overlaps a protected mask. Protection is an absence of colour, not
content to preserve. The same logic covers gutters and seams for free, since they lie
outside every panel polygon and are therefore in no label map. The three options offered
were all over-engineered against this reading; the question should not have been asked in
that shape.

---

## Detector ambition

### Q1 — What should propose speech bubbles and SFX in Phase 2?

| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic heuristic — closed light blobs | Flood-fill light areas enclosed by ink, filter by area and contained darker pixels | |
| Hand-drawing only, honest empty state | Ship PROT-02/03 fully, proposal list starts empty | |
| Search for an OSS bubble detector first | Spend research budget before deciding; matches the standing integrate-before-building preference | ✓ (then superseded) |

**User's choice:** Search first — then, after seeing the survey, the user proposed their own
algorithm, which was adopted instead.

**Notes:** The user first offered `github.com/pedrovgs/DeepPanel`. Investigated: Apache-2.0
and clean on licence, but the Python repo ships **no trained weights** (550-page training
set private), weights exist only as a TFLite blob in the Android/iOS libraries, it needs
TensorFlow in a torch project, and it deliberately groups related panels "as a human would
while reading" — which can merge panels a colourist needs kept apart.

A wider survey of bubble detectors found the landscape is a licence problem, not a quality
problem — nearly all are YOLO derivatives and Ultralytics is AGPL-3.0:

| Model | Masks | Licence |
|---|---|---|
| `kitsumed/yolov8m_seg-speech-bubble` | yes, + ONNX | GPL-3.0 |
| `dmMaze/comic-text-detector` | yes | GPL-3.0 |
| `huyvux3005/manga109-segmentation-bubble` | yes | Apache-2.0 claimed, but Manga109-derived (research-use-only) |
| `roboflow pers-kdqu3/manga-speech-bubble-detection-1rbgq` | yes, user-verified as working well | non-permissive |
| DeepPanel | n/a | Apache-2.0, no weights |

Noted for the record: GPL-3.0 has no network clause, so it would not bite a hosted tier the
way AGPL would — but GPL §7 forbids the added use-restrictions that Cobra's OpenRAIL++-M
carries, so bundling both in one distributed work is a conflict with no clean answer.

The user then proposed: *"a bubble is text surrounded by white. If text is detected using
simple OCR, then it's trivial to detect the bubble around it, by simply filling the space.
In the case of unclosed bubble, a max area should be set (so that the bubble is not the
entire page or seams between the cases), and if the letter is a big white fill or colored
one, it's probably not in a bubble and should be discarded."* Adopted as D-22.

Two sharpenings offered and accepted implicitly: it needs text *detection*, not OCR (the
characters are never read, so connected-component analysis in the vendored OpenCV suffices
— no model, no language pack, no licence); and the seeded flood fill already exists in
`trappedball.py`/LineFiller. Direct precedent surfaced:
`Rabbit1010/Speech-Bubble-Aware-Automatic-Comic-Colorization` implements this exact
pipeline for this exact purpose.

### Q2 — Text detected but no enclosing bubble found: the SFX case

| Option | Description | Selected |
|--------|-------------|----------|
| Protect the glyphs themselves, dilated | Covers SFX over artwork and across panel boundaries; dilation needs tuning | |
| Propose nothing — artist hand-draws SFX | Zero false positives on detailed artwork; PROT-01 names SFX explicitly | |
| Propose the glyph bounding hull | One shape, no leakage through letter counters; protects artwork between letters | |

**User's choice:** *"If SFX gets colored it's okay. Let's go with bubbles and advances, and
deal with the sfx in a later version."*

**Notes:** Scope consequence flagged at the time — PROT-01 says "speech bubbles **and SFX
lettering**" and criterion 4 names an SFX crossing a panel boundary. PROT-02 hand-drawing
still covers SFX completely, so criterion 4 stays verifiable; it is the automatic proposal
that is deferred, not the capability. REQUIREMENTS.md and the roadmap criterion should be
amended so a later verifier does not read it as an unmet requirement.

---

## Canvas dependency

### Q1 — What draws the panel and mask editor?

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-rolled canvas on `transform.ts` | Zero runtime dependencies, one coordinate authority; you write pan/zoom and handles | ✓ |
| Konva 9.x (MIT), bridged to `transform.ts` | Drag handles and hit-testing free; two descriptions of one mapping, bridge tested at extreme zoom | |
| Konva, and retire `transform.ts` as frontend authority | One coordinate system, no bridge; discards a tested Phase 1 asset Phase 3 also depends on | |

**User's choice:** Hand-rolled canvas on `transform.ts`.

**Notes:** Chosen against research's HIGH-confidence Konva recommendation in `STACK.md`.
The deciding factor was coordinate authority rather than dependency count: Konva ships its
own stage scale/position model describing the same screen↔page mapping that Phase 1 built
and unit-tested at 64× and 0.05×, specifically because success criterion 2 requires
corrections to hold "at every zoom level via the shared coordinate transform."

---

## Claude's Discretion

Three gray areas were surfaced at the closing gate and the user chose to proceed without
discussing them:

- **Screen and gate structure** — `panels` and `protected` as two gates on one screen or
  two screens. Phase 2 is the first phase to exercise D-06/D-07, so the shape chosen
  becomes the pattern Phases 3–5 reuse.
- **Reading order configurability** — `_reading_order()` already takes a
  `ReadingDirection`; manga runs right-to-left, Franco-Belgian left-to-right.
- **Undo inside the panel editor** — Phase 3 formally owns undo/redo; Phase 2 needs
  something minimal without pre-building Phase 3's history model.

## Deferred Ideas

- SFX lettering auto-proposal — later version (D-24).
- DeepPanel as a future PAN-01 upgrade — blocked on absent weights, TensorFlow, and its
  deliberate panel-grouping behaviour.
- Learned bubble detectors — rejected on licence, not quality; full table above. If ever
  revisited, it belongs behind an optional seam on the Cobra model, with ComicColor
  distributing no restricted weights.
- Roadmap/requirements amendment for the SFX deferral — flagged, not performed here.
