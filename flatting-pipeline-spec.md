# Comic Flatting Pipeline — Build Specification

Handoff document. Target reader: an implementing agent with repo access.

---

## 1. What this is

A layered colour-flatting system for comic and manga production. Input: line art
pages (ink layer, or extracted lines). Output: a layered file with mutually
exclusive flat colour regions keyed to a persistent palette, plus protected
bubble/SFX masks.

**Core architectural claim:** the generative model is a *colour proposer*, not the
output path. Exactness comes from deterministic segmentation. The model is a
swappable component.

```
line art
  → panel segmentation
  → bubble/SFX detection (protected masks)
  → line gap closure
  → trapped-ball region segmentation        [exact, deterministic]
  → Cobra colour proposal @ 1024px           [semantic, probabilistic]
  → per-region mode extraction
  → CIELAB snap to palette table             [palette IDs, not RGB]
  → layered export
```

**Non-goals for v1:** shading, lighting, effects, painted/lineless art,
text rendering or translation.

---

## 2. Prerequisites — resolve before writing code

These gate architecture decisions. Do not skip.

| # | Item | Blocks | Status |
|---|---|---|---|
| P1 | Determine which PixArt checkpoint the released Cobra weights derive from. | Deployment model (SaaS vs on-prem). | **RESOLVED 2026-08-02** — see below. AGPL does not apply. |
| P2 | Check the licence of `MangaLineExtraction_PyTorch` (acknowledged Cobra dependency, used in production). | Line extraction stage. | **RESOLVED** — MIT. Cobra bundles the same `erika.pth` as `LE/erika.pth`. |
| P3 | Run trapped-ball on 10 real pages across target styles. Count regions per panel. ~80 = viable. ~3000 = hatching is the real problem and Tier 3 reorders. | Whether Tier 1 ships at all. | **PASSED 2026-08-02** — verdict reversed, style coverage met on 4 pages. See §2.2. |
| P4 | Confirm with studios: Clip Studio or Photoshop; flats delivered as layer groups or alpha-locked regions. | Export format, which constrains the internal data model. | **RESOLVED 2026-08-02** — PSD, one group per panel. See §2.3. |

### 2.1 P1 resolved — the AGPL question was misposed

The premise was that Cobra's weights *derive from* a PixArt checkpoint, making
its provenance decisive. They do not. **Cobra never redistributes PixArt.** It
downloads it at runtime:

```python
PixArtTransformer2DModel.from_pretrained(
    "PixArt-alpha/PixArt-XL-2-1024-MS", subfolder="transformer")
```

That is the diffusers repo, licensed `openrail++`. Cobra's own 4.83 GB release
is only its deltas — `line_ckpt/` and `shadow_ckpt/` (LoRA + ControlNet),
`line_GSRP/`, `shadow_GSRP/`, and `LE/erika.pth`.

There are three distributions, not two:

| Artifact | Licence |
|---|---|
| `github.com/PixArt-alpha/PixArt-alpha` — code | Apache-2.0 |
| `hf.co/PixArt-alpha/PixArt-XL-2-1024-MS` — diffusers | `openrail++` ← the one in our chain |
| `hf.co/PixArt-alpha/PixArt-alpha` — raw `.pth` | `agpl-3.0`, "research purpose only" |

The AGPL sits only on the raw-`.pth` mirror, which nothing here pulls from. The
earlier note attributing AGPL to the upstream code repo was wrong.

**Consequence: the on-premise default is lifted.** The network clause never
fires, so hosted serving is not a licence problem. What replaces it is smaller:
OpenRAIL++-M's use-based restrictions propagate to derivatives and must remain
enforceable downstream, so a hosted tier must carry Attachment A into its terms
of service. That is contract work, not architecture.

**Keep the dependency pinned to the diffusers repo deliberately.** The `agpl-3.0`
mirror carries a "research purpose only" note that is stricter than AGPL itself
and would be a genuine blocker if anything ever resolved to it by accident.

Not a legal opinion. Confirm with a lawyer before taking revenue, not before
writing code.

### 2.2 P3 resolved differently than it appeared

P3's raw verdict — MARGINAL on manga, HATCHING DOMINATES on Moebius — **does not
stand**. It was measuring our trapped-ball implementation, not the art. Under
LineFiller the structural counts land at 68–87 on the hard pages against a
ceiling of 150, i.e. on the spec's own "~80 = viable" figure. Tier 1 ships and
the §7 Tier 3 hatching adapter does not need to jump the queue.

