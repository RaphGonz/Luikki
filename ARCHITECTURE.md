# Luikki — how the app works

This document is the fast way into the code. `SPEC.md` tells you what the app
must be. `flatting-pipeline-spec.md` tells you why the algorithms are what they
are. This document tells you where things are and how the data moves.

The text follows ASD-STE100 Simplified Technical English: short sentences,
active voice, one idea for each sentence, and the same word for the same thing.

## 1. What the app does

An artist gives the app one page of line art. The app divides the page into
panels and into colour zones. The app then gives each zone a colour. The app
writes a layered PSD file. The artist opens that file in Photoshop or in Clip
Studio and finishes the page there.

The app does not correct anything by itself. The artist corrects it. Each
stage gives a proposal, and the artist can refuse it:

| Stage | What the artist corrects |
|---|---|
| 2 Detect panels | Drag a corner. Add a corner. Draw a panel. Delete a panel. |
| 3 Detect bubbles | The same four actions, on the balloons. |
| 4 Segment zones | Merge many zones into one. Cut one zone in two. |
| Palette | Change a colour. Every zone with that colour changes. |
| 6 Snap | Point one zone at one palette colour, or put the proposal back. |

Each correction is possible at one stage only. The stage closes when the next
stage uses its result. Section 4 gives the rule for each one.

## 2. How to run the app

    pip install -e ".[web,dev]"
    luikki serve

The command starts a local web server. Open the address that the command
prints. Options: `--proposer cobra|remote`, `--extractor raw`, `--port`.

    pip install -e ".[desktop]"
    luikki app

The same app in its own window, as the installed app runs it (`desktop.py`).
The server takes a free port of 127.0.0.1, and closing the window stops it.
`--proposer` defaults to `remote`; `--debug` opens the web inspector.

Run the tests with `pytest`.

## 3. The words this project uses

Use these words only with these meanings. Do not rename them in the code.

| Word | Meaning |
|---|---|
| page | One image of line art from the artist. |
| grey | The 8-bit greyscale of the page. Anti-aliased edges stay visible. |
| line mask | A boolean array. `True` is the ink of the artist. |
| structural mask | A second line mask. A neural model makes it from `grey`. |
| panel | One area of the page. It holds a polygon and a box. Not always a rectangle. |
| protected area | A polygon that the app must never colour. A bubble is one. |
| box | Four numbers from the bubble model: `x0, y0, x1, y1`. Not a shape. |
| zone | One flat colour area in a panel. The code calls it a region. |
| label map | An `int` array for one panel. Each value is one zone number. |
| palette entry | One colour with an id and a label. |
| proposal | An RGB image. It says which colour each pixel must be. |
| flats | The result: each zone points to one palette entry. |
| segment | One zone after step 5. It holds the palette entry, the area, the box and one point inside the zone. |
| candidate | One colour that a reference offers. It is not in the palette until the artist clicks it. |
| palette image | An image of swatches. Every colour in it goes into the palette. |

**Rule that you must not break:** a zone holds a `palette_entry_id`. A zone
never holds an RGB value. This rule makes "change the hair colour on all
pages" one change to one row.

## 4. The seven buttons

Nothing runs by itself. The artist starts each step. If the artist runs a step
again, the app deletes the results of all later steps. A step that deletes
work asks the artist first. The question is in the rail, and it names what the
step deletes.

| # | Button | Function | File |
|---|---|---|---|
| 1 | Upload page | `load_line_art` | `segmentation/preprocess.py` |
| 2 | Detect panels | `segment_panels` | `segmentation/panels.py` |
| 3 | Detect bubbles | `detect_bubbles` (a model) | `segmentation/bubbles.py` |
| 4 | Segment zones | `LineFillerSegmenter.segment` | `segmentation/segmenter.py` |
| 5 | Generate flats | `propose` then `assign_zones` | `colour/` |
| 6 | Snap | `snap_segment`, `snap_all` | `colour/segments.py`, `colour/snap.py` |
| 7 | Export PSD | `write_psd` | `export/psd.py` |

Step 3 needs step 2. The app refuses step 3 before step 2. The rail shows that
refusal before the click: a locked step says what to do first. The steps run in
one order, because the artist corrects the result of each one, and a step that
runs again deletes those corrections.

