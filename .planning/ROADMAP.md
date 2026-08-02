# Roadmap: ComicColor

## Overview

ComicColor adds an artist-facing web layer on top of an already-validated deterministic
segmentation core. The build follows the horizontal-layer order the user explicitly chose
over vertical MVP slices: backbone first, then the two geometry-editing surfaces (panels,
zones), then the isolated Cobra colour proposer, then the deterministic snapping/triage
that turns its output into palette assignments, then the review surface where artists
correct and the app measures its own value, and finally the layered PSD export that is
the literal deliverable. The first exportable PSD arrives last by design — every boundary
before it needs to be inspectable and correct before there is a file worth handing to a
colourist. Metrics are the one place this spine deliberately bends: each MET requirement
lands in the phase that owns the feature producing its data, not in a single late phase.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation — Project, Palette & Pipeline Backbone** - Artist creates a persistent project, accumulates pages and a palette, on top of a stage-registry backbone and invariant-checked coordinate infrastructure the editors will share.
- [ ] **Phase 2: Panel Polygon Editor & Protected Masks** - Artist corrects detected panel polygons and masks bubbles/SFX as protected regions that no later stage ever touches.
- [ ] **Phase 3: Zone Editor — Merge, Split, Gaps & Undo** - Artist merges, splits, and gap-fixes colour zones with undo/redo that can never produce an invalid label map.
- [ ] **Phase 4: Cobra Worker & Isolated Colour Proposal** - Cobra proposes colours per panel from an isolated, VRAM-measured worker process, never shown raw to the artist.
- [ ] **Phase 5: Mode Extraction, CIELAB Snapping & Confidence Triage** - Every zone gets a palette entry via mode extraction and validated CIELAB snapping, with reject-before-snap and seed-variance flagging instrumented from the start.
- [ ] **Phase 6: Review View & Metrics Instrumentation** - Artist works flagged zones as a queue, reassigns or confirms in one click, and the app measures post-correction time, acceptance and correction rates live.
- [ ] **Phase 7: Layered PSD Export** - Artist exports a halo-free, layer-per-panel PSD in three granularities that opens identically in Photoshop and Clip Studio.

## Phase Details

### Phase 1: Foundation — Project, Palette & Pipeline Backbone
**Goal**: An artist can create a persistent project, add pages and reference images to it over time, and build a palette by hand, from a swatch, or from a proposed character-sheet extraction — with every edit surviving a refresh or crash. Underneath, the pipeline stage registry, the shared screen↔label-map coordinate transform, and the label-map exclusivity/exhaustiveness invariant check are built and unit-tested as the foundation every later editor and stage depends on, since retrofitting them after an editor exists is far costlier than building them first.
**Depends on**: Nothing (first phase)
**Requirements**: PROJ-01, PROJ-02, PROJ-03, PROJ-04, PROJ-05, PAL-01, PAL-02, PAL-03, PAL-04
**Success Criteria** (what must be TRUE):
  1. Artist creates a named project, closes the app, reopens it later, and finds its pages, palette and prior edits intact.
  2. Artist uploads line art pages and character-sheet reference images to a project, adds more pages weeks later without losing anything already there, and can see each page's current pipeline stage and open any page for editing.
  3. Artist uploads a swatch image and gets named palette entries built from its colour chips; separately uploads a character sheet and accepts or rejects each app-proposed palette entry individually; and can also create, rename, recolour or delete a palette entry entirely by hand.
  4. Artist changes a palette entry's colour once and sees every page that references it update immediately, with no pipeline stage re-run.
  5. Every one of these edits persists the moment it's made — a refresh or crash immediately afterward loses no work.
**Plans**: TBD
**UI hint**: yes

### Phase 2: Panel Polygon Editor & Protected Masks
**Goal**: An artist can trust panel boundaries and protected regions before any colour work begins. Detected panels are correctable polygons, not fixed boxes, and bubble/SFX lettering is guaranteed protected from every fill and colour stage all the way to export — by a detector where one exists, and by hand always, since panel-boundary and bubble-crossing art is explicitly unsolved research and the editable mask is the answer, not a better detector.
**Depends on**: Phase 1
**Requirements**: PAN-01, PAN-02, PAN-03, PROT-01, PROT-02, PROT-03, PROT-04
**Success Criteria** (what must be TRUE):
  1. Artist opens a page and sees panels already detected as polygons, presented in reading order.
  2. Artist drags, adds and deletes a polygon's vertices to correct a detected panel, draws a panel the detector missed from scratch, and deletes one the detector invented — each correction holds at every zoom level via the shared coordinate transform, not just at the zoom level it was made.
  3. Artist sees speech bubbles and SFX lettering proposed automatically as protected masks, draws one by hand wherever detection missed, and reshapes or deletes a proposed mask.
  4. Protected regions are excluded from every fill and colour stage and reach export completely untouched — verified on a page where art or an SFX crosses a panel boundary, not only on a clean test page.
