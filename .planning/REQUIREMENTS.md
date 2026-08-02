# Requirements: ComicColor

**Defined:** 2026-08-02
**Core Value:** An artist gets flats they can actually use, and every place the machine got it wrong is one click to fix.

## v1 Requirements

Requirements for the first release — a local web app, run on one machine, demonstrated
to colourists over video call. Each maps to exactly one roadmap phase.

### Project

- [ ] **PROJ-01**: User can create a named project and reopen it later with its pages, palette and edits intact
- [ ] **PROJ-02**: User can upload line art pages to a project and add more pages over time
- [ ] **PROJ-03**: User can upload character sheet images to a project as colour references
- [ ] **PROJ-04**: User can see each page's stage in the pipeline and open any page for editing
- [ ] **PROJ-05**: User's edits persist as they are made, so a refresh or crash loses no work

### Palette

- [ ] **PAL-01**: User can upload a swatch image and the app creates named palette entries from its colour chips
- [ ] **PAL-02**: User can have the app propose palette entries from an uploaded character sheet and accept or reject each proposal individually
- [ ] **PAL-03**: User can create, rename, recolour and delete palette entries by hand
- [ ] **PAL-04**: User can change a palette entry's colour and see every affected page update without re-running the pipeline

### Panels

- [ ] **PAN-01**: App detects panels on a page and presents them as polygons in reading order
- [ ] **PAN-02**: User can drag, add and delete a polygon's vertices to correct a detected panel
- [ ] **PAN-03**: User can draw a panel the detector missed, and delete one it invented

### Protected Masks

- [ ] **PROT-01**: App detects speech bubbles and SFX lettering and proposes them as protected masks
- [ ] **PROT-02**: User can draw a protected mask by hand where detection missed one
- [ ] **PROT-03**: User can reshape or delete a proposed protected mask
- [ ] **PROT-04**: Protected regions are excluded from every fill and colour stage and reach export untouched

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
| (pending roadmap) | — | — |

**Coverage:**
- v1 requirements: 40 total
- Mapped to phases: 0
- Unmapped: 40 ⚠️

---
*Requirements defined: 2026-08-02*
*Last updated: 2026-08-02 after initial definition*