Two more inputs are optional, and they are not the same thing. **Add
reference** gives the colour model an image to look at. **Add palette** gives
the palette an image of swatches. See section 4a.

### Step 1 — Upload page

`load_line_art` reads the file and makes two arrays: `line_mask` and `grey`.
The function uses the alpha channel when the file has one. If the file has no
alpha channel, the function uses an Otsu threshold.

### Step 2 — Detect panels

`segment_panels` uses the **raw** line mask. First it makes the frame lines
stronger. Then it finds the network of white gutters between the panels. Then
it takes the areas that the gutters enclose. The result is a list of `Panel`.
Each `Panel` holds a polygon and a box.

The panel step must have solid blacks. This is why it does not use the
structural mask: the gutter network would go through a spot black.

**A panel is a polygon. The box says only where to cut.** A panel is not
always a rectangle. It can be a diamond, or it can have a piece missing where
another panel touches it. For such a panel, the box is not the panel: the box
of a diamond also covers a part of each panel next to it. The app cuts the box
out of the page, and then makes all pixels outside the polygon white.

`_panel_polygon` makes the polygon:

1. Trace the outline of the area.
2. Simplify the outline. Use a tolerance of 0.5% of the length of the outline.
3. If the result has more than 12 corners, the area is artwork and not a
   panel. Use the box.

Step 3 is necessary. A panel with no frame gives no closed area to the gutter
step. The area that stays is the drawing itself. If you trace it, you get the
shape of the character and not the shape of the panel.

Measured on the 7 test pages: a panel with a frame gives 4 to 9 corners.
Artwork with no frame gives 31 to 43 corners. The limit of 12 is between these
two groups.

Keep the tolerance small. At 2%, all areas on all pages gave 4 or 5 corners.
That removes the missing piece of a panel, which is the reason to trace.

**The artist corrects the panels here.** Detection gives a proposal. The
artist clicks inside a panel to select it, drags a corner, clicks an edge to
add a corner, clicks outside the panels to draw a new panel (Shift-click draws
inside one), or right-clicks to delete a corner or a panel. Each action sends
the complete polygon to the server. The server does not receive an edit. It
receives the shape.

`set_panel_polygon`, `add_panel` and `delete_panel` are in `web/session.py`.
Each one puts the panels back into reading order with `panels._reading_order`.
The number in the corner of a panel is the order of the groups in the PSD.

The artist can correct the panels until step 4 cuts the zones. After that the
app refuses, because the zones come from the shape of the panel. To open the
geometry again, press Detect panels. That deletes the corrections.

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
`LUIKKI_BUBBLE_MODEL` to use a different file. The model needs no GPU and
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

### Step 4a — References and the palette (optional, at any time)

A reference and the palette are two different things. A reference is an image
that the colour model looks at. The palette is the list of colours of the
artist. Both belong to the book, not to the page. Thus they stay when the
artist loads a new page, and they stay when the app stops and starts again.

`ReferenceStore` (`colour/references.py`) keeps them in
`<workdir>/references/`: one file for each image, and an `index.json`. Each
record has an id, a filename, a label, a `kind` and a date. Ids increase and
the app never uses an id again.

`kind` is one of four values. Three of them are references:

| kind | Meaning |
|---|---|
| `page` | A finished coloured page of this book. The app stores its panels. |
| `panel` | One finished coloured panel. |
| `sheet` | A character sheet. |
| `palette` | An image of swatches. It is **not** a reference. |

The artist selects the kind. The app cannot find it out from the image. The
kind tells the colour step how to fit the image to the panel later.

`palette` is not in `KINDS` and `reference_images()` does not return it. The
colour model never sees it. A strip of swatches is not an example of a
coloured page.

**A finished page becomes its panels.** `add_reference` runs panel detection
on a `page` upload. The app stores one `panel` reference for each panel that
it finds. The app does not keep the page. Cobra reads patches of a reference,
and most patches of a whole page are background. A patch that covers a face
can then find something that is not a face. A page with no panels that the app
can find stays complete, because half of a split is worse than none.

The app cuts each panel to its box. The app does not make the pixels outside
the polygon white. White pixels give no colour, and a reference is there only
to give colour. A part of the panel next to it is drawn colour, and that is
better than white.

