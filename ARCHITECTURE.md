# Luikki — how the app works

This document is the fast way into the code. `SPEC.md` tells you what the app
must be. `flatting-pipeline-spec.md` tells you why the algorithms are what they
are. This document tells you where things are and how the data moves.

The text follows ASD-STE100 Simplified Technical English: short sentences,
active voice, one idea for each sentence, and the same word for the same thing.

## 1. What the app does
An artist gives the app one page of line art. The app divides the page into
panels, balloons and zones, then sorts the zones into depth planes. The app
writes a layered PSD file: one layer for each plane, and fake flat colours in
it. The artist opens that file in Photoshop or in Clip Studio, selects a zone
with the magic wand and colours the page there. The app proposes no colour
(ROADMAP G).

The app does not correct anything by itself. The artist corrects it. Each
stage gives a proposal, and the artist can refuse it:

| Stage | What the artist corrects |
| --- | --- |
| 2 Detect panels | Drag a corner. Add a corner. Draw a panel. Delete a panel. |
| 3 Detect bubbles | The same four actions, on the balloons. |
| 4 Cut into zones | Merge many zones into one. Cut one zone in two. |
| 5 Planes | Put zones on another plane. Call zones characters. |

Each correction is possible at one stage only. The stage closes when the next
stage uses its result. Zones are the exception: merge and cut stay open at
step 5. Section 4 gives the rule for each one.

## 2. How to run the app

    pip install -e ".[web,dev]"
    luikki serve

The command starts a local web server. Open the address that the command
prints. Options: `--port`, `--workdir`.

    pip install -e ".[desktop]"
    luikki app

The same app in its own window, as the installed app runs it (`desktop.py`).
The server takes a free port of 127.0.0.1, and closing the window stops it.
`--debug` opens the web inspector.

    python -m venv .venv-build
    .venv-build\Scripts\pip install -e ".[desktop]" pyinstaller
    .venv-build\Scripts\pyinstaller packaging\luikki.spec --noconfirm
    .venv-build\Scripts\python packaging\smoke.py <page>

The installed app, in `dist\Luikki`. Build it from a venv without torch, after
`luikki models` and with `third_party/LineFiller` present. `Luikki.exe` alone
opens the window; `Luikki.exe <command>` runs any `luikki` command, which is
what `smoke.py` uses to take one page through the build. The app has no
console: its output goes to `luikki.log` in the user's log folder.

    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" packaging\luikki.iss

The Windows installer, in `dist\installer`, from `dist\Luikki`. It installs
for the current user in `%LOCALAPPDATA%\Programs\Luikki`, without
administrator rights; the project in `%LOCALAPPDATA%\Luikki` is not touched by
installing or uninstalling. The icon is drawn from `favicon.svg` by
`packaging/icon.py` during the PyInstaller build.

Run the tests with `pytest`.

## 3. The words this project uses

Use these words only with these meanings. Do not rename them in the code.

| Word | Meaning |
|---|---|
| page | One image of line art from the artist. |
| grey | The 8-bit greyscale of the page. Anti-aliased edges stay visible. |
| line mask | A boolean array. `True` is the ink of the artist. |
| structural mask | The line mask that zones are cut from. By default it is the ink itself; with line extraction on, a neural model makes it from `grey`. |
| panel | One area of the page. It holds a polygon and a box. Not always a rectangle. |
| protected area | A polygon that the app must never put in a zone. A bubble is one. |
| box | Four numbers from the bubble model: `x0, y0, x1, y1`. Not a shape. |
| zone | One flat area in a panel. The code calls it a region. |
| label map | An `int` array for one panel. Each value is one zone number. |
| palette entry | One colour with an id and a label. There are eight: the fake flats. |
| depth groups | An `int8` array for one panel: 0 near, 1 middle, 2 far, from the depth model. |
| plane | Where a zone is: 0 1st plane, 1 2nd plane, 2 background, 3 characters. |

**Rule that you must not break:** a zone holds a `palette_entry_id`. A zone
never holds an RGB value.

## 4. The six buttons

Nothing runs by itself. The artist starts each step. If the artist runs a step
again, the app deletes the results of all later steps. A step that deletes
work asks the artist first. The question is in the rail, and it names what the
step deletes.

| # | Button | Function | File |
|---|---|---|---|
| 1 | Upload page | `load_line_art` | `segmentation/preprocess.py` |
| 2 | Detect panels | `segment_panels` | `segmentation/panels.py` |
| 3 | Detect bubbles | `detect_bubbles` (a model) | `segmentation/bubbles.py` |
| 4 | Cut into zones | `LineFillerSegmenter.segment` | `segmentation/segmenter.py` |
| 5 | Find the planes (or Skip) | `panel_planes` (a model), then a vote | `segmentation/planes.py` |
| 6 | Export PSD | `write_psd` | `export/psd.py` |