**Plans**: TBD
**UI hint**: yes

### Phase 3: Zone Editor — Merge, Split, Gaps & Undo
**Goal**: An artist can see, correct, and fully trust the zone segmentation inside each panel. Merge, trace-split, gap-absorption and undo/redo are all built against the shared coordinate transform and invariant check from Phase 1, so no interaction — at any zoom level, in any sequence — can ever leave the label map overlapping or non-exhaustive. This is the highest invariant-risk surface in the project and is hardened here, before any colour data depends on the regions being stable.
**Depends on**: Phase 1, Phase 2
**Requirements**: ZONE-01, ZONE-02, ZONE-03, ZONE-04, ZONE-05, ZONE-06
**Success Criteria** (what must be TRUE):
  1. Artist opens a panel and sees it already segmented into mutually exclusive colour zones, boundaries overlaid on the line art; the overlay tracks the artwork exactly through pan and zoom, tested at both extreme zoom-in and extreme zoom-out, not just a mid-zoom demo.
  2. Artist merges two zones by clicking them, and splits a zone by tracing a cut — the traced stroke itself never appears in any exported artwork.
  3. Artist sees exactly which pixels belong to no zone (the known, characterized gap defect in the underlying segmenter) surfaced per-panel in the editor, not buried in a report, and absorbs them into a neighbouring zone in one click.
  4. Artist undoes and redoes any sequence of merges, splits and absorptions and the label map returns to bit-identical states at every step — an automated invariant check runs after every transition and no edit or undo/redo step ever produces overlapping or missing-pixel zones.
**Plans**: TBD
**UI hint**: yes

### Phase 4: Cobra Worker & Isolated Colour Proposal
**Goal**: Cobra runs as a black-box colour proposer inside its own long-lived, isolated worker process — never imported into the web server, never shown raw to the artist — with its real VRAM footprint on the target machine measured rather than assumed, and its job queue serialized so a second request during an in-flight run cannot corrupt or crash it. The spike happens inside this phase, not as a separate one: the seam is built and the spike runs against it.
**Depends on**: Phase 1, Phase 2
**Requirements**: COL-01
**Success Criteria** (what must be TRUE):
  1. Cobra runs in its own isolated environment (pinned numpy==1.26.4 / torch==2.5.1) behind a long-lived local worker process, and can be started and stopped independently of the web server without either one crashing the other.
  2. Artist triggers colour proposal for a panel from the project's reference images; the app calls Cobra through the worker and gets a proposal raster back that is never rendered, displayed, or diffed anywhere the artist can see it.
  3. The worker's actual peak VRAM usage for one in-flight panel at 384–512px is measured on the real target machine and recorded as a real number, replacing the ~12GB placeholder estimate rather than shipping on top of it unverified.
  4. A second colour-proposal request submitted while one is already running queues behind it and completes correctly rather than causing a GPU OOM or a silent hang.
**Plans**: TBD