**The app does not fit a reference to a panel at upload time.** Cobra needs
each reference part to be one half of the width and the height of the panel.
The app does not know the shape of the panel before segmentation. Therefore
the app tiles the image at colour time. Section 5a tells you how.

**The palette is a list. It is not a result.** `extract_palette` reads the
colours of an image. What happens next depends on the door:

- **Add reference** offers the colours. They are candidates. The app shows one
  chip for each candidate below the thumbnail. The artist clicks a chip to put
  that colour in the palette. A drawing is not a decision: the extraction
  cannot tell the jacket of a character from the wall behind it.
- **Add palette** takes all the colours. There are no chips. A palette image
  is the decision of the artist, already made, in a file.

To delete is not the same at the two doors. If you delete a palette image, its
colours go with it. If you delete a reference, the palette does not change: the
artist selected those colours one at a time, and a click about an image must
not repaint the page.

The app gives each palette entry an id one time. The app never uses an id
again, and never renumbers. A zone holds an id. An id that means a different
colour tomorrow is worse than no id.

**To change a palette colour changes every zone that holds it.** There is no
new segmentation and no new proposal. `flats_rgba` and `write_psd` read the
palette when the artist asks for the image. One row changes the page. This is
the reason for the rule in section 3.

The app writes the palette to `<workdir>/palette.json`. The palette belongs to
the book, like the references, so it must survive a restart.

`_created_palette` is the other half of the palette. Step 5 makes one private
entry for each zone. Those entries belong to the page. They are not offered to
the artist and the artist never snaps to them: a segment must not be offered
its own colour.

**The artist corrects the balloons here.** The actions are the same four as
for the panels, and they use the same code path in the browser. The methods
are `set_bubble`, `add_bubble` and `delete_bubble`. The rule is the same too:
the artist corrects the balloons until step 4 cuts the zones.

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
3. `split_open_borders` audits the result. It only divides a zone, never moves
   one. A border that is ink with a hole in it is a leak and the zone is cut.
   A border that is open along its whole length is a passage and it is not.
4. `absorb_micro_zones` gives every crumb the label of the neighbour that
   encloses it: small **as a share of the panel**, and one neighbour holding
   over 80% of its border. Before the expansion below, or the border would be
   measured on shapes already fused under the strokes.
5. `expand_under_lines` makes the zones grow below the ink. It uses the
   **raw** line mask here, because the ink layer of the artist goes on top.
   Without this step each line leaves a white gap in the export.
6. `expand_under_lines` runs a second time on everything that is left. The
   zones were cut on the structural lines but grown under the real ink, so a
   pixel the extractor called line and the artist's ink does not cover belongs
   to no zone at all. Nothing covers it at export either, so it takes the
   nearest label. Two holes stay holes: what is protected, and the artist's
   own spot black, which `inked_zones` finds before the expansion and punches
   out after it.

`panel.orphans` counts what still has no zone once those two exceptions are
taken out. It should read 0. Like the zone count it is an alarm, not a score.

**The artist corrects the zones here.** Trapped-ball reads the ink, and the
ink is not always closed. Two failures follow. The fill goes through a gap and
one zone holds a garment and the background. Or the drawing is busy and one
pair of trousers comes back as forty zones.

The artist selects a zone while the button is down over it. To press picks up
one zone. To hold the button and move picks up each zone that the pointer
touches. Two zones far apart need two presses, and nothing between them is
selected, because the button was up. To press a selected zone drops it. A
sweep only adds.

Right-click gives the actions, and the inspector shows the same actions as
buttons. Two or more zones give **merge**. Exactly one zone gives **cut**: with
more, the app cannot know which zone a stroke belongs to.

- `merge_zones` writes the label of the largest zone over the others. The
  zones do not need to touch. The panes of a glass are one thing to colour.
  The zones must be in one panel: a label belongs to a panel, and the same
  shirt in the next panel is the work of the palette.
- `cut_zone` draws the stroke of the artist as a wall inside the zone, then
  runs connected components. The stroke is the ink line that is not there. The
  app makes both ends of the stroke longer, because to stop a few pixels short
  is the usual reason a cut fails. The pixels of the stroke go to the piece
  that is nearest, so the cut leaves no unassigned pixels for the export to
  fringe around. A stroke that separates nothing changes nothing, and the app
  says so.

