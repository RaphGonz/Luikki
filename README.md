# Luikki

Upload a page, press the buttons in order, click the zones the machine got
wrong, get a layered PSD.

    pip install -e ".[web,dev]"
    luikki serve

Then open <http://127.0.0.1:8000>.

| Button | What runs | Where |
|---|---|---|
| 1 Upload page | `load_line_art` | `segmentation/preprocess.py` |
| 2 Detect panels | gutter network → traced polygons, box fallback; corners then dragged | `segmentation/panels.py` |
| 3 Detect bubbles | RT-DETR box → radial trace → polygon; corners then dragged | `segmentation/bubbles.py` |
| 4 Segment zones | MangaLineExtraction → LineFiller trapped-ball, per panel; then merged and cut by hand | `extract/`, `segmentation/segmenter.py` |
| Add reference | image for the model; a finished page splits into its panels | `colour/references.py` |
| Add palette | image of swatches; every colour taken | `colour/extract.py` |
| 5 Generate flats | proposer → per-segment mode, **no snap** | `colour/` |
| 6 Snap | per segment, artist-driven; `snap all` for the bulk | `colour/segments.py` |
| 7 Export PSD | group per panel, layer per colour | `export/psd.py` |

## The palette is not the references

A reference is an image the model is shown. The palette is the artist's list
of colours. They were one thing until now — the palette was re-derived from
the references on every change — and that made two ordinary things
impossible: keeping a colour whose reference had been deleted, and editing a
colour at all, since the next rebuild put it back.

There are two upload buttons, because there are two different things to
upload:

**Add reference** — a character sheet, a finished page, a finished panel.
This is what Cobra is shown. Its colours are *extracted and offered*: chips
under the thumbnail, dimmed until taken. Clicking one puts it in the palette,
clicking a lit one takes it out. A drawing's colours are a proposal, because
the extraction cannot tell the character's jacket from the wall behind it.

A **finished page is stored whole *and* as its panels**. Cobra retrieves
patches — it tiles the reference, ranks the tiles against the panel being
coloured, and reads colour out of whichever ones match — and most patches of a
whole page are backgrounds and props, so the tile covering a face can retrieve
something that is not a face. That is measured, not assumed: a tight crop of
one coloured face reproduced a character's skin where a whole finished page of
the same character in the same colour world produced a cold blue one. Panel
detection runs on the upload and each panel is stored as its own `panel`
reference, cropped to its box and *not* masked to its polygon — white padding
would put white in the patches the retrieval ranks, and a reference exists to
supply colour.

Only panels big enough to reach the model's frame without being blown up are
cut out (`_MAX_UPSCALE`), because an enlarged panel outranks the sharp tile
that actually holds the character. The page is kept whichever way that goes:
the colours of a panel too small to cut are still *in* the page, and scored
against the artist's own labels, page-plus-panels ranks exactly as well as the
best arm measured. A page whose panels cannot be found is simply stored on its
own — half a split is worse than none.

**Add palette** — an image of your swatches. Same extraction, no chips: every
colour in it goes straight into the palette. A palette *is* the decision about
which colours this book uses, already made, in the file; confirming each
swatch of a strip built on purpose is the same work twice. It is not shown to
the proposer — a grid of flat rectangles is not an example of how a page is
coloured (`references.PALETTE_KIND`).

Deleting follows from that difference. Deleting a palette image takes its
colours out with it. Deleting a reference leaves the palette alone: those
colours were picked out of a drawing one at a time, and a click that said
nothing about colour must not repaint every zone snapped to them. Either way,
a colour leaving the palette un-snaps the zones that pointed at it — a zone
cannot hold an id that is gone.

**Clicking a palette swatch changes that colour everywhere it is used.** No
re-segmentation, no re-proposal, no re-snapping: a zone stores a
`palette_entry_id` and never an RGB, so the flats raster and the PSD both
resolve through the palette at the moment they are asked for, and one row
changing is the whole repaint. This is what rule 1 was for, and until the
palette became editable there was nothing in the app that showed it.