### Phase 5: Mode Extraction, CIELAB Snapping & Confidence Triage
**Goal**: Every colour zone gets a palette entry, and gets it correctly: mode extraction reads Cobra's proposal raster only through its eroded interior (never a raw pixel, never a boundary-adjacent sample), CIELAB matching downweights L* specifically because shading moves lightness and not hue, and a distance too far from every existing entry creates a new flagged entry instead of silently coercing a genuinely new colour. Three-seed variance flags the zones the model itself was unsure about. The L* weight, the reject threshold, and flagged-region precision are all treated as things to validate against real hard cases and instrument from the first run, not spec values to implement as given.
**Depends on**: Phase 4
**Requirements**: COL-02, COL-03, COL-04, MET-04
**Success Criteria** (what must be TRUE):
  1. Every zone in a panel is assigned a palette entry by extracting its dominant colour from the eroded interior of its region mask (never the true boundary, never a raw pixel read) and matching it in CIELAB with L* downweighted — validated against a labelled set of real hard cases (shadow-side skin vs. hair, similar uniforms), not shipped as an untested constant.
  2. When no existing palette entry is close enough, the app creates a new flagged palette entry rather than snapping to the nearest one — and every distance and outcome is logged from the first run so the reject threshold can be tuned against real accept/reject data rather than guessed once.
  3. Zones the model disagreed with itself on across 3 seeds are visibly flagged, and that flag is tracked as a distinct state from "flagged as a new colour" — the two causes are never merged into one status field.
  4. For every flagged zone, the app records whether it actually needed editing once reviewed, so flagged-region precision is measurable from the first real session rather than reconstructed later.
**Plans**: TBD

### Phase 6: Review View & Metrics Instrumentation
**Goal**: An artist sees the fully flatted page, works through flagged and low-confidence zones as a queue instead of hunting for them, and reassigns or confirms each one in a single click. This is where the product's actual value becomes measurable: post-correction time, acceptance-without-edit rate, and corrections-per-region are instrumented into the correction workflow's first version — not retrofitted onto sessions that already happened — and the resulting figures are visible in-app.
**Depends on**: Phase 5
**Requirements**: REV-01, REV-02, REV-03, REV-04, MET-01, MET-02, MET-03, MET-05
**Success Criteria** (what must be TRUE):
  1. Artist sees the flatted page with every zone filled from the project palette.
  2. Artist reassigns a zone to a different palette entry in one click, and confirms a zone as correct so it leaves the review queue.
  3. Artist works through flagged and low-confidence zones as a queue instead of hunting across the page for them.
  4. From this view's first working version, the app records how long the artist spent editing after the automatic pass, the proportion of zones accepted without any edit, and corrections made per fillable region — captured live during the session, not reconstructed afterward from logs that don't exist yet.
  5. Artist views post-correction time, acceptance rate, corrections per region, and flagged-zone accuracy for a project without leaving the app.
**Plans**: TBD
**UI hint**: yes

### Phase 7: Layered PSD Export
**Goal**: An artist exports a page as a layered PSD that is actually usable in a real studio pipeline: one group per panel, a choice of three granularities, flats that don't halo under anti-aliased ink, and a structure that opens identically in both Photoshop and Clip Studio rather than merely "opening" in whichever app the developer tested first. Export is deliberately last — it is a read-only, re-runnable pass over already-stable upstream data, and the riskiest granularity option ("per zone") is exactly where the pre-export size/layer estimate matters most.
**Depends on**: Phase 6
**Requirements**: EXP-01, EXP-02, EXP-03, EXP-04, EXP-05
**Success Criteria** (what must be TRUE):
  1. Artist exports a page as a PSD with one layer group per panel.
  2. Artist chooses between a single flat layer, one layer per colour (the default) and one layer per zone, and the exported file's structure reflects that choice.
  3. Exported flats composite under anti-aliased line art with no fringing or halo, verified visually at high zoom on a curved line against a page with genuinely soft, non-binarized ink — not an idealized test asset.
  4. The exported PSD opens with identical group and layer structure in both Photoshop and Clip Studio Paint, verified as a dual-app round-trip test, not a Photoshop-only check.
  5. Before running an export, the artist sees the projected layer count and file size the export will produce, validated against a hatching-dense page's actual region count under "per zone" granularity — not only against a clean test page.
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation — Project, Palette & Pipeline Backbone | 0/TBD | Not started | - |
| 2. Panel Polygon Editor & Protected Masks | 0/TBD | Not started | - |
| 3. Zone Editor — Merge, Split, Gaps & Undo | 0/TBD | Not started | - |
| 4. Cobra Worker & Isolated Colour Proposal | 0/TBD | Not started | - |
| 5. Mode Extraction, CIELAB Snapping & Confidence Triage | 0/TBD | Not started | - |
| 6. Review View & Metrics Instrumentation | 0/TBD | Not started | - |
| 7. Layered PSD Export | 0/TBD | Not started | - |

---
*Roadmap created: 2026-08-02*
*Granularity: standard (7 phases — user-directed horizontal-layer spine, explicitly preserved per project mode rather than compressed to the standard 4-6 default)*
