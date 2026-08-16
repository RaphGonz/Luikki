# Requirements: ComicColor

**Defined:** 2026-08-02
**Core Value:** An artist gets flats they can actually use, and every place the machine got it wrong is one click to fix.

## v1 Requirements

Requirements for the first release — a local web app, run on one machine, demonstrated
to colourists over video call. Each maps to exactly one roadmap phase.

### Project

- [x] **PROJ-01**: User can create a named project and reopen it later with its pages, palette and edits intact
- [x] **PROJ-02**: User can upload line art pages to a project and add more pages over time
- [x] **PROJ-03**: User can upload character sheet images to a project as colour references
- [x] **PROJ-04**: User can see each page's stage in the pipeline and open any page for editing
- [x] **PROJ-05**: User's edits persist as they are made, so a refresh or crash loses no work

### Palette

- [x] **PAL-01**: User can upload a swatch image and the app creates named palette entries from its colour chips
- [x] **PAL-02**: User can have the app propose palette entries from an uploaded character sheet and accept or reject each proposal individually
- [x] **PAL-03**: User can create, rename, recolour and delete palette entries by hand
- [x] **PAL-04**: User can change a palette entry's colour and see every affected page update without re-running the pipeline

### Panels

- [x] **PAN-01**: App detects panels on a page and presents them as polygons in reading order
- [x] **PAN-02**: User can drag, add and delete a polygon's vertices to correct a detected panel
- [x] **PAN-03**: User can draw a panel the detector missed, and delete one it invented

### Protected Masks

- [ ] **PROT-01**: App detects speech bubbles and SFX lettering and proposes them as protected masks
- [x] **PROT-02**: User can draw a protected mask by hand where detection missed one
- [x] **PROT-03**: User can reshape or delete a proposed protected mask
- [x] **PROT-04**: Protected regions are excluded from every fill and colour stage and reach export untouched

### Zones

- [ ] **ZONE-01**: App segments each panel into mutually exclusive colour zones
- [ ] **ZONE-02**: User can see zone boundaries overlaid on their line art and pan and zoom without the overlay drifting from the artwork
- [ ] **ZONE-03**: User can merge zones by clicking them
- [ ] **ZONE-04**: User can split a zone by tracing a stroke, and that stroke never appears in any exported artwork
- [ ] **ZONE-05**: User can see which pixels belong to no zone and absorb them into a neighbouring zone in one click
- [ ] **ZONE-06**: User can undo and redo any zone edit, and no edit or undo can produce a zone map with overlaps

### Colour Proposal

- [ ] **COL-01**: App proposes colours for each panel from the project's reference images, and never shows the raw model output to the user
- [ ] **COL-02**: App assigns each zone a palette entry by extracting the zone's dominant colour and matching it in CIELAB
- [ ] **COL-03**: App creates a new flagged palette entry instead of snapping when no existing entry is close enough
- [ ] **COL-04**: App flags zones the model was uncertain about, measured as variance across multiple seeds

### Review

- [ ] **REV-01**: User can see the flatted page with every zone filled from the project palette
- [ ] **REV-02**: User can reassign a zone to a different palette entry in one click
- [ ] **REV-03**: User can work through flagged and low-confidence zones as a queue instead of hunting for them
- [ ] **REV-04**: User can confirm a zone as correct so it leaves the review queue

### Export

- [ ] **EXP-01**: User can export a page as a PSD with one layer group per panel
- [ ] **EXP-02**: User can choose between a single flat layer, one layer per colour, and one layer per zone
- [ ] **EXP-03**: Exported flats composite under anti-aliased line art without fringing or halos
- [ ] **EXP-04**: Exported PSD opens in both Photoshop and Clip Studio Paint with groups and layers intact
- [ ] **EXP-05**: User can see the layer count and file size an export will produce before running it

### Metrics

- [ ] **MET-01**: App records post-correction time per page — how long the user spent editing after the automatic pass
- [ ] **MET-02**: App records the proportion of zones accepted without any edit
- [ ] **MET-03**: App records corrections required per fillable region per page, so the trend across a project is visible
- [ ] **MET-04**: App records how often a flagged zone actually needed editing
- [ ] **MET-05**: User can see these figures for a project without leaving the app

## v2 Requirements

Acknowledged and deferred. Not in the current roadmap.

### Colour

- **SHAD-01**: App produces a shadow mask layer from per-pixel deviation from the zone mode
- **IDENT-01**: App propagates a character's colour identity across pages after a single hint
- **IDENT-02**: User can correct a mis-propagated identity once and have the correction carry forward

### Editing

- **ZONE-07**: User can have a traced split also emit an ink line on its own export layer
- **PAN-04**: User can bypass panel detection and treat a whole page as one panel

### Learning

- **LOG-01**: App logs accepted-without-edit zones as positives and edit deltas as negatives, for later training

### Deployment

