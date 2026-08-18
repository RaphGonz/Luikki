# ComicColor — how the app works

This document is the fast way into the code. `SPEC.md` tells you what the app
must be. `flatting-pipeline-spec.md` tells you why the algorithms are what they
are. This document tells you where things are and how the data moves.

The text follows ASD-STE100 Simplified Technical English: short sentences,
active voice, one idea for each sentence, and the same word for the same thing.

## 1. What the app does

An artist gives the app one page of line art. The app divides the page into
panels and into colour zones. The app then gives each zone a colour. The app
writes a layered PSD file. The artist opens that file in Photoshop or in Clip
Studio and corrects it there.

The app does not correct anything by itself. There is no editor in this
version.

## 2. How to run the app

    pip install -e ".[web,dev]"
    comiccolor serve

The command starts a local web server. Open the address that the command
prints. Options: `--proposer cobra`, `--extractor raw`, `--port`.

Run the tests with `pytest`.

## 3. The words this project uses

Use these words only with these meanings. Do not rename them in the code.

| Word | Meaning |
|---|---|
| page | One image of line art from the artist. |
| grey | The 8-bit greyscale of the page. Anti-aliased edges stay visible. |
| line mask | A boolean array. `True` is the ink of the artist. |
| structural mask | A second line mask. A neural model makes it from `grey`. |
| panel | One rectangle of the page. It holds a polygon and a position. |
| protected area | A polygon that the app must never colour. A bubble is one. |
| box | Four numbers from the bubble model: `x0, y0, x1, y1`. Not a shape. |
| zone | One flat colour area in a panel. The code calls it a region. |
| label map | An `int` array for one panel. Each value is one zone number. |
| palette entry | One colour with an id and a label. |
| proposal | An RGB image. It says which colour each pixel must be. |
| flats | The result: each zone points to one palette entry. |

**Rule that you must not break:** a zone holds a `palette_entry_id`. A zone
never holds an RGB value. This rule makes "change the hair colour on all
pages" one change to one row.

## 4. The six buttons

Nothing runs by itself. The artist starts each step. If the artist runs a step
again, the app deletes the results of all later steps.

| # | Button | Function | File |
|---|---|---|---|
| 1 | Upload page | `load_line_art` | `segmentation/preprocess.py` |
| 2 | Detect panels | `segment_panels` | `segmentation/panels.py` |
| 3 | Detect bubbles | `detect_bubbles` (a model) | `segmentation/bubbles.py` |
| 4 | Segment zones | `LineFillerSegmenter.segment` | `segmentation/segmenter.py` |
| 5 | Generate flats | `propose` then `assign_zones` | `colour/` |
| 6 | Export PSD | `write_psd` | `export/psd.py` |

A seventh input is optional: the artist can upload reference images. Each image
does two jobs. Its colours become the palette. The image itself is what the
colour model sees. See section 4a.

### Step 1 — Upload page

`load_line_art` reads the file and makes two arrays: `line_mask` and `grey`.
The function uses the alpha channel when the file has one. If the file has no
alpha channel, the function uses an Otsu threshold.

### Step 2 — Detect panels

`segment_panels` uses the **raw** line mask. First it makes the frame lines
stronger. Then it finds the network of white gutters between the panels. Then
it takes the areas that the gutters enclose. The result is a list of
`PanelBox`. `box_to_polygon` makes a four-corner polygon from each box.

The panel step must have solid blacks. This is why it does not use the
structural mask: the gutter network would go through a spot black.

### Step 3 — Detect bubbles

This step has two halves. **A model says where each balloon is. The artwork
says what shape it has.** Keep these two jobs apart. This is why a spiky
balloon, a cloud balloon and a caption box all work: no part of the shape step
expects a shape.

**Half 1 — the model.** `BubbleDetector` runs an RT-DETR-v2 network through
`onnxruntime`. The model gives boxes with a score and a class. The app keeps
class `bubble` with a score of 0.7 or more. The model has two more classes,
`text_bubble` and `text_free`. The app does not use them yet. `text_free` is
the SFX lettering outside balloons.

The weights are 161 MB. The app downloads them one time into `models/`. Set
`COMICCOLOR_BUBBLE_MODEL` to use a different file. The model needs no GPU and
takes approximately 0.85 s for each page. A large page costs the same as a
small page, because the model resizes each page to 640 x 640.

**Half 2 — the shape.** `trace_bubble` finds the outline of one balloon:

1. Find the centre of the box.
2. Send 128 rays outward from that centre.
3. On each ray, keep the distance of the **furthest** ink pixel. Do not go
   further than the box border plus 15%.
4. Apply a circular median filter to the 128 distances.
5. Make a polygon from the 128 points and simplify it.

Step 3 is what makes text safe: the lettering is always nearer to the centre
than the outline is. Step 4 is what makes a broken outline safe: a ray that
escapes through a gap is one value, and its neighbours out-vote it.

The polygon is star-shaped. Therefore it is always simple, and it can never
fold back around the text. The polygon lands **on** the outline, so the black
outline is protected too.

The app does not read the text. There is no OCR engine and no language pack.

