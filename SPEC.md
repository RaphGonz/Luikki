# ComicColor — barebone spec

The smallest version of the app that is actually usable end to end. Build this
first, develop from it later.

`flatting-pipeline-spec.md` remains the long-form architecture reference.

---

## The user story

> A colourist opens ComicColor, picks a folder, and drops in a page of line art
> and the character sheets for the book.
>
> They press **Detect panels** and see the panels outlined. Two are wrong, so
> they drag a corner, delete one the app invented, and draw one it missed.
>
> They press **Detect bubbles** and see the speech balloons outlined. One is
> missed, so they draw it by hand.
>
> They press **Segment zones** and each panel fills with flat regions. Two
> regions should be one, so they click both to merge. One region should be two,
> so they draw a line across it to cut it.
>
> They press **Generate flats**. Cobra colours the page from the character
> sheets, and every zone takes a colour from the palette. They never see Cobra's
> raw output — only flat, palette-bound zones.
>
> Most of it is right. The ones that aren't, they click and reassign in one go.
>
> They press **Export** and get a PSD they open in Photoshop, drop their own
> line layer on top, and keep working.

That is the whole product. Everything else is an improvement to one of those steps.

---

## Features

### Project
1. Pick a folder. It becomes the project; a SQLite database lives inside it.
2. Drop image files in. They become pages. Add more any time.
3. Reopen the app later and everything is there.
4. Every edit saves the moment it happens. No Save button.

### Panels
5. **Detect panels** button. The artist presses it; nothing runs on its own.
6. Panels appear as editable 4-corner polygons, numbered in reading order.
7. Drag a corner. Add a corner. Delete a corner.
8. Draw a panel from scratch. Delete a panel — one click, no confirmation.

### Bubbles / protected areas
9. **Detect bubbles** button. Same rule: artist presses it.
10. Detected bubbles appear as editable polygons.
11. Draw a protected area by hand. Reshape one. Delete one.
12. Protected areas are page-level, not per-panel — a bubble crossing a panel
    border is one shape.
13. Protected areas never receive colour. That is all "protected" means.

### Zones
14. **Segment zones** button. Fills each panel with flat regions.
15. Click two zones to merge them.
16. Draw a line across a zone to cut it in two. The line is a cut in the zone
    map only — it never appears in any export.

### Palette and character sheets
17. Create, rename, recolour, delete colours by hand.
18. Upload a swatch image, get colours out of it.
19. Upload a character sheet. It belongs to a named character and is what Cobra
    is given as reference.
20. The app proposes palette colours from a character sheet; accept or reject
    each one.
21. Change a colour once and every page using it updates. No re-run, no
    regeneration.

### Generation
22. **Generate flats** button. Cobra colours each panel using the character
    sheets as reference.
23. Each zone takes the *mode* — the most common colour — of Cobra's output
    inside it, then snaps to the nearest palette colour.
24. Cobra's raw output is never shown. The artist sees flat, palette-bound
    zones or nothing.
25. Click a zone and reassign it to a different palette colour.

### Export
26. **Export** button. PSD, one layer group per panel, one layer per colour.
27. No line art in the export. Flats only.

---

## Algorithms

### Panel detection
Already built, in `src/comiccolor/segmentation/panels.py`.

- Reinforce frames first: keep only pixels on long straight runs, bridge gaps
  along them, add back to the line mask. Adding ink can only seal, never split.
- Panel area = everything the page margin cannot reach (`_gutter_network`).
- Connected components on that area → bounding boxes → 4-corner polygons.
- Reading order left-to-right by default (Franco-Belgian); `"rtl"` for manga.

Parameters (`PanelParams`):

| Param | Value | Meaning |
|---|---|---|
| `min_gutter_frac` | 0.012 | narrowest gutter, as fraction of shorter side |
| `min_area_frac` | 0.005 | below this share of page area it is debris |
| `min_solidity` | 0.25 | **floor** — components less solid are discarded |
| `frame_length_frac` | 0.05 | shortest run counted as a frame |
| `frame_gap_frac` | 0.10 | longest frame break to repair |

