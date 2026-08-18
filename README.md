# ComicColor

Upload a page, press five buttons, get a layered PSD.

    pip install -e ".[web,dev]"
    comiccolor serve

Then open <http://127.0.0.1:8000>.

| Button | What runs | Where |
|---|---|---|
| 1 Upload page | `load_line_art` | `segmentation/preprocess.py` |
| 2 Detect panels | gutter network → boxes → 4-corner polygons | `segmentation/panels.py` |
| 3 Detect bubbles | RT-DETR box → radial trace → polygon | `segmentation/bubbles.py` |
| 4 Segment zones | MangaLineExtraction → LineFiller trapped-ball, per panel | `extract/`, `segmentation/segmenter.py` |
| 5 Generate flats | proposer → per-zone mode → CIELAB snap | `colour/` |
| 6 Export PSD | group per panel, layer per colour | `export/psd.py` |

Character sheet / swatch upload is optional and does two jobs at once: its
colours become the palette that zones snap to, and the image itself is what
the model is shown as reference.

Nothing runs on its own, and re-running a step clears what depended on it.
There is no editing yet — corrections happen in Photoshop.

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

    comiccolor serve      # pulls the weights on first use, 161 MB into models/

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
    pip install -e third_party/Cobra/diffusers      # the patched fork
    pip install -r third_party/Cobra/requirements.txt
    comiccolor serve --proposer cobra              # pulls the weights on first use

`colour/cobra.py` is written against Cobra `48d6168` and **has never been
executed** — it was built on a 6 GB card with nothing installed. Verify it on
the GPU machine before trusting a pixel of it.

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

**Nothing is correctable in-app.** No dragging corners, no merging zones, no
reassigning a colour — that is the deliberate scope of this version. A wrong
panel or a false bubble gets fixed in Photoshop, or by not pressing that button.

## Tests

    pytest

`tests/test_web.py` presses every button in order through the HTTP API and
opens the PSD that comes out — rule 3's "every screen reaches the next one",
as a test rather than a promise.
