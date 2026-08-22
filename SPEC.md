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

### References and the retrieval pool
Cobra colours from references. Its only hard constraint is that every
reference patch is exactly half the query's width and height — whole pages are
a convention of its demo, not a requirement, so a character sheet is an
equally valid pool entry.

`ReferenceStore` keeps them in `<workdir>/references/` with a JSON index. Each
carries a `kind` (`page` | `panel` | `sheet`) that the artist sets, because it
is the one thing we cannot infer and it decides how the image is fitted.
A fourth kind, `palette`, is stored in the same place and is deliberately not
a reference: it is a strip of swatches, and the model is never shown one.

A `page` upload is stored as its panels rather than as itself. Retrieval ranks
patches, and most patches of a whole page are backgrounds and props, so the
patch covering a face can retrieve something that is not a face — measured: a
crop of one coloured face reproduced a character's skin where a whole finished
page of the same character produced a cold blue one. Panels are cropped to
their boxes, never masked to their polygons, because white padding gives the
retrieval no colour to rank.

- **sheet** — a montage, so windows are placed on the drawings themselves
  (connected components of not-paper), one character per patch.
- **page / panel** — one composition with no paper between subjects, so a grid
  of target-shaped tiles, overlapping by half.

**Nothing becomes a reference by itself.** A validated page is promoted by the
artist, never automatically — rule 2 applied to the pool. This is what keeps
it bounded, and it is the cheapest of all the available controls.

**Pool growth, for when this is measured on the GPU.** The DiT always sees
`4 × top_k` patches whatever the pool size, so the pool costs retrieval time,
never inference time. At `T=3` tiles per reference, a 50-page book is ~750
patches against the ~1000 the paper describes; 200 pages would be 3× beyond
it. Two risks, in this order:

1. *Near-duplicate crowding* — our tiles overlap, so `top_k` could return the
   same pose repeatedly and lose the diversity the whole design is for. Fix:
   dedupe the selection by overlap, not the candidate pool.
2. *CLIP cost, linear in pool.* Fix: cache embeddings by `(reference, bucket)`
   — a page's panels collapse to 2–3 distinct buckets, not one per panel.

Neither is built. Neither is measurable without the GPU, and tuning a
retrieval system that cannot be run is how the first bubble detector went
wrong.

### Zones
14. **Segment zones** button. Fills each panel with flat regions.
15. Select zones by pressing over them — a press takes one, a press-and-sweep
    takes every zone the pointer crosses — then right-click to merge them.
    Merged zones need not touch, and must share a panel.
16. Draw a line across a zone to cut it in two. The line is a cut in the zone
    map only — it never appears in any export.
16a. Both are corrections to the segmenter's proposal, so they happen at that
    stage: after **Segment zones**, before **Generate flats**. They are
    permanent — there is no unmerge, and the boundary is what protects the
    artist instead of a history that every later stage would have to
    interpret.

### Palette and character sheets
17. Recolour and delete palette colours by hand. Removing a colour un-snaps
    the zones that pointed at it: a zone cannot hold an id that is gone.
18. **Add palette** — upload an image of swatches. Every colour in it joins
    the palette, with nothing to confirm: a palette is the decision already
    made, in a file. Deleting that image takes its colours back out.
19. **Add reference** — upload a character sheet, a finished page or a
    finished panel. This is what Cobra is shown. A finished page is stored as
    its panels, because most patches of a whole page are background.
20. A reference's colours are *offered*, not taken: one chip per extracted
    colour, and the artist clicks the ones the book uses. Deleting the
    reference leaves them in the palette — they were chosen.
21. Change a colour once and every zone using it updates. No re-run, no
    regeneration. The palette is written beside the reference pool, because it
    belongs to the book.

### Generation
22. **Generate flats** button. Cobra colours each panel using the character
    sheets as reference.
23. Each zone takes the *mode* — the most common colour — of Cobra's output
    inside it, and stops there. **Flats do not snap**, even with a palette
    loaded: every zone comes out holding its own colour and its own entry.
24. Cobra's raw output is never shown. The artist sees flat, palette-bound
    zones or nothing.
25. **Snap** is its own step. Click a zone to see the colour it holds, the
    nearest palette colour and the distance between them; snap it, pick
    another colour, or put the proposal back. `snap all` is the bulk
    shortcut, and it can do nothing a click cannot.

Snapping was part of 23 until it was measured. In one pass it was the only
stage with no boundary the artist could see or refuse, and it was the stage
that folded every neutral zone into a character sheet's ink black.

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

**Panels are polygons, not boxes (D-17 revised).** D-17 originally forbade
`findContours` here, because with no frame to seal the gutter network against,
a borderless panel's surviving blob is the ink silhouette of the drawing and
tracing it returns a character-shaped polygon. That reason still holds, so the
reversal is conditional rather than total.

`diagonal_page.jpg` shows both halves at once. Its five framed panels trace
exactly — the diamond comes back as a rotated square and its four neighbours
come back notched where it bites into them — and no bounding box can express
that page at all, since the diamond's box overlaps all four. Its top panel is
borderless and traces the artwork itself at 40 vertices, which is D-17's case
verbatim.

The vertex count separates them, measured over the seven test pages at
`polygon_epsilon_frac`: framed panels come back with 4–9 vertices, borderless
artwork with 31–43. `max_polygon_vertices = 12` sits in that gap and falls
back to the box above it. The epsilon must stay fine — at 0.02 every blob on
every page collapsed to 4–5 vertices, erasing the notches and the signal with
them.