**Borderless panels are the motivating case.** With no frame to seal the gutter
network, the surviving component is the ink silhouette of the drawing, not a
rectangle. So: no contour tracing (it would trace the character's outline), and
`min_solidity` stays low so silhouettes are proposed rather than silently
dropped. Over-propose; the artist deletes false positives. Never raise it back
toward 0.55 — that silently drops every borderless panel.

### Bubble detection
Already built, in `src/comiccolor/segmentation/bubbles.py`.

**A bubble is text surrounded by white.**

1. Find glyphs — small dark components of similar height, aligned, not long
   straight runs. This is *detection*, not OCR: the text is never read, so no
   OCR engine, no language pack, no licence question.
2. Drop lonely blobs; cluster the rest into text blocks.
3. Flood-fill the enclosing white outward from each cluster.
4. Cap the filled area, so an unclosed bubble cannot leak across the page or
   run along the gutters.
5. Discard if the filled ground is dark — that is lettering on artwork, not a
   bubble.
6. Trace the fill to a polygon with `approxPolyDP`.

Parameters (`BubbleParams`):

| Param | Value | Meaning |
|---|---|---|
| `min/max_glyph_height_frac` | 0.4 / 2.5 | band around median small-component height |
| `max_glyph_aspect` | 4.0 | rejects frames and speed lines |
| `min_glyphs_per_cluster` | 3 | a lone blob is dirt |
| `cluster_dilate_px` | 15 | merges lines of one text block |
| `max_area_frac` | 0.35 | the leak cap — **needs tuning on real pages** |
| `min_area_frac` | 0.001 | smaller is a hole in the ink |
| `min_ground_brightness` | 127 | below this it is artwork, not paper |
| `max_bubbles` | 64 | hard ceiling |

**SFX lettering gets no automatic detection.** A "BOOM" over artwork has no
white to fill. If SFX gets coloured, that is acceptable — the artist masks it by
hand if they care. Revisit later.

No learned model here. Every open-source bubble detector that works is GPL,
restricted by its training dataset, or ships without weights.

### Zones
Existing: trapped-ball fill via vendored LineFiller (MIT), with `merge_fill`.
Chosen on visual comparison against real pages, not region counts.
Protected areas and anything outside a panel polygon are passed in as blocked
and come back unlabelled.

A cut (feature 16) relabels the zone map on the server — it is a relabel, never
a stroke drawn into the artwork.

### Colour generation — Cobra
Not built yet. This is the centre of the product.

- **Per panel, not per page.** Cobra runs on one panel at a time, at 384–512px,
  with the project's character sheets as reference.
- **The output is never shown.** It is an intermediate that exists only to be
  reduced to palette colours. Showing it would promise a fidelity the flats
  cannot keep.
- **Per zone:** take the **mode** of Cobra's output inside the zone's mask —
  the most frequently occurring colour, not the average — then snap it to the
  nearest palette entry in CIELAB.

  Mode, not average, because a zone is rarely one clean colour in Cobra's
  output: it has an anti-aliased rim, a gradient, maybe a stray highlight. An
  average is pulled by all of it and lands on a colour that appears nowhere in
  the zone — skin next to a dark outline averages muddy. The mode is the colour
  the zone actually mostly *is*, and outliers cannot drag it.

- **Snapping is by palette entry id, never RGB** — see rule 1.

Two things to get right when building the snap:

- **Downweight `L*`.** CIELAB has three axes: `L*` (lightness, 0 black → 100
  white), `a*` (green↔red) and `b*` (blue↔yellow). Weighted equally, the same
  skin in shadow and in light reads as two different colours, because only `L*`
  moved — and they snap to two different palette entries when the colourist
  wanted one flat. Weight `L*` less than `a*`/`b*` so matching goes on hue and
  saturation and forgives brightness. Shading is a later layer's job, never the
  flat's.
- **Reject before snapping.** If nothing in the palette is close enough, create
  a new entry and flag it rather than snapping to something wrong. Silently
  snapping a distant colour is worse than an extra entry the artist can merge.

**Licence:** Cobra is OpenRAIL++-M via its runtime PixArt pull. Keep the
dependency pinned to the diffusers repo — the raw `.pth` mirror is AGPL and
research-purpose-only. OpenRAIL's use restrictions propagate to derivatives.

**Hardware:** local NVIDIA GPU. There is no CPU path.

### Palette extraction
Existing, in `src/comiccolor/colour/extract.py`: Pillow quantize then merge
colours closer than `MERGE_DELTA_E = 12.0` in CIELAB. `K_MAX = 24`,
`MIN_PIXEL_SHARE = 0.005`. Ink below 30 and paper above 235 are dropped first.
The same extractor serves both the swatch upload (18) and the character-sheet
proposals (20).

### Export
PSD via `psd-tools`. One group per panel, one layer per colour. Flats only —
the artist keeps their own line layer.

---

## Rules that must hold

1. **Regions store a palette entry id, never RGB.** That is what makes "change
   the hair colour everywhere" one row update. Non-negotiable.
2. **Nothing runs by itself.** Every detection, segmentation and generation step
   is a button the artist presses. No background pipeline, no auto-advance.
3. **Every screen reaches the next one.** A route with no button is a feature
   that does not exist. This is what went wrong last time: panel detection,
   bubble detection and the editor route were all built, tested, and unreachable.
4. **Re-running a step replaces its output.** So it must refuse, or ask, when the
   artist has already corrected something.
5. **One coordinate transform** for screen ↔ image pixels. Everything hit-tests
   through it.
6. **Cobra's raw output never reaches the artist's eye or the export.**
7. **No line art in any export.**

---

## Not in the barebone version

- Confidence scoring across multiple seeds, flagged-zone review queue.
- Gap absorption — pixels belonging to no zone.
- Undo/redo beyond a single step.
- Metrics: post-correction time, acceptance rate, corrections per region.
- Multiple export granularities — one layer per colour is enough.
- Stage gates, confirmation dialogs, Go-Back. Buttons are the flow.
- Colour identity propagation across pages from a single hint.
- Shadow masks, shading, halftone.
- Hosting, accounts, multi-user, remote GPU.

---

## Stack

Python 3.11+, FastAPI, SQLite, numpy/opencv/scipy/pillow, pytest.
Cobra via diffusers, on a local NVIDIA GPU.
Frontend: Vite + TypeScript, no framework, no canvas library, zero runtime
dependencies. Hand-rolled 2D canvas.
Runs on one machine, tested live over video call with the artist watching.
