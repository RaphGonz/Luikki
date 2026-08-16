# Phase 2: Panel Polygon Editor & Protected Masks - Context

**Gathered:** 2026-08-16
**Status:** Ready for planning

<domain>
## Phase Boundary

An artist can trust panel boundaries and protected regions before any colour work
begins. Detected panels are correctable polygons in reading order, not fixed boxes.
Speech bubbles are proposed automatically and can be drawn, reshaped and deleted by
hand — and hand-drawing is the guarantee, since panel-boundary and bubble-crossing
art is explicitly unsolved research and the editable mask is the answer, not a
better detector.

Requirements: PAN-01, PAN-02, PAN-03, PROT-01, PROT-02, PROT-03, PROT-04.

**Scope reduction agreed in discussion:** automatic *proposal* of SFX lettering is
deferred to a later version (D-24). Hand-drawing (PROT-02) still covers SFX
completely, so success criterion 4 remains verifiable via a hand-drawn mask on a
boundary-crossing SFX. REQUIREMENTS.md PROT-01 and the roadmap's criterion 4 should
be amended to say "speech bubbles" rather than "speech bubbles and SFX lettering"
for the automatic half, so a later verifier does not read this as an unmet
requirement.

</domain>

<decisions>
## Implementation Decisions

### Panel polygons

- **D-17: Panels arrive as a 4-vertex box seed, never a traced contour.**
  `segment_panels()` already has the component shape in hand and keeps only the
  bounding box; tracing it with `findContours` + `approxPolyDP` was considered and
  rejected. On a *borderless* panel `_gutter_network` cannot be blocked by a frame,
  so the surviving component is the ink silhouette of the drawing itself — tracing
  yields a polygon shaped like the character, not the panel. Tracing helps only the
  tilted-framed case and actively destroys the borderless one, which is the common
  case in Franco-Belgian work. `Panel.polygon` (`entities.py:116`) already exists
  and is unused; seed it with the four box corners.

- **D-18: Lower `PanelParams.min_solidity` so borderless panels are proposed at
  all.** `panels.py:97` reads `if area / float(w * h) < params.min_solidity:
  continue` — it is a *floor*, so today an ink-silhouette component is silently
  **discarded**, not mis-boxed. Lower it, propose a bounding box around whatever
  survives, and let the artist delete false proposals (a large SFX glyph, a stray
  blob). Explicit user instruction: over-propose and let the artist remove noise,
  rather than under-propose and make them draw from scratch. Do not "fix" this by
  raising the threshold back.

- **D-19: Correction is by vertex editing — move, add, delete — plus draw-from-
  scratch and delete-panel.** This is PAN-02/PAN-03 and it is the load-bearing
  mechanism, not a fallback. The detector's job is to save keystrokes, not to be
  right.

### Protected masks

- **D-20: `ProtectedMask` moves from panel scope to page scope, clipped per panel
  at use.** `entities.py:167` currently binds `panel_id`, which makes a bubble
  straddling two panels unrepresentable — and success criterion 4 demands exactly
  that page. Store against `page_id`; each stage clips the page mask to the panel
  it is working on. One bubble stays one object, so reshape and delete do the
  obvious thing. Phase 2 is the only phase in which protected masks exist so far,
  so no downstream consumer breaks.

- **D-21: Protection means "never coloured", not "content preserved".** The export
  is **colour patches only** — the line layer never leaves the artist's hands and
  exists in this pipeline purely as a guideline for colouring. So a protected area
  is not content to carry through to export; it is an area that never receives a
  palette entry, so no patch is ever emitted there. The artist drops their own
  lines back on top in Photoshop and the bubble is bare paper.

  Consequence: **PROT-04 verifies as one flat property** — no emitted colour patch
  overlaps a protected mask — not as an integrity invariant threaded through four
  phases. Do not build a fail-loud assertion chain on the model of Phase 1's
  `assert_invariant` for this; it is not that kind of problem. `Segmenter.segment(
  line_mask, protected=...)` already returns protected pixels as label 0, which is
  the whole mechanism.

  Same logic covers the seams for free: gutters and inter-panel space lie outside
  every panel polygon, so they are in no panel's label map and are never coloured.
  Panels and protected masks are two mechanisms serving one purpose — bounding
  where colour is allowed to go.

