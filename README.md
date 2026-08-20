# ComicColor

Upload a page, press five buttons, get a layered PSD.

    pip install -e ".[web,dev]"
    comiccolor serve

Then open <http://127.0.0.1:8000>.

| Button | What runs | Where |
|---|---|---|
| 1 Upload page | `load_line_art` | `segmentation/preprocess.py` |
| 2 Detect panels | gutter network → traced polygons, box fallback | `segmentation/panels.py` |
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
    pip install -e third_party/Cobra/diffusers      # the patched fork, required
    pip install transformers peft accelerate einops sentencepiece matplotlib
    comiccolor serve --proposer cobra              # pulls the weights on first use

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
face can retrieve something that is not a face. This matters for promoting
corrected pages to references: crop them to character scale first.

**Colour hints propagate, but not reliably.** A hint filled a whole ink-bounded
region in one test and only tinted it in another. When measuring one, sample
*outside* the hinted rectangle — inside it the colour is whatever was painted
there, so the measurement always succeeds and means nothing.

**Nothing is correctable in-app.** No dragging corners, no merging zones, no
reassigning a colour — that is the deliberate scope of this version. A wrong
panel or a false bubble gets fixed in Photoshop, or by not pressing that button.

## Tests

    pytest

`tests/test_web.py` presses every button in order through the HTTP API and
opens the PSD that comes out — rule 3's "every screen reaches the next one",
as a test rather than a promise.