### Step 4a — References (optional, at any time)

The references are the images that the colour model looks at. They belong to
the book, not to the page. Thus they stay when the artist loads a new page,
and they stay when the app stops and starts again.

`ReferenceStore` (`colour/references.py`) keeps them in
`<workdir>/references/`: one file for each image, and an `index.json`. Each
record has an id, a filename, a label, a `kind` and a date. Ids increase and
the app never uses an id again.

`kind` is one of three values:

| kind | Meaning |
|---|---|
| `page` | A finished coloured page of this book. |
| `panel` | One finished coloured panel. |
| `sheet` | A character sheet or a colour swatch. |

The artist selects the kind. The app cannot find it out from the image. The
kind does not change how the app stores the image. The kind tells the colour
step how to fit the image to the panel later.

**The app stores each image complete. The app does not cut it.** Cobra needs
each reference part to be one half of the width and the height of the panel.
To get that size, the app must fit the image to the shape of the panel. The
app does not know the shape of the panel before segmentation. Therefore the
app cuts the image at colour time, not at upload time. Section 5a tells you
how the app cuts it.

The palette has two halves:

- The **reference half** comes from the references. If you remove a reference,
  its colours go away with it. The app makes this half again from all the
  references each time one changes.
- The **created half** is what step 5 invented for zones that matched no
  colour.

`extract_palette` uses median cut, which always gives the same result.
Therefore the app does not save the palette. The app makes it again from the
files.

### Step 4 — Segment zones

This step does not use the ink of the artist. First `structural_mask()` runs
the MangaLineExtraction model on `grey`. The model gives back structural
lines. A thick brush stroke becomes one thin line. A spot black becomes its
outline.

Then, for each panel:

1. `_blocked_for` makes the blocked mask. It contains the protected areas and
   everything outside the panel polygon.
2. `LineFillerSegmenter.segment` runs trapped-ball fill on the structural
   lines of that panel. The result is a label map.
3. `expand_under_lines` makes the zones grow below the ink. It uses the
   **raw** line mask here, because the ink layer of the artist goes on top.
   Without this step each line leaves a white gap in the export.

### Step 5 — Generate flats

For each panel the app builds a `PanelRequest` and calls the proposer. The
proposer gives back a proposal raster.

The `line_art` in the request is the box of the panel, but the app first makes
all pixels outside the polygon of the panel white. A box is the panel only when
the panel is a rectangle. For an L-shaped panel the box also holds a part of
the panel next to it. The colour model must not look at that part. For a
rectangular panel this step changes nothing.

`assign_zones` then takes the **mode** colour of each zone from that raster.
It does not take the average. Then it finds the nearest palette entry in
CIELAB space. If the distance is more than `SNAP_MAX_DELTA`, the app flags the
zone.

If the artist uploaded no palette, there is nothing to snap to. Each zone then
becomes a new palette entry of its own.

The proposal raster is never shown and never exported. It exists only to give
one colour to each zone.

There are two proposers:

- `DistinctColourProposer` (`distinct`) is the default. It gives a different
  colour to each zone. It needs no GPU. This is classical flatting output.
- `CobraProposer` (`cobra`) needs an NVIDIA GPU with much VRAM. Its code is
  written but **nobody has run it**. Test it on the GPU machine first.

Everything after this step reads the proposal raster only. To change the
proposer, change one constructor call.

### Step 5a — How the app fits images to Cobra

Cobra accepts only some shapes. It has a list of 15 shapes ("buckets"). The
widest is 2.06:1 and the tallest is 1:2.06. Real panels are not always in that
range: on the test pages they go from 0.63:1 to 3.38:1.

**The panel goes on a white rectangle.** `_letterbox` (`colour/cobra.py`)
makes the panel as large as possible in the bucket, keeps its shape, and fills
the rest with white. After the model runs, the app cuts the white away again.

Do not squash the panel to make it fit. A squashed face is a face that the
model must recognise through a distortion that no comic has. The app loses
some resolution instead. Resolution does not matter here, because the app
keeps only one colour for each zone and then deletes the raster.

**The reference is cut into tiles.** `_tiles` (`colour/cobra.py`) cuts the
image into pieces that have the shape of the bucket. The way it cuts depends
on the `kind`.

For a `sheet`, the app puts one window on each drawing (`_subject_tiles`). A
character sheet is drawings with paper between them. Therefore the app finds
the drawings as the connected parts of "not paper". Then it makes a window of
the correct shape around each drawing and cuts it out. The result is one
character in each piece, at a size that the retrieval step can use. If the app
finds fewer than 2 drawings, the image is not a montage, and the app uses the
grid instead.

For a `page` or a `panel`, the app uses a grid: it cuts pieces that have the
shape of the bucket, and the pieces overlap by one half. Nothing is lost. A
page has no paper between its subjects, so there is nothing to put a window
on.

Do not put a reference on a white rectangle. White pixels in a reference are
of no use: a reference must give colours. Cut it instead.

If the shape of the reference is already near to the shape of the bucket (a
difference of less than 15%), the app makes one tile from the whole image.
This is the same rule Cobra uses.