Ids are handed out once and never renumbered, and the palette is written to
`palette.json` beside the reference pool — it belongs to the book, so it
outlives the page and the process. An id that means a different colour
tomorrow is worse than no id at all.

## Detection proposes the geometry, the artist settles it

Panels and balloons come out of a detector, which means some of them are
wrong. At step 2 every panel corner is a handle; at step 3 every balloon
corner is. Three gestures, and no modes to be in:

- **drag a corner** to move it,
- **click an edge** to put a new corner there — it comes up already in your
  hand, so adding one and placing it are one gesture,
- **click empty page** to start drawing a new panel or balloon, corner by
  corner, and click the first corner again to close it.

Right-click is the destructive half and always names what it is about to
destroy: *delete this corner*, *delete this panel*, or *stop drawing this
bubble* for the mis-click that started a shape you never wanted. Escape does
the last one too.

Each gesture sends the **whole polygon** — `PUT /api/panel/{order}`. The
alternative, "corner 3 of panel 2 moved to here", is a second description of
the shape, and the two go out of step the first time a corner is inserted
mid-drag. A panel added by hand is renumbered into reading order like any
other, because the number in its corner is the order the PSD groups run in.

**The stage is the boundary.** Corrections happen at step 2 and step 3 and
nowhere else: once `Segment zones` has run, the geometry is no longer a
proposal — it is what the zones were cut from, and moving it silently would
leave them describing a page that no longer exists. The server refuses, and
says which button reopens it. For the same reason step 3 will not run before
step 2: a balloon traced onto a page whose panels are about to be re-detected
is work the artist cannot get back.

Re-pressing a step still replaces what it produced (rule 4) — including the
corrections. That is now worth a sentence before it happens, so every step
that would destroy work asks first.

## Zones the artist merges and cuts

Trapped-ball cuts from the ink it can see, and the ink is not always closed.
So it leaks a garment into the background through a gap, and it returns what
the eye reads as one thing — a pair of trousers, a glass, a pair of shoes — as
forty scraps that would each need colouring by hand.

Both corrections live at step 4, between the cut and the colour. One rule runs
the selection: **a zone is selected while the button is pressed over it.** A
press picks one up; holding and moving picks up everything the pointer passes
over; two zones on opposite sides of the page take two presses and drag
nothing in between, because the button was up. Pressing a selected zone drops
it. The press itself toggles, but a sweep only ever adds — otherwise wobbling
back over a zone mid-sweep would drop it again.

Right-click is the whole menu, and it reads what is selected: **Merge these N
zones** with two or more, **Cut this zone** with exactly one (with several
there is no saying which one a stroke belongs to), **Clear selection** with
any.

Merged zones need not touch — the panes of a glass, a shirt split by an arm.
A zone is a set of pixels, not a blob. What they must share is a panel: labels
are panel-local, and the same shirt in the next panel is the *palette's* job,
which is the difference between merging (one unit of work for ever after) and
snapping two zones to one colour (same colour, still two clicks). The largest
zone keeps its label, so the anchor stays in the body of the trousers rather
than in a 300px scrap.

Cutting is one gesture: press, drag across the leak, release. The stroke is
the line the ink was missing, and the zone parts along it — both ends run on
past where the hand stopped, because stopping a few pixels short is the
commonest way a cut fails and the overshoot can do no harm inside one zone's
own mask. The stroke's own pixels go to whichever piece they are nearest, so a
cut leaves no unassigned seam for the flats to fringe around. A stroke that
separates nothing says so and changes nothing.

**These corrections are permanent.** There is no unmerge and no history:
keeping one would mean carrying the segmenter's map beside the artist's, and
every later stage would have to say which of the two it meant. The stage
boundary is the protection instead — this is step 4's work, it happens before
a single colour is proposed, and it closes when the flats are generated.
Pressing Segment zones again starts the page over, and says so first.

## Flats propose, the artist snaps