### Bubble detection

- **D-22: A bubble is text surrounded by white — detect the text, then fill.**
  User's own design, adopted over every OSS detector surveyed. Algorithm:
  1. Detect glyphs on the page.
  2. Flood-fill the enclosing white outward from the text as seed.
  3. Cap by maximum area, so an *unclosed* bubble cannot leak into the whole page
     or run out along the gutters between panels.
  4. Discard when the text sits on a large white fill or on a coloured area — that
     is lettering on artwork, not a bubble.

- **D-23: This needs text *detection*, not OCR.** The characters are never read,
  only located, so no OCR engine, no language pack and no licence question. That is
  connected-component analysis in the already-vendored OpenCV: small dark blobs of
  similar height, aligned on a baseline, sitting on locally uniform light ground.
  Those three filters together reject hatching, which has irregular heights and no
  baseline. The seeded flood fill itself already exists in
  `segmentation/trappedball.py` and the vendored LineFiller; the area cap is the
  same guard shape as `panels.py`'s `min_area_frac`. **Read
  `Rabbit1010/Speech-Bubble-Aware-Automatic-Comic-Colorization` before
  implementing** — it is this exact pipeline (scene text detection → bounding-box
  clustering to drop lonely boxes → bubble segmentation) built for this exact
  purpose.

- **D-24: SFX lettering gets no automatic proposal this phase.** User's call, given
  verbatim: *"If SFX gets colored it's okay. Let's go with bubbles and advances,
  and deal with the sfx in a later version."* A "BOOM" over artwork is text with no
  enclosing white to fill, so the flood step finds nothing and the area cap discards
  it. PROT-02 hand-drawing still covers it fully. See the scope note in `<domain>`.

- **D-25: No learned bubble detector, and none is bundled.** Surveyed and rejected
  on licence, not on quality — see `<deferred>` for the full table and the
  GPL/OpenRAIL conflict. If a detector is ever added it belongs behind an optional
  seam on the model of Cobra ("build the seam, spike inside"), with ComicColor
  distributing no restricted weights.

### Editor implementation

- **D-26: Hand-rolled 2D canvas — no Konva, no runtime frontend dependency.**
  Research (`STACK.md`) recommends Konva 9.x (MIT) with HIGH confidence, and it was
  rejected deliberately. Konva ships its own stage scale/position model, which
  describes the same screen↔page mapping as
  `frontend/src/geometry/transform.ts` — the transform Phase 1 built and unit-tested
  at 64× and 0.05× precisely because success criterion 2 requires corrections to
  hold *"at every zoom level via the shared coordinate transform."* Adopting Konva
  means either orphaning that asset or maintaining two sources of truth for one
  mapping, and Phase 3's zone editor depends on the same transform.

  A polygon editor is tens of vertices, not thousands: vertex hit-testing is a
  distance check against `transform.ts`, and drag handles are a few hundred lines.
  Phase 1's zero-runtime-dependency frontend (three audited dev packages) stays
  intact. The planner writes pan/zoom, handle rendering and z-ordering directly.

### Claude's Discretion

Three gray areas were surfaced and the user chose not to discuss them. Decide them
from the decisions above and Phase 1's established conventions:

- **Screen and gate structure** — whether `panels` and `protected` are two
  confirmation gates on one screen or two separate screens. Phase 2 is the first
  phase to actually exercise D-06/D-07 (forward-only, gate per stage, per page), so
  whatever shape is chosen becomes the pattern Phases 3–5 reuse. `01-UI-SPEC.md`
  §2 already specifies the confirmation-gate pattern and §3 the Go-Back flow.
- **Reading order configurability** — `_reading_order()` already takes a
  `ReadingDirection` literal, and manga runs right-to-left while Franco-Belgian runs
  left-to-right. Whether that becomes a per-project setting or stays a parameter is
  open.
- **Undo inside the panel editor** — Phase 3 formally owns undo/redo. Phase 2 needs
  *something* for vertex edits; keep it minimal and do not pre-build Phase 3's
  history model.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 assets this phase builds directly on