The `kind` of the reference gives the number of tiles: a `sheet` gets 6, a
`page` or a `panel` gets 3. A sheet holds many separate drawings and needs
more tiles. **These two numbers are a guess. Measure them on the GPU machine.**

Measured on `test_pages/laurine_ref.jpg` (a real character sheet, 1440 x 1440,
13 drawings): against a tall panel, the grid gives 2 pieces, and each one is a
wall of 7 small figures. The drawing windows give 6 pieces, and each one shows
one character at a size you can read.

**How the pool grows.** Cobra always shows the model `4 x top_k` pieces. This
number does not change with the size of the pool. Thus more references make
the search more costly, but never the model. Two dangers stay:

1. The cost of the CLIP step increases with the number of references.
2. Pieces that overlap can fill the `top_k` with the same view many times.

An artist adds each reference by hand. Nothing becomes a reference by itself.
This is the rule that keeps the pool small.

### Step 6 — Export PSD

`write_psd` makes one layer group for each panel. It makes one layer for each
palette colour. Read the comment on `_set_preview` in `export/psd.py` before
you change that file. Without that function the export takes eight minutes.

## 5. Where the state is

`src/comiccolor/web/session.py` holds all the state of the app in one
`Session` object. One page is in the app at a time. A new page replaces the
old one. The palette and the reference images stay, because they belong to the
book and not to the page.

A lock makes the buttons sequential. The artist will click two times.

`src/comiccolor/model/store.py` is a full SQLite store with the same shape.
This version of the app **does not use it**. Persistence is not the purpose of
this version.

`src/comiccolor/web/app.py` is the FastAPI layer. Each button is one POST
route. Each preview image is one GET route that sends a PNG.

## 6. Map of the source files

    src/comiccolor/
      cli.py                  the `comiccolor` command
      web/session.py          all state, the six buttons        <- start here
      web/app.py              the HTTP routes
      segmentation/
        preprocess.py         file -> line_mask + grey
        panels.py             gutter network -> panel boxes
        bubbles.py            RT-DETR box -> ray trace -> polygon
        segmenter.py          the LineFiller adapter
        trappedball.py        the fill parameters, expand_under_lines
        closure.py            gap closure experiments
        protected.py          polygons -> a panel-local blocked mask
      extract/
        manga_line.py         the MangaLineExtraction model
        passthrough.py        the `raw` extractor: no model
      colour/
        references.py         the reference images on disk + index.json
        proposer.py           the ColourProposer protocol, `distinct`
        cobra.py              the Cobra proposer. Never executed.
        snap.py               zone mode -> nearest palette entry (CIELAB)
        extract.py            image -> palette colours
      export/psd.py           panels -> a layered PSD
      model/                  the SQLite store. Not used by the web app.
      spike/                  the A/B experiments. Reports are in `reports/`.

## 7. Facts that you must not lose

- Evaluate on **real ink layers** only. Never evaluate on extracted lines.
  Extracted lines are closed and clean. Real ink is not. A test set of
  extracted lines measures nothing.
- The zone count is an alarm, not a score. Decide segmentation changes on the
  rendered images in `reports/`, not on the count.
- Export PSD only. The `.clip` format is an undocumented SQLite container.
  Clip Studio reads PSD and keeps the groups.
- Keep Cobra as the `diffusers` repository dependency. The raw `.pth` mirror is
  AGPL and permits research only.
- Do not install Cobra on the development machine. Its card is too small.
- Cobra does not need complete pages. Its only rule is that each reference part
  is one half of the width and the height of the panel. A character sheet is
  as good as a page.
- Do not squash a panel to fit the shape that Cobra accepts. Put the panel on
  a white rectangle instead. Measured on the test pages, panels go from 0.63:1
  to 3.38:1, and 13 of 23 panels get squashed more than 5%.
- Do not put a reference on a white rectangle. Cut it into tiles. White pixels
  give no colour, and a reference is there only to give colour.
- `colour/cobra.py` has never run. Its shape functions have tests, but the
  model itself is not tested. Verify it on the GPU machine.
- Keep the bubble detector on `onnxruntime`. Nearly every other comic balloon
  detector on GitHub needs the `ultralytics` package, and that package is
  AGPL-3.0. The licence of the weights does not change this.

## 8. Known problems

- **A balloon with a long tail loses its tail.** A star-shaped polygon cannot
  follow a concave shape, so the trace goes across the tail and not around it.
- **A balloon with no outline comes back as its text block only.** The trace
  has no boundary to find, so the white margin of that caption stays
  unprotected and the app colours it.
- **The shape can be a little too large.** Where a ray finds no ink, it stops
  at the box border. This shows as slack around the oval balloons in
  `manga_page.jpg`.
- **Nothing is correctable in the app.** A wrong panel or a wrong bubble goes
  to Photoshop, or the artist does not press that button.
- Segmentation is slow. A large page takes approximately two minutes. The cost
  is in LineFiller.

## 9. Tests

`pytest` runs all tests. `tests/test_web.py` presses each button in sequence
through the HTTP API. It then opens the PSD that comes out. Keep that test
working: it is the proof that each screen goes to the next one.