**These corrections are permanent.** There is no unmerge. To keep one would
mean to hold the map of the segmenter beside the map of the artist, and each
later stage would have to say which of the two it uses. The stage boundary
protects the artist instead. The stage opens when the zones exist and closes
when step 5 colours them.

### Step 5 — Generate flats

For each panel the app builds a `PanelRequest` and calls the proposer. The
proposer gives back a proposal raster.

The `line_art` in the request is the box of the panel, but the app first makes
all pixels outside the polygon of the panel white. A box is the panel only when
the panel is a rectangle. For an L-shaped panel the box also holds a part of
the panel next to it. The colour model must not look at that part. For a
rectangular panel this step changes nothing.

`assign_zones` then takes the **mode** colour of each zone from that raster.
It does not take the average.

**Step 5 does not snap.** The app calls `assign_zones` with `threshold=None`
every time. Each zone gets a new palette entry of its own, whatever the
palette holds. Snapping is step 6, and the artist does it.

The reason is a measured failure. Snapping used to happen in this same pass.
It was then the one stage with no boundary: the artist could not see it and
could not refuse it. It was also the stage that made every neutral zone the
ink black of a character sheet.

The proposal raster is never shown and never exported. It exists only to give
one colour to each zone.

Step 5 also builds the segments. `build_segments` gives each zone its area,
its box in page space, and one point inside the zone. A crescent anchors on
its own pixels, not on the centre of its box. The segments are the unit of
work from here on.

There are two proposers:

- `DistinctColourProposer` (`distinct`) is the default. It gives a different
  colour to each zone. It needs no GPU. This is classical flatting output.
- `CobraProposer` (`cobra`) needs an NVIDIA GPU with much VRAM. It runs on the
  machine of the artist. `README.md` has the numbers of the first real runs.
- `RemoteProposer` (`remote`) is Cobra on a GPU somewhere else. It sends the
  line art, the references and the hints of one panel to `POST /v1/panel`
  (`cloud/server.py`) and reads back the raster. The zone map does not leave
  the machine. It needs `LUIKKI_REMOTE_URL` and a signed-in account
  (`account.py`), whose session is the only way into the server.

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

### Step 6 — Snap

One segment at a time, and the artist decides each one. The artist clicks a
zone. `segment_at` finds it in the label map, not in the boxes of the
segments: the boxes of two zones that interlock overlap, and a click must find
the zone under the pointer.

`snap_suggestion` gives the nearest colour of the palette **and the distance**
to it. The artist sees the number that the old automatic pass used in silence.
`SNAP_MAX_DELTA` orders the attention of the artist. It does not refuse the
instruction of the artist.

- `snap_segment` points one segment at one palette entry. One row changes.
- `unsnap_segment` puts back the colour that the proposer gave. A snap that
  the artist cannot undo takes the decision away from them.
- `snap_all` is the bulk action for a page whose references are good. It calls
  `snap_segment` for each segment, so it can do nothing that a click cannot,
  and each segment stays reversible one at a time. **It has no threshold by
  default**: what the artist wants is their own palette, not five hundred
  invented colours, and the fastest way there is to snap everything and correct
  what is wrong. The guard is what they switch on, not what they switch off.

The suggestion uses the palette of the artist only. It never uses the private
entries of step 5. Those hold the colour of the segment itself, and each
segment would find itself at distance zero.

### Step 7 — Export PSD

`write_psd` makes one layer for each palette colour. `granularity` says how
they stack:

- `colour` (the default) puts one layer per palette entry over the whole page.
  The same colour in five panels is one layer. This is rule 1 made selectable:
  one selection recolours every occurrence.
- `panel` puts one group per panel, one layer per colour inside it, for the
  colourist who works panel by panel.

Both composite to the same page, which is what makes the choice safe.
`layer_count` says how many layers a stack would write without writing them.
Step 7 in the rail reads it, and it warns past `EXPORT_LAYER_WARNING` before
the artist clicks.
A count that high means the page is still wearing the model's guesses, one
private entry per segment, and Snap all is the answer.