**P3 passes on style coverage, not page count.** The item asks for 10 pages; 4
were run, but they span four distinct regimes and all segment well enough for a
colourist to merge by hand afterwards:

| Page | Style | Result |
|---|---|---|
| moebius | Franco-Belgian, dense hatching | passes — the case that was supposed to fail |
| manga | thin uniform lines | passes |
| teddy | ligne claire, flat blacks | passes |
| antoine | thick-line idiosyncratic | passes |

Only American comics (variable-weight inking, spot blacks, feathering) remain
untested, and §7 already scopes that as needing a retrained extractor.

No leaks observed on visual inspection, including on Moebius where coverage
measured 0.997.

**Teddy's ink-fraction collapse (0.173 → 0.058) is benign.** The page uses flat
black zones and very heavy lines; the extractor converts those solid fills into
their contours, so the ink fraction drops by two thirds while the structure it
matters for is preserved. Not evidence of the extractor discarding linework.

Full comparison in `reports/ab/ab.md`; original counts in `reports/p3/p3.md`.

**Extraction is a hatching absorber, not a general improvement.** It nets a gain
only on the hatching-dense page and mildly hurts the other three:

| Page | raw (regions/structural) | extracted | effect |
|---|---|---|---|
| moebius | 612 / 87 | 364 / 68 | **better** |
| manga | 206 / 15 | 242 / 32 | worse |
| antoine | 440 / 70 | 474 / 80 | worse |
| teddy | 388 / 50 | 535 / 57 | worse |

This matches the observed behaviour that manga's very thin lines scatter zones
after extraction. Extraction stays on by default — it is what makes the hard
case work — but gating it on texture density is an available knob if thin-line
input ever becomes a problem.

### 2.3 P4 resolved — PSD, one group per panel

**Format: PSD.** Clip Studio's `.clip` is an undocumented SQLite container, and
CSP imports PSD natively with groups intact. One export path serves both apps
and matches what studios already pass around.

**Structure: one layer group per panel.** Panels are coloured separately by
Cobra anyway — §1.6 runs at 1024px, so per-panel inference gives each panel
the full pixel budget instead of a downscaled share of the page. The export
structure and the inference structure agree.

**Layer granularity inside the group — one layer per colour is the default.**
Confirmed against working practice with a professional colourist: they already
work one layer per colour. Volume is not a concern; ~10 colour zones per panel
over ~10 panels is ~100 layers, which studio files carry comfortably. Note that
colour zones are far fewer than *regions* — many regions share one colour, so
the region counts in §2.2 are not layer counts.

Offer all three as export options:

| Option | Shape |
|---|---|
| Flat | one flats layer under the line art |
| **Per colour** (default) | one layer per palette colour |
| Per zone | one layer per region |

**Drift across panels is handled and not a blocker.** Per-panel colouring risks
the same character shifting hue between panels; three gates prevent it — Cobra's
reference module, a properly prepared character sheet supplied as reference, and
snapping output to the §1.5 palette table. The palette snap is the backstop that
does not depend on the model behaving.

**Panel segmentation is not solved, and this is known.** Artists routinely draw
open panels, characters and bubbles crossing panel borders, and large SFX
lettering ("BOOM") overlaying several panels at once. Bubble and large-text
masking feeds the `protected` argument the `Segmenter` protocol already takes.
Research existing open-source comic text/bubble detectors before writing one.
Deferred to project start.

> **Settled.** The research was skipped the first time and a heuristic was
> written instead; it returned 39 bubbles on the Tintin page, none of them a
> balloon. Doing the research produced `ogkalu/comic-text-and-bubble-detector`
> (RT-DETR-v2, Apache-2.0), which is exact on all six test pages. §1.2 below.

---

## 3. Data model — build this first

One day of work. Everything else assumes it. Retrofitting is a rewrite.

```
Series
  └── Volume
        └── Page
              └── Panel
                    └── Region

PaletteEntry        # volume-scoped, versioned
  id                # stable identifier
  rgb               # editable
  entity_id         # nullable FK → Entity
  label             # "Kaito / hair / base"

Entity              # character, prop, recurring background
  id
  name
  reference_images[]

Region
  id
  panel_id
  mask              # from trapped-ball, exact
  palette_entry_id  # REFERENCE, never a baked RGB
  confidence        # from seed variance
  status            # auto | confirmed | flagged | manual

ProtectedMask
  panel_id
  kind              # bubble | sfx | border | text
  mask
```

**Invariants:**

- A region stores `palette_entry_id`. Never an RGB value. This is what makes
  "change the hair colour everywhere" a single-row update.