Step 5 resolves one modal colour per segment and stops. It does not snap, even
with a palette loaded. Every segment comes out holding its own colour and its
own palette entry.

Snapping is step 6, and it happens one segment at a time because the artist
decides it. `session.segment_at(x, y)` resolves a click off the label map,
`snap_segment` points that segment at a palette entry, and `unsnap_segment`
puts back what the proposer said. Because a segment stores a
`palette_entry_id` and never an RGB, each of those is a single-row change.

These were one pass until the split, which made snapping the only step with no
boundary the artist could see or refuse — and it was the step that quietly
folded every neutral zone into a character sheet's ink black. `snap_suggestion`
now returns the nearest reference colour *and its distance*, so the number the
old pass decided on silently is the number the artist is shown.

**Segments are never merged or grouped by colour.** Two segments that agree are
still two segments. Measured on `diagonal_page.jpg`, 752 zones collapse to 39
colour groups — which looks like an efficiency win and is not: those are 752
correctly-found segments that a reference-starved proposal could not tell
apart. Merging on that signal would bake a model failure into the data and
destroy exactly the zones the artist needs in order to bucket the page. The
answer to "too many zones" is more references, not fewer zones.

`snap all` is the bulk shortcut, for a page whose references are good enough
that the artist would have agreed anyway. It goes through the same per-segment
call, so it can do nothing clicking could not, and every segment it touches
stays individually reversible.

## Running a page without the browser

    luikki flatten test_pages/diagonal_page.jpg -r sheet.jpg --proposer cobra

Every step headlessly, then `snap all`, then the PSD. `--no-snap` stops after
flats; `--threshold` moves the guard, and `--threshold inf` snaps everything
regardless of distance.

`--steps` writes one image per stage boundary — page, panel polygons, bubble
polygons, zone map, flats before and after snapping, what snapping left for the
artist, and the exported PSD composited back down. The pipeline's claim is that
every boundary is inspectable, which is hard to check while the only artefact
is the PSD at the end. On `diagonal_page.jpg` with one character sheet:
752 segments, 501 snapped, 251 left as proposed — including the page
background, whose suggestion sits at dE 15.6 and is correctly left alone
rather than tinting the paper.

Nothing runs on its own, and re-running a step clears what depended on it —
including the artist's snapping, which is why the browser drops its selection
whenever a step is re-pressed.

## The extraction stage

Segment zones does not run trapped-ball on the artist's ink. It runs
MangaLineExtraction first and segments the *structural* lines, which is the
condition §2.2's A/B chose. Fed raw ink, trapped-ball treats a thick brush
stroke as a corridor bounded by its own two edges and a spot black as a zone in
its own right, so hair, brows and shadow masses come back merged into whatever
they sit on. Measured on `teddy_page.png`: ink fraction 0.173 → 0.058, matching
the figure §2.2 recorded.

Panel and bubble detection deliberately stay on the raw mask —
`segment_panels` needs spot blacks solid or the gutter network leaks through
them, and `detect_bubbles` traces the balloon outline the artist actually
drew. `expand_under_lines` also stays on raw ink, because the layer the artist drops on top is real ink and
that is what the flats have to reach under.

Tick **extracted lines** in the Show panel to see what segmentation actually
received. `--extractor raw` turns it off; use it only when the ink layer is
already a clean line image.

## Detecting bubbles

`detect_bubbles` is a model, not a heuristic. The heuristic version it replaced
returned 39 bubbles on `tintin_page.jpg` and not one of them was a balloon; it
read hatching as `iiii` and cup holders as `OOO` on the three pages that have
no balloons at all. Deciding "is this text?" from the geometry of ink blobs
does not survive real artwork.

    luikki serve      # pulls the weights on first use, 161 MB into models/

RT-DETR-v2 (`ogkalu/comic-text-and-bubble-detector`, **Apache-2.0**), run
through `onnxruntime`. No GPU, ~0.85 s per page whatever its size. The licence
matters more than it looks: nearly every other comic balloon detector on GitHub
needs `ultralytics` to run, and that is AGPL-3.0 — which P1 established must
never enter this chain, whatever the model card claims.

