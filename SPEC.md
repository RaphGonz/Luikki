# Luikki — barebone spec

The smallest version of the app that is actually usable end to end. Build this
first, develop from it later.

`flatting-pipeline-spec.md` remains the long-form architecture reference.

---

## The user story

> A colourist opens Luikki and drops in a page of line art.
>
> They press **Detect panels** and see the panels outlined. Two are wrong, so
> they drag a corner, delete one the app invented, and draw one it missed.
>
> They press **Detect bubbles** and see the speech balloons outlined. One is
> missed, so they draw it by hand.
>
> They press **Cut into zones** and each panel fills with flat regions. Two
> regions should be one, so they click both to merge. One region should be two,
> so they draw a line across it to cut it.
>
> They press **Find the planes**. Every zone lands on the 1st plane, the 2nd
> plane or the background, read off the depth of the drawing. A few are on the
> wrong one, so they sweep them and move them; they sweep the two heroes and
> call them characters.
>
> They press **Export** and get a PSD — one layer per plane, the balloons on
> top, fake flat colours inside — that they open in Photoshop, drop their own
> line layer on top, select each zone with the magic wand and colour.

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
14. **Cut into zones** button. Fills each panel with flat regions, cut from
    the whole of the ink; line extraction is an option of each page.
15. Select zones by pressing over them — a press takes one, a press-and-sweep
    takes every zone the pointer crosses — then right-click to merge them.
    Merged zones need not touch, and must share a panel.
16. Draw a line across a zone to cut it in two. The line is a cut in the zone
    map only — it never appears in any export.
16a. Both are corrections to the segmenter's proposal. They open after
    **Cut into zones** and stay open over the planes. A merged zone, and every
    piece of a cut, votes again on the depth under it. There is no unmerge;
    Ctrl+Z takes back the last few edits, until the zones are cut or the
    planes found again.

### Planes (ROADMAP G2)
17. **Find the planes** button, optional: **Skip** goes to the export. Depth
    Anything V2 Small reads each panel; its values are cut into three groups
    (1st plane, 2nd plane, background); every zone takes the group most of its
    pixels are in. A zone is never split, and the depth draws no boundary.
18. The artist moves zones between planes, with the gestures of step 4, and is
    the only one who calls zones **characters**. Ctrl+Z takes a move back.

### Export
19. **Export** button. PSD, one layer per plane: Background, Middle ground,
    Foreground, Characters, Balloons on top; one layer of flats if the planes
    were skipped. « By plane and by colour » makes each plane a group of
    colour layers, every object apart: 33 layers at most.
20. Inside a layer, eight fake flat colours; two zones that touch never share
    one, so the magic wand takes one zone. Luikki proposes no colour.
21. No line art in the export unless asked for (the printer's support grey).

---

## Algorithms

### Panel detection
Already built, in `src/luikki/segmentation/panels.py`.

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
Built, in `src/luikki/segmentation/bubbles.py`. Rewritten once, and the
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

### Planes
`segmentation/planes.py`. Per panel: crop on the polygon's box, Depth Anything
V2 **Small** at 518 px on the long side (Apache-2.0; Base and Large are
CC-BY-NC-4.0 and never used), back to the crop's size. A 1-D k-means in three
groups on the panel's own values, started from the quantiles so a page gives
the same planes on every run: the highest centre is the 1st plane. Each zone
takes the **majority** group under its pixels, never the mean. The groups are
kept per panel so a zone cut or merged later votes again.

### Fake flats
`export/flat_colours.py`. Eight well-separated colours (Okabe-Ito, black
swapped for pale pink), as palette entries 1–8. A greedy colouring of the
page's zone adjacency in 8-connectivity, in zone order, each zone taking the
free colour the page has used least. Given again after every change to the
zones.

### Export
PSD via `psd-tools`. One layer per plane, or a group per plane with one layer
per colour. Flats only — the artist keeps their own line layer.

---

## Rules that must hold

1. **Regions store a palette entry id, never RGB.** Non-negotiable, even with
   eight fake entries.
2. **Nothing runs by itself.** Every detection, segmentation and generation step
   is a button the artist presses. No background pipeline, no auto-advance.
3. **Every screen reaches the next one.** A route with no button is a feature
   that does not exist. This is what went wrong last time: panel detection,
   bubble detection and the editor route were all built, tested, and unreachable.
4. **Re-running a step replaces its output.** So it must refuse, or ask, when the
   artist has already corrected something.
5. **One coordinate transform** for screen ↔ image pixels. Everything hit-tests
   through it.
6. **No model draws a boundary.** Depth labels zones; the ink cuts them.
7. **No line art in any export** the artist did not ask for.

---

## Where the barebone app stands
Built and reachable from a button: 5–21. Every stage proposes, and the artist
can refuse it — panel and balloon corners, zone merges and cuts, and each
zone's plane.

Built differently: 1–4. The project is the working folder, and it holds JSON
and image files rather than a SQLite database — simpler to read and to debug
(`web/project.py`). Every edit saves before it returns, and the app reopens
the page that was open. `model/store.py` stays unused.

Dropped on 2026-10-01 (ROADMAP G): Cobra, references, the palette, snapping —
every colour the app used to propose. Testers judged the colours unusable.

---

## Not in the barebone version

- Confidence scoring across multiple seeds, flagged-zone review queue.
- Gap absorption — pixels belonging to no zone.
- Undo/redo beyond a single step.
- Metrics: post-correction time, acceptance rate, corrections per region.
- Stage gates and Go-Back. Buttons are the flow. One exception, which rule 4
  asks for: a step that would delete the artist's own corrections asks before
  it runs.
- Colour identity propagation across pages from a single hint.
- Shadow masks, shading, halftone.
- Hosting, multi-user. (An account exists, for the licence only.)

---

## Stack

Python 3.11+, FastAPI, numpy/opencv/scipy/pillow, onnxruntime, pytest.
Models on onnxruntime: MangaLineExtraction, an RT-DETR balloon detector, Depth
Anything V2 Small. GPU when there is one, CPU otherwise.
Frontend: one HTML file, one CSS file, one JS file, served as they are. No
framework, no canvas library, no build step, zero runtime dependencies.
Hand-rolled 2D canvas.
Runs on one machine, tested live over video call with the artist watching.