Step 3 needs step 2. The app refuses step 3 before step 2. The rail shows that
refusal before the click: a locked step says what to do first. The steps run in
one order, because the artist corrects the result of each one, and a step that
runs again deletes those corrections. Step 5 is optional: the export takes the
zones without planes, as one layer of flats.

### Step 1 — Upload page

`load_line_art` reads the file and makes two arrays: `line_mask` and `grey`.
It reads the bytes with `np.fromfile` and decodes them: `cv2.imread` cannot
open a path with an accent in it on Windows.
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

### Step 4 — Cut into zones
By default the zones are cut from the whole of the artist's ink
(`PassthroughExtractor`). Line extraction is an option of each page, under
« Advanced »: then `structural_mask()` runs the MangaLineExtraction model on
`grey`, and a thick brush stroke becomes one thin line, a spot black its
outline. It is off by default because the model erases small dense detail —
windows, pipes — that it takes for hatching (ROADMAP G5,
`reports/traits_fins/`). Either way, `thick_ink` adds back the thick strokes.

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
  The zones must be in one panel: a label belongs to a panel.
- `cut_zone` draws the stroke of the artist as a wall inside the zone, then
  runs connected components. The stroke is the ink line that is not there. The
  app makes both ends of the stroke longer, because to stop a few pixels short
  is the usual reason a cut fails. The pixels of the stroke go to the piece
  that is nearest, so the cut leaves no unassigned pixels for the export to
  fringe around. A stroke that separates nothing changes nothing, and the app
  says so.

**There is no unmerge.** To keep one would mean to hold the map of the
segmenter beside the map of the artist, and each later stage would have to
say which of the two it uses. `_undo` keeps the last few edits instead — a
label map and its planes, or only the planes for a plane change — and dies
when the zones are cut or the planes found again.

After every change to the zones, `_assign_colours` gives each zone one of the
eight fake flats (`export/flat_colours.py`): a greedy colouring of the page's
adjacency, in 8-connectivity, so two zones that touch never share a colour,
across panel borders too. Of the free colours a zone takes the one the page
has used least, so the eight are spread. Step 4 shows the zones in these
colours: what the canvas shows is what lands in the PSD.

### Step 5 — Planes (optional)
`detect_planes` reads each panel on its own:

1. `DepthEstimator.depth` runs Depth Anything V2 **Small** (Apache-2.0; Base
   and Large are CC-BY-NC) on the panel's crop of `grey`, 518 px on the long
   side, and scales the answer back to the crop. Larger is nearer.
2. `depth_groups` cuts the panel's own values into three groups with a 1-D
   k-means started from the quantiles: the same page gives the same groups on
   every run. A panel with no relief still gets three.
3. `vote` gives each zone the group most of its pixels are in — never the
   mean: a floor that runs from the back to the front would fall in the middle.
   A zone is never split. Balloons and spot blacks have no zone, so they do not
   vote.

The depth map draws no boundary: its edges are soft and do not follow the
ink. The zones stay the only geometry, and a plane is a label on a zone. The
groups are kept (`PanelState.depth_groups`, `depthN.npy`): a zone cut or
merged later votes again on the depth under it (`_revote`).

**Characters** are the fourth plane, and only the artist sets it: no model
says who is a character (anime-seg found none on the Tintin page). A
character zone stays one through a cut or a merge. The artist picks zones the
way step 4 does, then the inspector or the right click puts them on a plane
(`set_planes`). Ctrl+Z takes a plane change back.

The canvas shows the planes first and the zones inside them (tester 3 was
frightened by every zone at once): one tint for each plane, the `--plane-*`
tokens of `app.css`, sent to `/api/planes.png`, with each zone's edge a shade
darker.

The step can be stopped, like step 4: every panel is read before any is
written.

### Step 6 — Export PSD
`write_psd` writes, bottom to top: Background, Middle ground, Foreground,
Characters, then Balloons (the balloon shapes, white). A page whose planes
were skipped has one layer, Flats, under the balloons. About five layers a
page: one layer for each colour made 956. `granularity` says how they stack:

- `plane` (the default): one layer for each plane, every zone in its fake
  flat.
- `colour` (« By plane and by colour »): one group for each plane, one layer
  for each colour inside it, named « Colour n ». Every object is apart, and
  there are 8 × 4 + 1 = 33 layers at most.