Read the comment on `_set_preview` in `export/psd.py` before you change that
file. Without that function the export takes eight minutes.

## 5. Where the state is

`src/luikki/web/session.py` holds all the state of the app in one
`Session` object. One page is in the app at a time. A new page replaces the
old one. The palette and the reference images stay, because they belong to the
book and not to the page.

A lock makes the buttons sequential. The artist will click two times.

`Session.progress` (`web/progress.py`) tells the browser how far a long step
is. `GET /api/progress` reads it without the lock, because the step holds the
lock for its whole run. A tick is a finished piece of work: one tile of the
extractor, one pass of LineFiller, one panel. `Session._learn` measures what
each pass costs on this machine, so the steps of the bar match that machine.
The route sends codes, not words.

`src/luikki/model/store.py` is a full SQLite store with the same shape.
This version of the app **does not use it**. Persistence is not the purpose of
this version.

The palette does not stay in memory only. `Session` writes it to
`<workdir>/palette.json` at each change and reads it at start. The reference
images and their `index.json` are in `<workdir>/references/`.

`src/luikki/web/app.py` is the FastAPI layer. Each button is one POST
route. Each preview image is one GET route that sends a PNG. A correction is
also one route: the browser sends the complete shape, the complete stroke, or
the complete colour. It never sends an edit.

`src/luikki/web/static/` is the browser. `UI.md` gives its layout, its colours
and its rules. The step rail on the left controls the canvas: the open step
decides what the canvas shows and what a click does. The canvas controls the
inspector on the right, which shows what the click selected.

`app.js` holds one screen-to-page transform, `view`. Nothing else in that file
converts coordinates. Each hit test goes through `view.toImage` and then asks
the server what is there. The browser never holds a second copy of the
segmentation. The outline of a selected zone comes from the mask that the
server sends for that zone (`/api/zone/{panel}/{label}.png`).

No word that the artist reads is in `index.html` or in `app.js`. Each word is a
key in `static/locales/en.json`, and `t("key")` looks it up. A new language is
a new file in `locales/` and one entry in `LOCALES`. `?lang=en-XA` shows a
pseudo-language: text that stays plain English is text that is in the code.

No colour is in `app.js`. Each colour is a token in the `:root` block of
`app.css`. The canvas reads the tokens one time, at start.

## 6. Map of the source files

    src/luikki/
      cli.py                  the `luikki` command
      desktop.py              `luikki app`: the server in a thread, a window on it
      web/session.py          all state, the seven buttons      <- start here
      web/app.py              the HTTP routes
      web/progress.py         how far a long step is, for the progress bar
      web/static/index.html   the shell: header, rail, canvas, inspector, footer
      web/project.py          the project folder: every page saved as it is edited
      web/static/app.js       the rail, the canvas, the corrections, one transform
      web/static/app.css      the tokens of UI.md, then the styles
      web/static/locales/     every word of the interface, one file a language
      segmentation/
        preprocess.py         file -> line_mask + grey
        panels.py             gutter network -> panel polygons
        bubbles.py            RT-DETR box -> ray trace -> polygon
        segmenter.py          the LineFiller adapter
        trappedball.py        the fill parameters, expand_under_lines
        leaks.py              the leak audit: a line with a hole gets cut
        absorb.py             the crumbs join the neighbour enclosing them
        closure.py            gap closure experiments
        protected.py          polygons -> a panel-local blocked mask
      extract/
        manga_line.py         the MangaLineExtraction model
        passthrough.py        the `raw` extractor: no model
      colour/
        references.py         the reference images on disk + index.json
        proposer.py           the ColourProposer protocol, `distinct`
        cobra.py              the Cobra proposer
        remote.py             the `remote` proposer: Cobra over HTTP
        segments.py           one zone as a thing the artist can click
        snap.py               zone mode -> nearest palette entry (CIELAB)
        extract.py            image -> palette colours
      export/psd.py           panels -> a layered PSD
      cloud/
        protocol.py           what client and server agree on: fields, PNG
        server.py             POST /v1/panel: session, quota, then the proposer
        modal_app.py          the server on a Modal L4, weights in a Volume
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
- Do not install Cobra on the development machine. Its card is too small. The
  machine of the artist runs it.