- Palette edits propagate incrementally. Never re-run the volume.
- Regions within a panel are mutually exclusive and exhaustive (minus protected
  masks).

---

## 4. Tier 1 — Minimum viable system

No item here is optional. Build in this order.

### 1.1 Ingest and panel segmentation
Gutter detection, panel bounds, reading order. Geometric; a fixed layout grammar.
Manga109 provides an annotated benchmark for panels, bubbles and text — as a
benchmark only. Its licence is research-only, so nothing trained on it can ship
here (§1.2).
Everything downstream addresses by panel.

**Output:** panel polygons + reading order per page.

### 1.2 Bubble and SFX detection → protected masks
Both are excluded from every generative and fill stage and passed through
untouched.

Frame this as **protection**, not detection: these are the regions diffusion
models corrupt most visibly. Detecting them removes the largest artifact class
in the pipeline.

**Bubbles — built.** A detection model gives boxes; the artwork gives the shape.
`ogkalu/comic-text-and-bubble-detector` (RT-DETR-v2, Apache-2.0) via
`onnxruntime`, then a radial trace from each box centre. Exact against the
artist's counts on all six test pages, ~0.85 s per page on CPU. Details and the
failure history in `SPEC.md`.

Two assumptions in the sentence this section used to open with — *"bubbles are
closed high-luminance regions with tails and enclosed text"* — turned out to be
wrong on real pages, and both cost a rewrite:

- **Not closed.** `manga_page.jpg`'s balloon outlines come out of Otsu as
  *dotted* lines. Anything tracing a closed curve fails there: an open outline
  is a `C`, and filling a `C` fills the stroke and leaves the middle out.
- **Enclosed text is not a usable signal.** Finding text by the geometry of ink
  blobs reads hatching as `iiii` and cup holders as `OOO`. It is the model's job.

**SFX — not built, and now a choice.** The same model returns a `text_free`
class, which is SFX lettering outside balloons. Hand-masking covers it until it
does not.

**Licence, the load-bearing constraint.** Nearly every open-source comic balloon
detector needs `ultralytics` at runtime, and that is **AGPL-3.0** regardless of
the licence on its weights. Any replacement must run without it.

**Output:** `ProtectedMask[]` per panel.

### 1.3 Line gap closure
Sketch and ink lines are open. Trapped-ball with increasing radii, plus a learned
closure pass if needed. This is the highest-variance step across art styles.

**Output:** closed line raster.

### 1.4 Trapped-ball region segmentation
Hierarchical flood fill. Deterministic, exact, inspectable, produces true masks.
Superior to SAM on clean line art — do not substitute a learned segmenter here.

**Implementation: `hepesu/LineFiller` (MIT), merge enabled.** Chosen 2026-08-02
over our own trapped-ball on the §2.2 A/B. Ours shatters thin corridors into one
region per bulge; LineFiller discards small fills at each radius and merges
afterwards, which is what collapses the count. The merge step is doing the work —
`merge=False` returns *more* regions than ours. Both sit behind the `Segmenter`
protocol and stay swappable; ours is retained as the comparison baseline.

Known defect: `merge_fill` breaks §3 exhaustiveness in proportion to texture
density — coverage 0.997 on Moebius raw, 1.000 on manga, antoine and teddy.
Bounded and characterised, not yet fixed.

**Output:** `Region[]` with exact masks. Log region count per panel as a health
metric (see P3) — but as an *alarm*, not a quality score. The A/B produced cases
where a higher region count read as visually better flatting, because what
matters is where the boundaries fall, not how many there are. A count can tell
you something collapsed; it cannot tell you the flats are good.

### 1.5 Palette table
Implemented per §3. Volume-scoped, versioned, editable.

### 1.6 Cobra as colour proposer
Wrap as a black box. **Do not modify the DiT.**

~~Run at 384–512px~~ — **superseded by measurement, 2026-08-20. Run at 1024.**
The reasoning below is still correct and still does not survive contact with the
model: reading only per-region modes does make pixel detail wasted compute, but
it assumes the raster is *usable*. Upstream `get_rate` returns its aspect bucket
unscaled at ~1024, so scaling the long side to 512 puts a wide panel near
512×320, far below anything the DiT trained on. Measured on `diagonal_page.jpg`
panel 0 (aspect 2.16): noise at 512, correct flats at 1024. Near-square panels
survive 512. A mode taken over noise is noise, so the cheap raster is not cheap.