Measured against the artist's own counts in `test_pages/bubble_counts.txt`,
score ≥ 0.7: tintin 12/12, laurine 4/4 (spiky, tailed and open balloons, with
its Blop/Pop/Hiii sound effects correctly ignored), manga 4/4, and zero on all
three pages with no balloons.

The model gives boxes. The shape comes from the artwork: 128 rays cast outward
from the box centre, each keeping the furthest ink it finds, then a circular
median so a ray that escapes through a gap in the outline is out-voted by its
neighbours. That is what handles a balloon outline Otsu leaves *dotted*, which
`manga_page.jpg`'s is.

## Plugging Cobra in

The default proposer (`distinct`) needs no GPU and no weights: it gives every
zone its own colour, which is classical flatting output. Cobra makes those
colours *mean* something, and needs an NVIDIA GPU with real VRAM.

    git clone https://github.com/zhuang2002/Cobra.git third_party/Cobra
    pip install -e third_party/Cobra/diffusers      # the patched fork, required
    pip install transformers peft accelerate einops sentencepiece matplotlib
    luikki serve --proposer cobra              # pulls the weights on first use

**Do not `pip install -r third_party/Cobra/requirements.txt`.** It pins
`torch==2.5.1`, `numpy==1.26.4` and `opencv-python==4.11`, which downgrades
numpy below this project's `numpy>=2.0` floor and replaces a CUDA torch build.
The line above installs what `cobra.py` actually imports, unpinned. `matplotlib`
is not optional — `cobra_utils/utils.py` imports it at module scope.

`colour/cobra.py` was written against Cobra `48d6168` on a machine with no GPU
and first executed on 2026-08-20. Three defects only a real run could surface
were fixed then: an import ordering bug, Cobra's hardcoded relative path to its
prompt tensors, and an all-black `hint_color` that made every generation dark
regardless of the references. Verified end to end on `teddy_page.png`,
`diagonal_page.jpg` and `laurine_page.jpg`.

Everything downstream consumes a proposal raster and cannot tell which
proposer produced it, so swapping them changes one constructor call. The
raster itself is never shown and never exported: it exists only to be reduced
to one modal colour per zone.

## Layer counts, and what a page costs

With no palette uploaded, every zone becomes its own palette entry and its own
layer — the "per zone" export granularity from P4. Upload a swatch or character
sheet and the export collapses to one layer per palette colour, which is the
default P4 asks for.

Measured on the real test pages, single machine, no GPU involved:

| Page | Panels | Zones | Extract | Segment | Export |
|---|---|---|---|---|---|
| `antoine_page.png` 1080×1080, raw | 1 | 581 | — | 60 s | 5 s (581 layers) |
| `antoine_page.png` + 11-colour swatch | 1 | 581 | — | 59 s | 14 s (62 layers) |
| `teddy_page.png` 2048×2732, raw | 3 | 427 | — | 102 s | 5 s |
| `teddy_page.png`, extracted (default) | 3 | 567 | 7 s (GPU) | 132 s | 5 s |

Extraction costs seconds on a GPU and minutes on a CPU; it runs once per page
and is cached. Segmentation is the slow step and that is LineFiller's cost.

The zone count goes *up* with extraction, which is not a regression — §1.4 is
explicit that region count is an alarm, not a quality score, and the A/B was
decided on renders. Extraction resolves detail that raw ink had merged into
neighbouring masses, and each newly separated eyebrow is a zone.

Export was eight minutes before `_set_preview` in `export/psd.py` — read the
comment there before anyone "simplifies" it back to a plain `psd.save()`.

## Known rough edges

**A balloon with a long tail loses its tail**, and a balloon with no outline
drawn at all comes back as its lettering rather than its white. Both follow
from the trace being star-shaped, which is also what stops it folding inward
around the text. See `segmentation/bubbles.py`.