- `frontend/src/geometry/transform.ts` — the shared screen↔label-map transform,
  unit-tested at extreme zoom. D-26 makes it the single coordinate authority;
  success criterion 2 is stated in terms of it.
- `src/comiccolor/segmentation/panels.py` — `segment_panels()`, `PanelParams`
  (`min_solidity` at line 97 is the floor D-18 lowers; `min_area_frac` is the guard
  shape D-22 reuses), `_gutter_network()`, `_reading_order()`.
- `src/comiccolor/segmentation/trappedball.py` and `third_party/LineFiller/` —
  existing seeded flood fill with a radius ladder; D-22's bubble fill adapts this
  rather than writing new machinery.
- `src/comiccolor/segmentation/segmenter.py` — the `Segmenter` protocol already
  accepts `protected=` and returns those pixels as label 0. This is the whole of
  PROT-04's mechanism per D-21.
- `src/comiccolor/model/entities.py` — `Panel.polygon` (line 116, exists, unused,
  seeded by D-17); `ProtectedMask` (line 167, moves `panel_id` → `page_id` per
  D-20); `ProtectedKind`.
- `src/comiccolor/model/masks.py` — label map I/O and `assert_invariant`. Note D-21:
  protection is deliberately *not* modelled as an invariant of this kind.
- `src/comiccolor/pipeline/stages.py` — `panels` and `protected` are declared with
  `runner=None`. Phase 2 fills both. D-11 warns the declared stage shapes may need
  amending; they are not frozen.

### Specification and scope
- `flatting-pipeline-spec.md` §1.1 — panel detection.
- `flatting-pipeline-spec.md` §1.2 — "frame as protection, not detection", the
  source of `ProtectedMask`'s docstring.
- `flatting-pipeline-spec.md` §315 — every stage boundary is inspectable and
  editable.
- `.planning/ROADMAP.md` — Phase 2 goal and its four success criteria.
- `.planning/REQUIREMENTS.md` — PAN-01..03, PROT-01..04. See the `<domain>` note on
  amending PROT-01 for the SFX deferral.
- `.planning/PROJECT.md` — "manual bubble masking is the guaranteed fallback; an OSS
  detector is an upgrade, not a dependency", and the licence constraints D-25 turns on.

### Phase 1 decisions still binding
- `.planning/phases/01-foundation-project-palette-pipeline-backbone/01-CONTEXT.md` —
  D-06/D-07 (forward-only, gate per stage per page), D-08 (going back is costed and
  explicit), D-10/D-11 (registry declares, never orchestrates).
- `.planning/phases/01-foundation-project-palette-pipeline-backbone/01-UI-SPEC.md`
  §2 (confirmation gate), §3 (Go-Back flow and destructive-confirmation shape),
  §1 (stage strip — note the corrected line 150).

### Research
- `.planning/research/STACK.md` — Konva recommendation (rejected by D-26, read the
  reasoning before revisiting) and the label-map transport pattern, which matters
  for Phase 3 more than here.
- `.planning/research/PITFALLS.md` — known failure modes.
- `https://github.com/Rabbit1010/Speech-Bubble-Aware-Automatic-Comic-Colorization` —
  **read before implementing D-22.** Scene text detection → bounding-box clustering
  → bubble segmentation, for comic colourisation. Direct precedent.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `segment_panels()`: produces panel components already; only the boxing and the
  `min_solidity` floor change (D-17, D-18). Reading order is already implemented.
- Trapped-ball / LineFiller seeded fill: becomes the bubble fill in D-22 with an
  area cap. Tested, vendored, MIT.
- `transform.ts`: vertex hit-testing and every screen↔page conversion in the editor
  (D-26). Already covers devicePixelRatio and panelOffset.
- `Segmenter.segment(line_mask, protected=)`: the exclusion path already exists and
  is the entirety of PROT-04's mechanism (D-21).
- `Panel.polygon`: the field is already on the entity and in the schema path.

### Established Patterns
- Protocol + swappable implementation (`Segmenter`, `LineExtractor`) — a bubble
  proposer should follow the same shape, which is also what makes D-25's optional
  learned detector possible later without redesign.