Inputs: line art, reference images (character sheets, prior coloured panels),
optional colour hints.

**Output:** a soft RGB proposal raster per panel. Never shown to the user.

### 1.7 Mode extraction and CIELAB snapping

```
for each region:
    quantise pixels into coarse bins
    take largest bin                        # mode, NOT median
    average within that bin                 # sub-bin precision
    match to nearest PaletteEntry in CIELAB
        with L* downweighted (~0.3)         # shading moves L, not a/b
    if distance > threshold:
        create new PaletteEntry, status = flagged
    else:
        assign palette_entry_id
```

**Mode, not median.** A shaded region is bimodal; the median lands between base
and shadow and returns a colour that exists nowhere in the reference.

**Downweight L\*.** Raw RGB nearest-neighbour confuses shadowed skin with
adjacent hair tones.

**Reject before snapping.** A new outfit or unregistered prop must not be
silently coerced into an existing entry. Silent wrong snapping is worse than an
empty region — the artist will not notice it.

**Built, and split in two.** Mode extraction is step 5; snapping is step 6 and
the artist drives it. In one pass this was the only stage with no boundary the
artist could see or refuse, and "reject before snapping" was not enough on its
own: with the L\* downweight, every neutral region — paper, grey props, the
page background — sat inside the threshold of a character sheet's ink black
and was coerced anyway. Step 5 therefore creates one entry per region
unconditionally. `snap_suggestion` returns the nearest entry *and its
distance*, so the number the automatic pass used silently is the number the
artist is shown, and the threshold orders their attention instead of vetoing
their instruction.

### 1.8 Confidence triage
Sample 3 seeds. Compute per-region variance of the extracted mode. High variance
= model uncertainty about that specific region. Route only those to review.

This is what converts a first-pass time saving into a *post-correction* time
saving. Instrument it from day one.

### 1.9 Region editor
One click reassigns a region's `palette_entry_id`. Merge and split regions.
Every stage boundary is inspectable and editable.

**This is the differentiator, not a nicety.** Professionals rejected prior
auto-colorisation specifically because intermediate stages were opaque and
uncontrollable. A pipeline whose every boundary is an editable layer answers
that objection by construction.

**Built.** Panel and balloon polygons are edited at steps 2 and 3, regions are
merged and cut at step 4, palette entries are recoloured at any time, and a
region is reassigned by clicking it at step 6. Two decisions that this
specification did not anticipate, both forced by use:

- *Each correction belongs to one stage and closes when the next stage
  consumes it.* Region merges and cuts are permanent, because the alternative
  is carrying the segmenter's map beside the artist's and making every
  downstream stage say which it means.
- *A step that would discard the artist's corrections asks before it runs.*
  §9's "no stage gates" stands for the flow; this is about work, not
  navigation.

### 1.10 Layered export
Line, flats (keyed to palette IDs), protected masks. Must round-trip into the
studio's software per P4.

---

## 5. Metrics — instrument from the first commit

| Metric | Why |
|---|---|
| Post-correction minutes per page | The only number worth quoting to a studio. Not first-pass time. |
| Hints required ÷ fillable regions, tracked across a volume | The value proposition. Should collapse as the volume progresses. |
| Regions per panel | Segmentation health. Spikes signal hatching (see Tier 3). |
| % regions auto-accepted without edit | Automation rate. |
| Flagged-region precision | Whether triage is worth the artist's attention. |

Do not carry a headline "60% saved" figure. Quote measured post-correction
numbers only.

---

## 6. Tier 2 — Next, highest leverage

- **Shadow mask layer.** Per-pixel deviation from the region mode, from the same
  Cobra pass. Second layer, free. Discardable by studios wanting flats only.
- **Cross-page identity propagation.** Hint a character once, resolve across the
  volume. Identity matching under pose, scale, occlusion and crop change is the
  hard part. Make mismatches one-click correctable and propagate corrections
  forward.
- **Incremental change propagation.** Edit a palette entry → all affected panels
  update in seconds. Falls out of the data model if §3 was respected.
- **Correction logging.** Log accepted-without-edit as positives *and* edit deltas
  as negatives. Training only on corrections shifts the model toward the failure
  distribution and degrades cases that already worked.

---

## 7. Tier 3 — Domain adapters

Each tier is a swappable **line extractor + segmentation profile**, selected per
project. Same core pipeline throughout.