- **HOST-01**: App runs on a server with multiple user accounts
- **HOST-02**: Colour proposal runs on a remote GPU endpoint rather than the local card

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Hosting, accounts, multi-user | v1 runs on one machine and is demonstrated over video call. "Let's keep it ultra simple." |
| CPU inference path, Mac support | No tester is ever left alone with the app in v1, so no second hardware target |
| Shading, lighting, effects, halftone | Tier 2/4. Flats are the product |
| Painted or lineless art | No line means no line art means no product |
| Text rendering, lettering, translation | Never in scope |
| American comics adapter | Needs a retrained extractor (§7); untested and acknowledged as such |
| Hatching adapter | Tier 3, and it stays there — P3's alarm was our own segmenter, not the art |
| Latency and throughput optimisation | LineFiller runs 15–66s per page and that is accepted at this stage |
| Modifying Cobra's DiT | Forfeits the pretrained weights and buys nothing |
| SAM for region identity | Class-agnostic segmentation, not instance retrieval; trapped-ball is already more exact |
| Full auto-colourisation with no review step | The exact thing FlatMagic's participants rejected; the review loop is the product |
| Synthetic training data from a generative model | Learns the generator's error distribution and misses the real tail |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PROJ-01 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PROJ-02 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PROJ-03 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PROJ-04 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PROJ-05 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PAL-01 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PAL-02 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PAL-03 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PAL-04 | Phase 1 — Foundation: Project, Palette & Pipeline Backbone | Complete |
| PAN-01 | Phase 2 — Panel Polygon Editor & Protected Masks | Complete |
| PAN-02 | Phase 2 — Panel Polygon Editor & Protected Masks | Complete |
| PAN-03 | Phase 2 — Panel Polygon Editor & Protected Masks | Complete |
| PROT-01 | Phase 2 — Panel Polygon Editor & Protected Masks | Pending |
| PROT-02 | Phase 2 — Panel Polygon Editor & Protected Masks | Complete |
| PROT-03 | Phase 2 — Panel Polygon Editor & Protected Masks | Complete |
| PROT-04 | Phase 2 — Panel Polygon Editor & Protected Masks | Complete |
| ZONE-01 | Phase 3 — Zone Editor: Merge, Split, Gaps & Undo | Pending |
| ZONE-02 | Phase 3 — Zone Editor: Merge, Split, Gaps & Undo | Pending |
| ZONE-03 | Phase 3 — Zone Editor: Merge, Split, Gaps & Undo | Pending |
| ZONE-04 | Phase 3 — Zone Editor: Merge, Split, Gaps & Undo | Pending |
| ZONE-05 | Phase 3 — Zone Editor: Merge, Split, Gaps & Undo | Pending |
| ZONE-06 | Phase 3 — Zone Editor: Merge, Split, Gaps & Undo | Pending |
| COL-01 | Phase 4 — Cobra Worker & Isolated Colour Proposal | Pending |
| COL-02 | Phase 5 — Mode Extraction, CIELAB Snapping & Confidence Triage | Pending |
| COL-03 | Phase 5 — Mode Extraction, CIELAB Snapping & Confidence Triage | Pending |
| COL-04 | Phase 5 — Mode Extraction, CIELAB Snapping & Confidence Triage | Pending |
| MET-04 | Phase 5 — Mode Extraction, CIELAB Snapping & Confidence Triage | Pending |
| REV-01 | Phase 6 — Review View & Metrics Instrumentation | Pending |
| REV-02 | Phase 6 — Review View & Metrics Instrumentation | Pending |
| REV-03 | Phase 6 — Review View & Metrics Instrumentation | Pending |
| REV-04 | Phase 6 — Review View & Metrics Instrumentation | Pending |
| MET-01 | Phase 6 — Review View & Metrics Instrumentation | Pending |
| MET-02 | Phase 6 — Review View & Metrics Instrumentation | Pending |
| MET-03 | Phase 6 — Review View & Metrics Instrumentation | Pending |
| MET-05 | Phase 6 — Review View & Metrics Instrumentation | Pending |
| EXP-01 | Phase 7 — Layered PSD Export | Pending |
| EXP-02 | Phase 7 — Layered PSD Export | Pending |
| EXP-03 | Phase 7 — Layered PSD Export | Pending |
| EXP-04 | Phase 7 — Layered PSD Export | Pending |
| EXP-05 | Phase 7 — Layered PSD Export | Pending |

**Coverage:**

- v1 requirements: 40 total
- Mapped to phases: 40
- Unmapped: 0 ✓

**Note on metrics distribution:** MET-01..05 are deliberately spread across two phases rather
than bundled into one. MET-04 (flagged-region precision) lands in Phase 5 because the flag
itself is created there and needs its own instrumentation to tune the reject threshold.
MET-01, MET-02, MET-03 and MET-05 land in Phase 6 because post-correction time, acceptance
rate and correction counts are all produced by the review/colour-correction workflow itself
and cannot be retrofitted onto sessions that already happened.

---
*Requirements defined: 2026-08-02*
*Last updated: 2026-08-02 after roadmap creation — traceability and coverage populated*