- Cobra does not need complete pages. Its only rule is that each reference part
  is one half of the width and the height of the panel. A character sheet is
  as good as a page.
- A panel is its polygon. The box is only where to cut. Never use the box as
  the shape: a diamond panel's box covers a part of four other panels.
- Do not trace an area that has more than 12 corners. It is artwork, not a
  panel, and its shape is the shape of a character.
- Do not squash a panel to fit the shape that Cobra accepts. Put the panel on
  a white rectangle instead. Measured on the test pages, panels go from 0.63:1
  to 3.38:1, and 13 of 23 panels get squashed more than 5%.
- Do not put a reference on a white rectangle. Cut it into tiles. White pixels
  give no colour, and a reference is there only to give colour.
- A zone holds an id, and the app never uses a palette id again. To renumber
  the palette would repaint a page in silence.
- Step 5 must not snap. Snapping is step 6, and the artist does it. See the
  reason in step 5.
- A correction to the panels, the balloons or the zones happens at its own
  stage and nowhere else. The stage closes when the next stage uses the
  result.
- A merge and a cut are permanent. Do not add an undo that keeps the map of
  the segmenter beside the map of the artist.
- Do not show a palette image to the colour model. It is a strip of swatches,
  not an example of a coloured page.
- Keep the bubble detector on `onnxruntime`. Nearly every other comic balloon
  detector on GitHub needs the `ultralytics` package, and that package is
  AGPL-3.0. The licence of the weights does not change this.
- No word that the artist reads goes in `index.html` or `app.js`. It goes in
  `static/locales/en.json`, under a key that the code writes out in full. A
  key that the code builds at run time is a key that `tests/test_locales.py`
  cannot see.
- No colour goes outside the `:root` block of `app.css`. A line on the artwork
  carries luminance, not hue (`UI.md` §11): the artist judges colour there.

## 8. Known problems

- **A balloon with a long tail loses its tail.** A star-shaped polygon cannot
  follow a concave shape, so the trace goes across the tail and not around it.
- **A balloon with no outline comes back as its text block only.** The trace
  has no boundary to find, so the white margin of that caption stays
  unprotected and the app colours it.
- **The shape can be a little too large.** Where a ray finds no ink, it stops
  at the box border. This shows as slack around the oval balloons in
  `manga_page.jpg`.
- **Panel detection joins two panels into one.** On `tintin_page.jpg` the two
  panels at the left of rows 1 and 2 come back as one panel. The artist now
  corrects this: delete the joined panel and draw the two real ones. It is
  still the failure that costs the most work.
- **Panel detection also finds panels that are not there.** The title of
  `tintin_page.jpg` and a balloon at the edge of `manga_page.jpg` come back as
  panels. This is not important: the artist deletes them with one click. Every
  filter that removes them also removes a thin panel that is real.
- **The zones are not correctable after step 5.** The artist must merge and
  cut before the colours arrive. To press Segment zones again opens the stage
  and deletes every merge and every cut. The app says so before it does it.
- **A split of a finished page can be wrong.** Panel detection reads the ink.
  A page with no ink layer, such as a flats-only export, gives boxes that are
  too small. The artist sees the thumbnails and deletes the bad ones.
- Segmentation is slow. A large page takes approximately two minutes. The cost
  is in LineFiller.
- The progress bar moves in large steps during segmentation, about one fifth of
  a panel for each step. LineFiller reports nothing inside one pass.

## 9. Tests

`pytest` runs all tests. `tests/test_web.py` presses each button in sequence
through the HTTP API. It also does the work of the artist: it drags a corner
of a panel, traces a balloon, sweeps up a dozen zones and merges them, cuts
one zone in two, takes a colour into the palette, and snaps a segment. It then
opens the PSD that comes out. Keep that test working: it is the proof that
each screen goes to the next one.

One test counts the coloured pixels before a cut and after it. A cut that
loses the pixels of its own stroke shows only as a halo in the PSD of somebody
else.

`tests/test_locales.py` checks the words. Each key that the interface uses is
in `en.json`, each key in `en.json` is used, and each other language has the
same placeholders. `tests/test_progress.py` checks that the bar only goes
forward and ends at 100 %.