**`min_gutter_frac` is 0.009, and it is measured.** There is a cliff between
0.009 and 0.010: `tintin_page.jpg` returns 12 panels at or below, and 5 above,
because past it the disc no longer fits the gutters *between* panels of a row
and whole rows survive as one blob. The previous 0.012 was on the wrong side.
Two known failures are left alone: tintin's left column merges rows 1–2, and
the page title comes back as a panel. Per D-19 a false positive is one click
to delete, while a merge is not correctable at all — there is no split tool —
so the merge is the one worth fixing next.

**Borderless panels are the motivating case.** With no frame to seal the gutter
network, the surviving component is the ink silhouette of the drawing, not a
rectangle. So: no contour tracing (it would trace the character's outline), and
`min_solidity` stays low so silhouettes are proposed rather than silently
dropped. Over-propose; the artist deletes false positives. Never raise it back
toward 0.55 — that silently drops every borderless panel.

### Bubble detection
Built, in `src/comiccolor/segmentation/bubbles.py`. Rewritten once, and the
rewrite is the point of this section.

**The model says where. The artwork says what shape.**

1. `BubbleDetector` runs RT-DETR-v2 through `onnxruntime` and returns boxes of
   class `bubble` scoring ≥ 0.7.
2. For each box, `trace_bubble` casts 128 rays outward from its centre and
   keeps the furthest ink pixel on each, capped at the box border + 15%.
3. A circular median over the 128 lengths, then `approxPolyDP`.

Step 2 is what makes lettering harmless — the text is always nearer the centre
than the outline is. Step 3 is what makes a *broken* outline harmless: a ray
escaping through a gap is one outlier its neighbours out-vote. The result is
star-shaped, therefore always a simple polygon, and it lands **on** the outline
so the balloon border is protected too.

Parameters (`BubbleParams`): `score` 0.7, `rays` 128, `reach` 1.15, `smooth` 7,
`epsilon_frac` 0.008, `max_bubbles` 64. Nothing here needs tuning per page —
verified against `test_pages/bubble_counts.txt`, which the artist wrote.

| Page | Balloons | Found |
|---|---|---|
| `tintin_page.jpg` | 12 | 12 |
| `laurine_page.jpg` | 4 (spiky, tailed, one open) | 4 |
| `manga_page.jpg` | 4 | 4 |
| `antoine_page.png`, `moebius_page.jpg`, `teddy_page.png` | 0 | 0 |

**Known limits, both from the trace being star-shaped.** A long tail is bridged
rather than followed. A balloon with no outline drawn at all comes back as its
lettering, so its white margin stays unprotected and gets coloured.

**SFX lettering gets no automatic proposal.** This is now a choice, not a
limitation: the model returns a `text_free` class which is exactly SFX outside
balloons. Turning it on is one line, whenever hand-masking stops being enough.

#### Why the heuristic version was abandoned
The original rule — *a bubble is text surrounded by white*, read left to right:
find glyphs, cluster them, flood-fill outward, cap the area — was measured
against all six real pages and failed on every one:

- `tintin_page.jpg`: 39 proposals, **not one of them a balloon**. The glyph
  filter keyed on the page's *median* component height, which on a scan is
  compression speckle — 4 px where the lettering is 7 px. It therefore excluded
  the real lettering and admitted the noise.
- `moebius_page.jpg`, `antoine_page.png`: hatching read as `iiii`.
  `teddy_page.png`: cup holders read as `OOO`. All three have no balloons.
- `laurine_page.jpg`: a whole panel proposed as one bubble.

One cause: deciding *is this text?* from the geometry of ink blobs. Height
similarity plus a shared baseline does not separate lettering from hatching in
real artwork, and no parameter fixes that.

**The licence objection is answered, not dodged.** The reason for "no learned
model here" was that every working open-source detector is GPL, dataset-
restricted, or shipped without weights. That is still true of most of them — and
there is a sharper trap underneath it: nearly every "manga bubble YOLO" needs
the `ultralytics` package to run, and that package is **AGPL-3.0**, whatever
licence its own weights carry. RT-DETR-v2 under Apache-2.0 through
`onnxruntime` is the one mainstream path with no AGPL code in the chain. Keep
it that way.

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

## Where the barebone app stands

Built and reachable from a button: 5–16a, 17–27. Every stage proposes, and the
artist can refuse it — panel and balloon corners, zone merges and cuts, the
palette, and the colour of each zone.

Not built: 1–4 (the project folder and the SQLite store; `model/store.py`
exists and the web app does not use it), the named character behind a sheet
in 19, and creating or renaming a palette colour by hand in 17 — a colour
arrives from an image today.

---

## Not in the barebone version

- Confidence scoring across multiple seeds, flagged-zone review queue.
- Gap absorption — pixels belonging to no zone.
- Undo/redo beyond a single step.
- Metrics: post-correction time, acceptance rate, corrections per region.
- Multiple export granularities — one layer per colour is enough.
- Stage gates and Go-Back. Buttons are the flow. One exception, which rule 4
  asks for: a step that would delete the artist's own corrections asks before
  it runs.
- Colour identity propagation across pages from a single hint.
- Shadow masks, shading, halftone.
- Hosting, accounts, multi-user, remote GPU.

---

## Stack

Python 3.11+, FastAPI, SQLite, numpy/opencv/scipy/pillow, pytest.
Cobra via diffusers, on a local NVIDIA GPU.
Frontend: one HTML file, one CSS file, one JS file, served as they are. No
framework, no canvas library, no build step, zero runtime dependencies.
Hand-rolled 2D canvas.
Runs on one machine, tested live over video call with the artist watching.