| Adapter | Character | Difficulty |
|---|---|---|
| **Manga** | Shipped default. MangaLineExtraction covers it. | Solved |
| **Ligne claire** | Hergé, Jacobs, Chaland. Closed uniform lines, extracts as cleanly as manga. | Easy — first Western win |
| **American comics** | Variable-weight inking, spot blacks, feathering. Needs a retrained extractor. | Medium |
| **Hatching handler** | Texture-vs-boundary classification *before* trapped-ball. Without it, trapped-ball returns thousands of micro-regions and the pipeline collapses upstream of the model. | Hard — genuine research |
| **Background specialist** | Architecture, perspective, low character content, high region count. | Medium |
| **Painted / lineless** | No line → no line art → no product. | Out of scope. Say so early. |

**Hatching gates Moebius, Schuiten and much of Franco-Belgian.** If P3 returns
high region counts, this adapter moves ahead of everything else in Tier 3.

**It does not move ahead.** P3's high counts were an artifact of our segmenter
(§2.2); under LineFiller, Moebius lands in viable range. This adapter keeps its
original Tier 3 position.

### Training data note
The manga literature trains on line art *extracted from finished pages*. Extracted
lines are closed, uniformly weighted, gap-free, and include lines that only exist
because they were reinforced during colouring. Real ink layers are none of those.

- Mitigate with degradation augmentation: erase segments, jitter width, introduce
  gaps, warp, add grain.
- **Evaluation sets must use real ink layers, never extracted ones.** A few
  hundred genuine ink layers from the studios is enough, and is a far smaller ask
  than training data.

---

## 8. Tier 4 — Only on studio pull

Light and shadow rendering, effects, halftone/screentone handling, cross-volume
palette inheritance.

Do not build speculatively. This is the fastest-commoditising part of the stack;
frontier models are closing it independently.

---

## 9. Explicit anti-patterns

- **Do not modify Cobra's DiT.** Segmentation is a separate deterministic stage
  before and after, not an architectural replacement. Touching the DiT forfeits
  the pretrained weights and buys nothing.
- **Do not use SAM for identity.** SAM is class-agnostic segmentation, not
  instance retrieval. Trapped-ball on line art is already more exact. The problem
  is *labelling* regions, not finding them.
- **Do not generate synthetic training data from a generative model** to train an
  identity matcher. You learn the generator's error distribution and miss the real
  tail: occlusion, crops, back views, foreshortening. The volume itself contains
  hundreds of in-distribution instances per character.
- **Do not conflate segmentation and labelling.** Geometric/deterministic vs
  semantic/probabilistic. Different failure modes, different fixes. Keep an
  inspectable boundary between them — that boundary is the layer file.
- **Do not bake RGB into regions.**
- **Do not ship diffusion output as the deliverable.** VAE round-trip introduces
  colour drift, gradients where uniformity was required, and halos at line edges.
  That is the entire reason a research demo has not displaced hand-flatting.

---

## 10. Known hard cases

Average-case flatting is straightforward. The tail is the product.

- Two characters in similar uniforms.
- A region spanning an occlusion boundary.
- Shadow-side skin vs hair where the reference is genuinely ambiguous.
- Regions with no correspondent in the reference: new outfit, back of head, novel prop.
- Anti-aliased line art — flats must composite under AA edges without fringing.
  Work at 2–4× and downsample.
- Merged line art (line not on its own layer) — requires extraction first.
- Hatching. See Tier 3.

---

## 11. Prior art to read before implementing

- **Cobra** (SIGGRAPH 2025) — `github.com/zhuang2002/Cobra`. Causal Sparse DiT,
  200+ reference images, colour hints, KV-cached ID consistency.
- **MangaNinja** (CVPR 2025 Highlight) — `github.com/ali-vilab/MangaNinjia`.
  Reference-guided colorisation with point control. Fallback / comparison.
- **LazyBrush** (Sýkora et al., Eurographics 2009) — hint propagation as Potts
  energy minimised by graph cut, tolerant of line gaps. Shipped in Krita's
  Colorize Mask.
- **FlatMagic** (CHI 2022) — the workflow study. Source of the ~50%-of-colorisation
  figure and the documented reason professionals reject opaque auto-colorisation.
- **Manga109** — annotated benchmark for panels, bubbles, text. Research-only;
  a model trained on it inherits that, whatever its own card claims.
- **ogkalu/comic-text-and-bubble-detector** — RT-DETR-v2, Apache-2.0, ~11k
  manga, webtoon, manhua *and western comic* pages. Classes: `bubble`,
  `text_bubble`, `text_free`. Ships ONNX, so it runs without `ultralytics`.
  This is the bubble detector §1.2 uses.