**Panel detection merges and over-proposes, and the two are not equal.** On
`tintin_page.jpg` the left column of rows 1–2 comes back as one panel, and the
page title comes back as a panel of its own; `manga_page.jpg` proposes a
balloon poking into the margin. Per D-19 a false positive is one click to
delete. A *merge* is not correctable at all — there is no split tool — so that
is the one worth fixing.

**Cobra's proposal quality tracks line-art cleanliness, hard.** On
`teddy_page.png` — uniform line weight, closed regions, no hatching — 74-92% of
a panel comes back saturated. On `laurine_page.jpg` — loose brush, heavy spot
black, dense crowds — the same settings give 7-40%, and one panel comes back
near-monochrome. When a page colours badly, check the drawing before tuning
steps, `top_k` or resolution. Panel aspect ratio is *not* the lever it looks
like: `teddy_page` panel 0 is aspect 3.38, far outside Cobra's bucket list, and
colours cleanly.

**A tight reference beats a whole page, for characters.** A crop of one coloured
face reproduced that character's skin correctly where a whole finished page of
the same character in the same colour world produced a cold blue face. Most
patches on a full page are backgrounds and props, so the query patch covering a
face can retrieve something that is not a face. Uploading a finished page now
stores it whole and cuts out the panels large enough to be worth cutting;
cropping further, to character scale, is still the artist's call.

**Dropping duplicate tiles is not what makes a page bland.** Tested because it
looked like the obvious suspect: `_subject_tiles` skips a window overlapping a
kept one by more than `_SUBJECT_MAX_OVERLAP`, and a starved retrieval pool
would explain washed-out colour. It does not. On `diagonal_page.jpg` with
`laurine_ref.jpg`, filter on against filter off moved the page by 0.03 mean
CIELAB chroma — 5.78 to 5.81, where a saturated comic colour is 40 to 80 — and
the only pixels that changed at all were in the one panel whose aspect makes
the filter alter which tiles are chosen. The rest of the page came back
byte-identical, because `_TILE_BUDGET` takes the first six windows and the
dropped ones fall outside that six. The filter changes *which* tiles, never how
many.

The same run says where to look instead. That page's top panel measured 14.79
chroma and its five diamond panels 2.46: the panels that come back grey are the
non-rectangular ones, which reach the model masked to their polygon and then
letterboxed, so most of what the DiT sees is white. Two knobs are left behind
for the next attempt, both defaulting to today's behaviour and read at call
time: `LUIKKI_TILE_OVERLAP=1.1` keeps every window, `LUIKKI_TILE_BUDGET`
raises the ceiling.

**References accumulate, and that is the plan.** The first page of a book is
expensive: one character sheet, and a lot of correcting. Every panel coloured
after that is a finished panel of *this* book in *this* colour world, and it
goes back into the pool as a reference — which is why uploading a finished page
splits it into panels rather than storing it whole. The pipeline gets better
across a book by being used, not by being tuned.

**Colour hints propagate, but not reliably.** A hint filled a whole ink-bounded
region in one test and only tinted it in another. When measuring one, sample
*outside* the hinted rectangle — inside it the colour is whatever was painted
there, so the measurement always succeeds and means nothing.

**Every stage is correctable in-app now.** Panel and balloon corners are
draggable at steps 2 and 3; zones are merged and cut at step 4; a palette
colour is editable wherever it is used; and clicking a zone at step 6 opens
what the machine decided about it — the colour it holds, the nearest palette
colour, and the distance between them — so snapping it, or putting the
proposal back, is one click. Photoshop is where the page is finished, not
where the machine's mistakes are repaired.

## Tests

    pytest

`tests/test_web.py` presses every button in order through the HTTP API, drags
a panel corner and traces a balloon the way the canvas does, sweeps up a dozen
zones and merges them, cuts one in two and counts the pixels back, clicks a
zone and snaps it the way the inspector does, and opens the PSD that comes out — rule 3's "every screen reaches the next one",
as a test rather than a promise.
