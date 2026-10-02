# Luikki

Upload a page, press the buttons in order, correct what the machine got
wrong, get a layered PSD: one layer per depth plane, fake flat colours inside,
ready for the colourist's own palette. Luikki proposes no colour (ROADMAP G:
Cobra and the whole colour pipeline were dropped on 2026-10-01; the history is
in git).

    pip install -e ".[web,dev]"
    luikki models
    luikki serve

Then open <http://127.0.0.1:8000>.

| Button | What runs | Where |
|---|---|---|
| 1 Upload page | `load_line_art` | `segmentation/preprocess.py` |
| 2 Detect panels | gutter network → traced polygons, box fallback; corners then dragged | `segmentation/panels.py` |
| 3 Detect bubbles | RT-DETR box → radial trace → polygon; corners then dragged | `segmentation/bubbles.py` |
| 4 Cut into zones | LineFiller trapped-ball on the ink, per panel; then merged and cut by hand | `segmentation/segmenter.py` |
| 5 Planes (optional) | Depth Anything V2 Small per panel → 3 groups → one vote per zone; then moved by hand | `segmentation/planes.py` |
| 6 Export PSD | one layer per plane, eight fake flats, no two touching zones alike | `export/psd.py` |

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
are panel-local. The largest
zone keeps its label, so the anchor stays in the body of the trousers rather
than in a 300px scrap.

Cutting is one gesture: press, drag across the leak, release. The stroke is
the line the ink was missing, and the zone parts along it — both ends run on
past where the hand stopped, because stopping a few pixels short is the
commonest way a cut fails and the overshoot can do no harm inside one zone's
own mask. The stroke's own pixels go to whichever piece they are nearest, so a
cut leaves no unassigned seam in the export. A stroke that
separates nothing says so and changes nothing.

**There is no unmerge**, only Ctrl+Z on the last few edits: keeping a history
would mean carrying the segmenter's map beside the artist's, and every later
stage would have to say which of the two it meant. Merge and cut stay open at
step 5, over the planes. Pressing Cut into zones again starts the page over,
and says so first.

## Planes, by depth

Two testers out of two asked, unprompted, for planes: foreground, middle
ground, background, and characters apart from the scenery. Step 5 reads each
panel's depth with Depth Anything V2 **Small** (Apache-2.0 — Base and Large are
CC-BY-NC, never use them), cuts the panel's own values into three groups with
a deterministic 1-D k-means, and gives each zone the group most of its pixels
are in. The depth map's edges are soft and do not follow the ink, so it never
draws a boundary: the zones stay the geometry, a plane is a label on a zone.
A zone cut or merged later votes again on the depth kept for its panel.

« Characters » is a label only the artist puts on: anime-seg missed every
character of the Tintin page and took a machine for one (`reports/depth/`).

The step is optional. Skipped, the export is one layer of flats.

## The export

About five layers a page, where one layer per colour made 956: Background,
Middle ground, Foreground, Characters, Balloons on top. Inside a layer every
zone holds one of eight fake colours — palette entries, so `palette_entry_id`
is untouched — given by a greedy colouring of the zones' 8-connected adjacency:
two zones that touch are never alike, so the magic wand (contiguous) takes one
zone, as on flats made by hand. « By plane and by colour » turns each plane
into a group with a layer per colour, for objects apart: 8 × 4 + 1 = 33
layers at most.

Export was eight minutes before `_set_preview` in `export/psd.py` — read the
comment there before anyone "simplifies" it back to a plain `psd.save()`.

## Running a page without the browser
    luikki flatten test_pages/diagonal_page.jpg --steps

Every step headlessly, then the PSD. `--no-planes` skips step 5,
`--extract-lines` cuts the zones from extracted lines, `--layers colour` picks
the other stack. `--steps` writes one image per stage boundary — page, panel
polygons, bubble polygons, zone map, planes, and the exported PSD composited
back down.

## The extraction stage
By default the zones are cut from the whole of the artist's ink. Line
extraction (MangaLineExtraction) is an option of each page, under « Advanced »
at step 4. It was the default until 2026-10-01: it collapses thick strokes and
spot blacks to their outlines, but it also **erases** small dense detail it
takes for hatching — windows, pipes — with a median value of 247 on the lost
pixels (`reports/traits_fins/`). Measured with the whole ink: teddy_page_compliqué
goes from 1 106 to 2 020 zones, moebius from 390 to 610, antoine from 581 to
624; the layer count no longer depends on it.

Panel and bubble detection always read the raw mask, and `expand_under_lines`
reaches under raw ink, because the layer the artist drops on top is real ink.

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

**A panel with no relief still gets three planes.** A close-up comes back cut
in three. The artist moves the zones.

**Every stage is correctable in-app.** Panel and balloon corners are
draggable at steps 2 and 3; zones are merged and cut at step 4; zones move
between planes at step 5. Photoshop is where the page is coloured, not where
the machine's mistakes are repaired.

## Tests

    pytest

`tests/test_web.py` presses every button in order through the HTTP API, drags
a panel corner and traces a balloon the way the canvas does, sweeps up a dozen
zones and merges them, cuts one in two and counts the pixels back, moves zones
between planes, and opens the PSD that comes out — rule 3's "every screen reaches the next one",
as a test rather than a promise.