- Fail-loud over report-and-ignore (`assert_invariant`) — the house style, but
  explicitly *not* applied to protection per D-21.
- Zero runtime frontend dependencies; three audited dev packages; `textContent`
  never `innerHTML` (Phase 1 T-01-XSS). D-26 keeps all of this true.
- Every mutation commits synchronously, no Save button (PROJ-05). Vertex drags must
  respect this without writing on every `mousemove` — Phase 1's colour picker solved
  the same problem by writing on `change`/blur, not `input` (T-01-FLOOD).

### Integration Points
- `pipeline/stages.py`: `panels` and `protected` runners get implemented; the
  registry contract already exists.
- `ProtectedMask` schema change (`panel_id` → `page_id`) touches `model/store.py`
  and its `protected_for_panel()` query, which becomes a clip-at-use call.
- New routes join the Phase 1 web layer: per-request `Store` via `get_store`,
  Pydantic-bounded bodies, no raw SQL in routers, 409 when no project is open.
- The editor mounts inside the Phase 1 shell's top toolbar strip
  (`01-UI-SPEC.md` §7 — 56px, reused by the canvas editor's tool controls).

</code_context>

<specifics>
## Specific Ideas

- **Borderless panels ("cases sans bordure") are the motivating case**, raised by
  the user unprompted, and they are what killed contour tracing. Any future attempt
  to improve panel proposals must be evaluated on a borderless page first.
- **The bubble algorithm is the user's design, not a library choice.** Text seed →
  fill white → cap area → discard text on large fills or colour. Keep it that shape.
- **"If SFX gets colored it's okay"** — the explicit tolerance that makes D-24
  acceptable. Do not spend planner effort defending against coloured SFX.
- The user surfaced `DeepPanel` and a Roboflow bubble model themselves and accepted
  the licence findings; both are recorded in `<deferred>` rather than dropped.

</specifics>

<deferred>
## Deferred Ideas

- **SFX lettering auto-proposal** — deferred to a later version by explicit user
  decision (D-24). The approach considered and parked: text detected with no
  enclosing fill becomes a dilated glyph mask.
- **DeepPanel** (`github.com/pedrovgs/DeepPanel`, Apache-2.0) as an upgrade to
  PAN-01 proposal quality. Not adoptable now: the Python repo ships **no trained
  weights** (its 550-page training set is private, so you would label your own),
  weights exist only as a TFLite blob inside the Android/iOS libraries, it needs
  TensorFlow in a torch-based project, and it deliberately *groups panels that are
  related as a human would while reading* — which can merge panels a colourist needs
  kept apart. Revisit only if a labelled dataset exists or the TFLite weights can be
  legitimately reused.
- **Learned bubble detectors** — surveyed and rejected on licence, not quality:
  - `kitsumed/yolov8m_seg-speech-bubble` — masks + ONNX export, **GPL-3.0**.
  - `dmMaze/comic-text-detector` — **GPL-3.0**.
  - `huyvux3005/manga109-segmentation-bubble` — claims **Apache-2.0** but is
    fine-tuned on Manga109, whose own terms are research-use-only.
  - `roboflow pers-kdqu3/manga-speech-bubble-detection-1rbgq` — non-permissive;
    user confirmed it segments well.
  Nearly all are YOLO derivatives and Ultralytics is AGPL-3.0, which propagates.
  Note for whoever revisits: GPL-3.0 has **no network clause**, so it would not bite
  a hosted tier the way AGPL would — but GPL §7 forbids the added use-restrictions
  that Cobra's OpenRAIL++-M carries, so bundling both in one distributed work is a
  conflict with no clean answer. The optional-seam route (D-25) avoids the question
  entirely.
- **Roadmap/requirements amendment** — PROT-01 and roadmap criterion 4 should be
  reworded for the SFX deferral. Not done here because discuss-phase does not edit
  the roadmap; flagged so it is a deliberate act rather than a verifier surprise.

</deferred>

---

*Phase: 2-Panel Polygon Editor & Protected Masks*
*Context gathered: 2026-08-16*