The app sends the layer names in the artist's language. `support_grey` adds
the two ink layers a printer wants on top; it is the only thing that puts line
art in an export. `layer_count` says how many layers a stack would write
without writing them.

Read the comment on `_set_preview` in `export/psd.py` before you change that
file. Without that function the export takes minutes.

## 5. Where the state is

`src/luikki/web/session.py` holds all the state of the app in one
`Session` object. One page is in the app at a time. A new page replaces the
old one. The gap allowance and the export stack stay, because they belong to
the book and not to the page.

A lock makes the buttons sequential. The artist will click two times.

`Session.progress` (`web/progress.py`) tells the browser how far a long step
is. `GET /api/progress` reads it without the lock, because the step holds the
lock for its whole run. A tick is a finished piece of work: one tile of the
extractor, one pass of LineFiller, one panel. `Session._learn` measures what
each pass costs on this machine, so the steps of the bar match that machine.
The route sends codes, not words.

Steps 4 and 5 can be stopped. `POST /api/cancel` (also without the lock) sets
a flag in `Progress`; the next tick raises `Cancelled`, between two passes and
never by killing a thread. Both compute every panel before they write any, so
a stopped run leaves the page as it was.

LineFiller's fill and merge passes run from `segmentation/linefiller_fast.py`:
upstream's answer, pixel for pixel (`tests/test_linefiller_fast.py`), without
the whole-page scan upstream makes per zone. The Windows build ships
`onnxruntime-directml`, so the line extractor runs on the GPU.

`src/luikki/model/store.py` is a full SQLite store with the same shape.
This version of the app **does not use it**. Persistence is not the purpose of
this version.

`src/luikki/web/app.py` is the FastAPI layer. Each button is one POST
route. Each preview image is one GET route that sends a PNG. A correction is
also one route: the browser sends the complete shape, the complete stroke, or
the zones and their plane. It never sends an edit.

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
      account.py              sign-in by email code; the licence (`my_status`)
      billing.py              Buy and Invoices: a Stripe page in the browser
      models.py               the model files, sha256-pinned; `luikki models`
      web/session.py          all state, the six buttons      <- start here
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
        planes.py             depth model -> three groups -> a vote per zone
      extract/
        manga_line.py         the MangaLineExtraction model (optional, per page)
        passthrough.py        the default: the ink as drawn, no model
      export/
        flat_colours.py       eight fake flats, no two touching zones alike
        psd.py                zones -> a PSD, one layer per plane
      cloud/
        billing.py            the licence: Stripe Checkout, portal, webhook
        stripe_setup.py       the Stripe objects, made once per mode
        schema.sql            the Supabase tables and functions
        modal_app.py          the billing endpoint on a CPU Modal function
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
- Use Depth Anything V2 **Small** only. Base and Large are CC-BY-NC-4.0.
- The depth map never draws a boundary. A plane is a label on a zone, by vote.
- Only the artist calls a zone a character.
- A panel is its polygon. The box is only where to cut. Never use the box as
  the shape: a diamond panel's box covers a part of four other panels.
- Do not trace an area that has more than 12 corners. It is artwork, not a
  panel, and its shape is the shape of a character.
- A zone holds an id: one of the eight fake flats, given again after every
  change to the zones.
- A correction to the panels or the balloons happens at its own stage and
  nowhere else. The stage closes when the next stage uses the result. Zones
  are the exception: merge and cut stay open at step 5.
- There is no unmerge. Do not add an undo that keeps the map of the segmenter
  beside the map of the artist.
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
- **A panel with no relief still gets three planes.** A close-up comes back
  cut in three. The artist moves the zones.
- Segmentation is slow. A large page takes approximately two minutes. The cost
  is in LineFiller.
- The progress bar moves in large steps during segmentation, about one fifth of
  a panel for each step. LineFiller reports nothing inside one pass.

## 9. Tests

`pytest` runs all tests. `tests/test_web.py` presses each button in sequence
through the HTTP API. It also does the work of the artist: it drags a corner
of a panel, traces a balloon, sweeps up a dozen zones and merges them, cuts
one zone in two, puts zones on a plane and calls some characters. It then
opens the PSD that comes out. No test loads the depth model: `tests/conftest.py`
stands in a depth that grows down each panel. Keep that test working: it is the proof that
each screen goes to the next one.

One test counts the coloured pixels before a cut and after it. A cut that
loses the pixels of its own stroke shows only as a halo in the PSD of somebody
else.

`tests/test_locales.py` checks the words. Each key that the interface uses is
in `en.json`, each key in `en.json` is used, and each other language has the
same placeholders. `tests/test_progress.py` checks that the bar only goes
forward and ends at 100 %.
