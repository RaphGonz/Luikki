# Feature Research

**Domain:** AI-assisted comic/manga colour flatting tools, for professional colourists
**Researched:** 2026-08-02
**Confidence:** MEDIUM-HIGH (primary sources for workflow and prior-art claims; MEDIUM on bubble/SFX detector accuracy since no candidate has been benchmarked on this project's own four style regimes)

This research assumes the deterministic segmentation core (panel gutters, line-gap
closure, trapped-ball regions via LineFiller) is already built and validated — see
`.planning/PROJECT.md` Validated section and `flatting-pipeline-spec.md`. It scopes
the artist-facing layer on top: project/palette management, the two editing
surfaces, the colour-proposal-and-snap pipeline, and export.

---

## Grounding: the professional flatting workflow (sourced, not assumed)

The single best-sourced artifact in this domain is **FlatMagic** (Yan, Chung, Yoon,
Gingold, Adar, Hong — CHI 2022, `https://johnr0.github.io/assets/publications/CHI2022-flatmagic.pdf`,
read directly, HIGH confidence). Its formative study (S1) interviewed five
professional colourists with 3+ years of commercial experience on platforms like
Webtoon and Lezhin. Findings, load-bearing for this project:

- **Colouring is a five-stage pipeline**: flatting → shadowing → lighting →
  background → special effects. Every participant used this same sequence.
- **Flatting is ~50% of total colouring labour**, and it is explicitly described as
  the *cheapest to outsource and least "owned"* stage — participants happily hand
  it to assistants (P5: assistants flat 50-60 panels/week; P5 then spends 40% of
  his remaining time re-touching their work) or would happily hand it to AI,
  **unlike** shading/lighting, which participants treat as their creative
  "signature" and explicitly do not want automated (P3: "I'm not sure if AI-driven
  shading and lighting can even be possible. I'm very dubious"; P5: fears an
  "occupational crisis" if shading/lighting were automated).
- **Two hard requirements professionals hold flats to**: *flat consistency* (a
  region must stay inside its intended boundary, never bleed into a neighbour) and
  *flat completeness* (regions are mutually exclusive and collectively exhaustive).
  This is the exact requirement your data model already encodes structurally
  (§3, mutually-exclusive label map) — it is not a nice-to-have, it is the
  professional bar for "did this even work."
- **Two failure modes cause most manual flatting time**: *falsely closed lines*
  (an unbroken line wrongly divides what should be one region — needs merging)
  and *falsely opened lines* (a gap lets fill spill across a boundary — needs
  closing). These map directly onto your click-merge and line-gap-closure
  features respectively.
- **Why professionals reject existing AI colorization tools**: not automation in
  principle — they *want* flatting automated — but **lack of control over
  intermediate outcomes**. P1: "The tool gives me automated results using my
  initial hints... I couldn't really use the outcome because it applies random
  colors here and there... I need control over every detail." P4: "there is no
  convincing reason to use the tools because it would double colorization
  processing time" (i.e. cleanup after a bad automated pass costs more than doing
  it by hand). This is the direct evidentiary basis for the "every stage boundary
  is inspectable and editable" differentiator already stated in `PROJECT.md`.
- **FlatMagic's measured result**: a controlled study (S2-1, 16 art students) found
  FlatMagic **reduced flat-colorization completion time by 30%**; a semi-deployment
  study (S2-2, 5 professionals) found participants felt it fit their workflow
  because its automation "cut down on their labour while meeting quality
  standards" — i.e. it earned trust by staying inspectable, not by being more
  automated.
- **FlatMagic's own feature set (F1-F7)** is a near-exact functional precedent for
  this project: F1 *Colorize* (bucket-click a coarse AI region), F2 *Fine colorize*
  (bucket-click a finer AI region), F3 *Tweak* (draw a line to manually correct a
  wrong boundary — this is literally your trace-split), F4 *View Options* (toggle
  the AI's working lines visible/hidden), F5 *Declutter* (auto-annex tiny
  unfilled slivers into a neighbour), F6 *Export as Layers* (each region its own
  layer), and — most relevant to your palette question — **F7 *Load Swatch*: a
  JSON colour-swatch file loadable per document so colourists get consistent
  colours across every page of a comic.** This is independent validation from a
  peer-reviewed HCI study that "a persistent, project-scoped colour swatch shared
  across pages" is table stakes, not a guess.

Two comparisons FlatMagic makes explicitly, both confirming your project's
choices: Zhang et al.'s end-to-end learned colourization produces visible colour
*bleeding* at boundaries (evidence against ever shipping raw diffusion output);
Sýkora et al.'s **LazyBrush** (Eurographics 2009, the algorithm behind Krita's
Colorize Mask) "intelligently interprets imprecise placement of user input... but
LazyBrush's heuristics sometimes lead to incorrect flat colour region boundaries"
— i.e. hint-propagation-only approaches are fundamentally weaker than exact
segmentation-then-snap for the *consistency* requirement above.

---

## Prior art surveyed

| Tool | Interaction model | What the colourist controls | Why accepted / rejected |
|---|---|---|---|
| **Clip Studio Paint — reference-layer fill** | Flag a line-art layer as "reference"; bucket/lasso tools on other layers then respect that line art as a fill boundary. 4 fill sub-modes (refer-only-editing-layer / refer-other-layers / enclose-and-fill / paint-unfilled-area). | Which layer is authoritative for boundaries; per-click fill. | Accepted broadly — it is the industry-standard manual flatting technique, not AI. Cheap, predictable, zero trust cost because there's no model in the loop. |
| **Clip Studio Paint — Colorize (AI, "Technology Preview")** | One click ("Colorize All") or a hint-stroke layer, referencing the line-art layer, produces a full auto-colourized result. | Only the hint strokes; the colourisation itself is opaque. | Explicitly named by FlatMagic's own participants (P1) as rejected for "applying random colors... I need control over every detail." Still labelled "Technology Preview" years after its 2022 introduction — even the vendor treats full-page auto-colourize as not production-ready. Source: `clip-studio.com` official guide, `johnr0.github.io` CHI2022 paper. |
| **Krita Colorize Mask (LazyBrush, Sýkora et al. 2009)** | Paint coarse coloured strokes on a mask layer over line art, press Update, get a full recolour; strokes are freely re-editable before "convert to paint layer." | Stroke placement and colour; tolerant of small line gaps (Potts-energy graph cut). | Popular with hobbyists/animators for speed; FlatMagic's own comparison shows it "creates inaccurate boundaries" on complex art — the same class of failure the project's own line-gap-closure work targets. Good for quick iteration, not for delivery-grade flats. |
| **FlatMagic (CHI 2022)** | See workflow section above. Photoshop plugin; three-layer canvas (input lines, AI "neural redrawing," AI regions shaded as visual aid). | Bucket-fill each AI-proposed region (2 granularities), manually tweak wrong boundaries by drawing a line, toggle AI lines on/off, declutter slivers, load/save a JSON swatch. | Accepted in both of its own studies specifically **because** it kept the intermediate region map visible and editable rather than collapsing straight to a final render. This is the strongest single piece of evidence behind your project's "every boundary is a layer" thesis. |
| **Petalica Paint / PaintsChainer** | Upload a sketch, get a one-click full auto-colourization; casual + "pro" tiers existed. | Almost nothing — a prompt-like service, not an editor. | Discontinued 2025-07-31 (source: multiple tool-status pages, MEDIUM confidence on cause — the discontinuation is a fact, the causal link to professional rejection is inference, not confirmed). Consistent with FlatMagic's broader observation that "existing solutions... over-automate the problem rather than supporting professional workflows." |
| **Cobra (SIGGRAPH 2025, `zhuang2002/Cobra`)** | Reference-conditioned diffusion; demo interface exposes line art, reference images, resolution, seed, steps, top-k reference selection, an optional hint mask + hint colour. | Which references to use, an optional colour hint per region, seed. | Already the chosen proposer in this project's pipeline, wrapped as a black box per spec. Its own demo already exposes a "hint mask/hint colour" input the project doesn't currently use in v1 — flagged below as a plausible v1.x differentiator once triage-and-snap alone proves insufficient on stubborn regions. |
| **MangaNinjia (CVPR 2025 Highlight, `ali-vilab/MangaNinjia`)** | Point-driven control: user places matched point pairs between a reference image and the line art to pin specific colour correspondences, handling extreme poses / cross-character colourization / multi-reference harmonization. | Exact point-to-point colour correspondence. | Not adopted (Cobra already chosen) but the interaction pattern — click a source pixel, click a target pixel, force that correspondence — is a stronger, more explicit hint mechanism than free-stroke hints. Worth remembering as a future differentiator if CIELAB-snap-and-triage alone leaves too many regions ambiguous; same VAE-roundtrip caveat applies (never ship its raster as the deliverable). |
| **Lazy Nezumi Pro** | *Correction to the research prompt*: this is a mouse/pen **line-stabilization and ruler** plugin for Photoshop/CSP, unrelated to colourization or flatting. Included in the prompt's list, but it has no bearing on this domain — noting this explicitly so it isn't mistakenly treated as prior art for flatting UX. | — | — |

---

## Bubble/SFX protected-mask options — ranked shortlist

This was flagged as the highest-value search in this task. The project's own
Key Decision already treats manual masking as the **guaranteed fallback** and any
detector as an **upgrade, not a dependency** — the findings below support keeping
exactly that posture, and give a concrete recommendation for what the upgrade
path looks like.

**Bottom line verdict: a good-enough off-the-shelf option exists for *detection*
(bounding boxes with bubble/text classification), not for pixel-perfect
*segmentation*, across your full style range — but that gap doesn't matter here,
because this project's own downstream trapped-ball segmentation already produces
exact zone masks. Protection can be implemented as "exclude any already-segmented
zone whose footprint falls under a detected bubble/text box," which only needs a
detector, not a segmenter. Manual masking should stay the primary, first-class UI
for v1 (not a rare escape hatch) because no candidate below has been validated on
Franco-Belgian, ligne claire, or thick-line styles — every training set is
manga/webtoon/manhua-first with an unquantified "Western comic" slice at best.**

| Rank | Model | License | Detects | Output | Style coverage (training data) | Verdict |
|---|---|---|---|---|---|---|
| 1 | **`ogkalu/comic-text-and-bubble-detector`** (HF) | Apache-2.0 | 3 classes: `bubble`, `text_bubble` (text inside bubble), `text_free` (text outside bubble — closest proxy for SFX) | RT-DETR-v2 r50vd, **boxes only**, no native mask | ~11k images, Manga/Webtoon/Manhua/Western comic mixed | **Primary candidate.** Broadest style coverage of anything found, permissive licence, and `text_free` gives a usable SFX proxy class. Pair its boxes with your existing region segmentation rather than needing it to output masks. |
| 2 | **`ShadowB/Manga109-panel-balloon-text-yolov26-segmentation`** (HF) | MIT | 3 classes: `frame`, `text`, `balloon` | YOLO26s, **real instance-segmentation masks**, mask mAP@0.5 = 0.970, mask mAP@0.5:0.95 = 0.846, ~23MB, ~11.4M params | 10,130 images, entirely Manga109-derived (`MS92/MangaSegmentation` + `ShadowB/Manga109_RegionLevelTextSegmentation`) | **Best raw accuracy and the only one with native pixel masks**, and MIT licence is clean by way of Manga109-s condition 5 (commercial use of ML results permitted with attribution). But it is manga-only in training and does not split SFX from dialogue text (single `text` class). Good secondary pass for manga-style pages specifically; do not assume it generalizes to Franco-Belgian/ligne claire pages. |
| 3 | `ogkalu/comic-text-segmenter-yolov8m` (HF) | Apache-2.0 | Text only (bubble vs free-text split unclear from docs) | YOLOv8m, "detection and segmentation" per model card, output format for masks not confirmed in available docs | ~3k images, Manga/Webtoon/Manhua/(few) Western | Worth a smoke test alongside rank 1 if `text_free` precision on SFX/onomatopoeia proves weak, but unverified enough to plan around for MVP. |
| 4 | `kitsumed/yolov8m_seg-speech-bubble` (HF) | **GPL-3.0** | Speech bubbles only | YOLOv8-seg, real instance masks, author notes edges are "often wavy" | Undocumented size/source | Technically capable (real masks), but GPL-3.0 is the wrong licence shape for a project that has already gone out of its way to keep its dependency chain clear of copyleft (cf. the Cobra/AGPL resolution in `flatting-pipeline-spec.md` §2.1). Do not adopt unless ranks 1-2 prove insufficient. |
| 5 | `dmMaze/comic-text-detector` | **GPL-3.0** | Generic "text" (bbox + segmentation + text-line), no bubble/SFX class split | YOLOv5 (boxes) + DBNet + UNet (segmentation) combo | ~13k images: 1/3 Manga109-s, 1/3 DCM, 1/3 synthetic | Same GPL-3.0 concern as rank 4, and it solves a narrower problem (no bubble-vs-SFX distinction) than rank 1. Not recommended. |
| 6 | `ragavsachdeva/magi` (v1/v2/v3) | **Non-commercial only** — "personal, research, non-commercial, and not-for-profit... contact author for other usage" | Panels, text blocks, character boxes, character clustering, speaker attribution | Boxes + clustering, no bubble segmentation mask | Manga109 + custom character-bank data (11K+ characters, 76 series) | **Disqualified on licence terms alone** for a project intended to be open-source with a possible SaaS tier. Genuinely the most sophisticated system found (full transcript generation, CVPR 2024/ACCV 2024), but not usable here. Keep only as a quality benchmark. |
| 7 | BallonsTranslator ecosystem (`dmMaze/BallonsTranslator`) + `lhj5426`'s YSGDetector (onomatopoeia-specific filter) | Undocumented in material found | Bundles multiple of the above; YSGDetector specifically "filters out onomatopoeia in CGs/Manga" | Varies by bundled detector | Varies | Not a standalone dependency — it's a full translation application. The onomatopoeia-specific detector is a genuine lead for SFX-only precision but licence and standalone usability are unverified (LOW confidence). Worth a deeper look only if SFX precision becomes the specific bottleneck later. |
| — | Manga109 / Manga109-s (dataset) | Academic → commercial ML-result use permitted under Manga109-s condition 5 with attribution | Frames, speech text, character faces/bodies, 500,000+ annotations | Ground truth for training, not a runtime model | 109 manga volumes | Explains why rank 2 can be MIT despite Manga109 heritage. Manga-only; not useful for Franco-Belgian coverage. |
| — | eBDtheque (dataset) | Registration-gated, redistribution/commercial-ML terms not found in available material | Panels, balloons, text lines with semantic annotation | Ground truth only | 100 pages spanning **Franco-Belgian, American, and manga** styles — the one dataset found that isn't manga-first | If Franco-Belgian-specific detector fine-tuning is ever pursued, this is the dataset to formally request, not to assume is freely usable. LOW confidence on licence terms — flagged for validation, not stated as fact. |

**Confidence on this whole section: MEDIUM.** All licence and class information comes
from official model cards / repos (HIGH confidence per-fact), but no candidate's
actual precision/recall on this project's four validated style regimes (manga,
Franco-Belgian hatching, ligne claire, thick idiosyncratic) has been measured —
that is a concrete, cheap next step (run rank 1 and rank 2 against the same four
pages already used for the P3/A/B segmentation spike) before deciding how much
weight the in-app manual masking tool needs to carry in v1.

---

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| Persistent project with cross-page palette accrual | FlatMagic's F7 "Load Swatch" is peer-reviewed validation that professionals need one swatch shared across every page of a comic, not per-page colour picking. | LOW-MED | Data model already validated (`model/entities.py`, `model/store.py`). |
| Swatch-image upload → palette entries | Matches how colourists already prepare a project before flatting begins (a discrete colour board per character), and is the direct analogue of "extract palette from image" features already normalized in general design tools (Adobe Color, Procreate) — MEDIUM confidence, no comic-specific precedent found, inferred from adjacent tooling. | LOW-MED | Source of truth for the palette per Key Decision in `PROJECT.md`; character-sheet extraction is a proposal layer on top, not a replacement. |
| Character-sheet palette proposal with accept/reject/edit | Same rationale as above; must stay a proposal, never authoritative, per Key Decision. | MED | Simple colour clustering + de-dup is the likely floor; review UI is the bulk of the effort. |
| Manual palette entry add/edit/name | Baseline CRUD underneath both of the above; without it, a wrong auto-extraction has no correction path. | LOW | — |
| Panel polygon detection + full vertex editing (drag/add/delete) + draw-from-scratch | Spec is explicit: "panel segmentation is not solved... making the boundary editable sidesteps the research problem" — this is stated as a known-hard, permanently-open problem, not a temporary gap. | MED-HIGH | Detection exists but unvalidated on diagonal/open panels (`segmentation/panels.py`). The editing surface, not a better detector, is the actual requirement. |
| Protected bubble/SFX masking, manual masking as guaranteed fallback | Without protection, the diffusion proposer corrupts these regions "most visibly" (spec §1.2); no surveyed detector is proven across this project's full style range (see shortlist above). | MED (detector integration) to MED-HIGH (a good manual lasso/polygon tool) | Manual tool must be first-class UI, not a rarely-used escape hatch — no detector shortcut is safe to rely on solely. |
| Zone click-merge | CVAT's Join tool (press J after selecting touching same-label polygons) is the established cheap gesture in the closest adjacent domain (annotation tooling); FlatMagic's users expect one-click region actions. | LOW-MED | Should stay a single interaction, not select-then-confirm-then-apply. |
| Zone trace-split | Direct analogue of CVAT's Slice tool and FlatMagic's F3 "Tweak" (draw a line to redraw a wrong boundary) — convergent precedent from two independent tools in adjacent domains. | MED | Must cut the label map only, never touch the exported line art, per spec invariant. |
| One-click colour reassignment in colour-correction view | Direct analogue of FlatMagic's F1/F2 bucket-click Colorize — the cheapest possible correction gesture, and central to the stated Core Value ("one click to fix"). | LOW | — |
| CIELAB snap with reject-before-snap (flagged, not silently coerced) | FlatMagic's "flat consistency" requirement plus the project's own principle that "silent wrong snapping is worse than an empty region — the artist will not notice it" (spec §1.7). | MED | Mostly an algorithm question (mode extraction, L* downweight, distance threshold) rather than a UI one. |
| Confidence triage (3-seed variance) surfaced to the artist | This is what turns a first-pass time saving into a *measured* post-correction saving (spec §1.8) — without it, every region needs review, which is exactly the "monotonous, labour-intensive" complaint FlatMagic's own participants raised about flatting in general. | MED | — |
| PSD export, one group per panel, 3 layer granularities | This is the literal deliverable; format and structure already resolved (P4) and confirmed against a working colourist's actual practice (one layer per colour, matching Key Decision). | LOW-MED | — |
| Post-correction metrics instrumentation (minutes/page, hints ÷ fillable regions, auto-accept rate, flagged-region precision) | Not artist-facing, but the project cannot demonstrate its own value proposition without it, and the spec is explicit it cannot be retrofitted (§5, "instrumented from the first commit"). | LOW | Internal/producer-facing table stake, distinct from the user-facing rows above. |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---|---|---|---|
| Every pipeline stage boundary is an inspectable, editable layer | This is the project's own stated central thesis, and it is directly evidenced by FlatMagic's finding that professionals reject prior tools specifically for opaque intermediate stages. No surveyed competitor (CSP Colorize, Petalica, LazyBrush) exposes intermediate stages this thoroughly. | HIGH (spans the whole app) | This is the actual product, not a nicety — restated from `PROJECT.md`. |
| Confidence-triage-driven review queue (only flagged zones need attention) | None of the surveyed tools surface a per-region confidence signal at all — CSP/Petalica give an all-or-nothing result, FlatMagic gives per-region fill control but no variance-based triage. Converts "review everything" into "review the ~10% that's actually uncertain." | MED | Directly targets the "monotonous, labour-intensive" complaint from FlatMagic's S1. |
| Palette-referenced (never-baked-RGB) data model enabling instant global recolour | "Change the hair colour everywhere" as a single-row update is not a first-class primitive in any surveyed tool — FlatMagic's swatch file is a static preset list, not a live reference graph; CSP/Krita bake colour into pixels. | MED (already validated) | This is a genuine structural advantage over every competitor surveyed, not just a UI polish item. |
| Two distinct editing surfaces (geometry, then colour) | Cleaner mental model than the single undifferentiated canvas every surveyed competitor (CSP, Krita, FlatMagic) uses, at the cost of more UI. | MED | Explicitly a Pending Key Decision (a hypothesis), not a proven win — validate directly against the working colourist during the supervised video-call testing this project already plans. |
| Reject-before-snap CIELAB matching (flags novel colours instead of coercing them) | No surveyed tool does this. LazyBrush/CSP Colorize/raw Cobra output all either force a nearest colour or leave uncorrected diffusion output. Closes exactly the trust gap FlatMagic identified as the reason professionals distrust AI colourization. | MED | — |
| Cross-style segmentation robustness (manga, Franco-Belgian hatching, ligne claire, thick idiosyncratic) already proven | The entire bubble/SFX detector ecosystem surveyed above is manga-first (Manga109-trained); this project's own segmentation core is already validated across a wider style range than any off-the-shelf detector. | Already validated | Worth remembering when deciding how much to trust an external detector vs. the project's own pipeline. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|
| Full one-click page auto-colourize | Looks like the biggest possible time saving; CSP Colorize and Petalica Paint both shipped this. | FlatMagic's own interviewees explicitly rejected it for "applying random colors... I need control over every detail," and reported it can *double* processing time once cleanup is counted. CSP's version is still labelled "Technology Preview" years later; Petalica Paint was discontinued in 2025. | Per-region proposal + confidence triage + one-click override (already the plan). |
| Auto shading / lighting | Seems like a natural next automation step after flats. | Professionals explicitly treat this as their creative "signature" and do not want it automated (FlatMagic P3, P4, P5 quotes above) — unlike flatting, which they're happy to hand off. Already correctly scoped to Tier 2/4 in the spec. | Ship flats only in v1; a discardable shadow-mask *layer* (per-pixel deviation from region mode) is a reasonable Tier 2 add, never baked into the base flats. |
| Learned/SAM-based region segmentation replacing trapped-ball | SAM is well-known, general-purpose, tempting to reach for. | Already an established anti-pattern in this project's own spec (§9): SAM is class-agnostic segmentation, not instance retrieval — the problem here is *labelling* known regions, not finding unknown ones. Trapped-ball is exact and cheaper on clean line art. | Keep trapped-ball (LineFiller) as the segmenter; use learned models only for detection/labelling tasks like bubble/SFX. |
| Cross-page automatic character identity propagation | Feels like the natural companion to "palette persists across pages" — why not auto-resolve which character a region belongs to? | Identity matching under pose, scale, occlusion, and crop change is a genuinely hard, unsolved research problem; a low-precision automatic resolver creates *silent wrong palette assignment*, which the spec itself calls worse than an empty region ("the artist will not notice it"). Already correctly deferred to Tier 2. | Palette persists across pages (already planned); identity resolution stays a manual, one-click-per-page decision for v1. |
| Building a custom bubble/SFX detector from scratch | The problem looks self-contained and the pipeline already has a `Segmenter`-style seam for it. | Directly violates the project's own standing rule ("search for an existing tool before writing one... learned the expensive way on the trapped-ball implementation"). Multiple Apache-2.0/MIT off-the-shelf options exist (see shortlist) and cover most of the need. | Integrate `ogkalu/comic-text-and-bubble-detector` (boxes) + existing region segmentation for masks; fall back to manual masking where it fails. |
| Real-time multi-user / hosted collaboration | Obvious "if this becomes a product" feature. | Explicitly out of scope for v1 in `PROJECT.md` ("Hosting, accounts, multi-user, upload plumbing... deferred deliberately"). Building it now adds auth, sync, and conflict-resolution surface area with zero v1 users to validate it against. | Single machine, supervised video-call testing, as already decided. |
| Lettering / translation / OCR pipeline creep | The bubble/SFX detector ecosystem surveyed above is dominated by translation tools (BallonsTranslator, manga-ocr) — it's tempting to add OCR/translation since the models overlap. | `PROJECT.md` explicitly rules out "text rendering, lettering, translation" as never in scope. The overlap in tooling is coincidental (both problems need bubble detection), not a signal to merge the products. | Use bubble/text detection strictly for masking; do not add OCR or translation. |
| Freeform point-based / hint-stroke painting before every proposal (MangaNinjia/Cobra-hint style) | Both surveyed proposer models (Cobra's demo, MangaNinjia) expose this, and it looks like a natural power-user feature. | Adds a whole new interaction surface and per-region hint bookkeeping before v1's core loop (propose → snap → triage → correct) has even been validated on a real page. | Defer to Tier 2/3; revisit only if CIELAB-snap-and-triage alone leaves too many regions ambiguous in practice. |

---

## Feature Dependencies

```
Persistent project + palette data model (validated)
    └──requires──> Swatch-image upload → palette entries
                       └──enhances──> Character-sheet palette proposal (accept/reject/edit)
                       └──requires──> Manual palette entry add/edit

Panel polygon detection (existing, unvalidated on diagonal/open panels)
    └──requires──> Panel polygon editor (drag/add/delete vertices, draw-from-scratch)
                       └──required-by──> Protected bubble/SFX masking (needs a panel-local coordinate space)
                       └──required-by──> Zone segmentation (regions are addressed per-panel)

Protected bubble/SFX masking
    ├──enhanced-by──> Off-the-shelf detector (ogkalu comic-text-and-bubble-detector)
    └──requires (guaranteed fallback)──> Manual masking tool
    [relying on the detector alone CONFLICTS with the "guaranteed fallback" Key Decision]

Zone segmentation (existing)
    └──requires──> Zone click-merge
    └──requires──> Zone trace-split (label-map-only mutation)

Cobra colour proposal
    └──requires──> Per-region mode extraction
                       └──requires──> CIELAB snap to palette (reject-before-snap)
                                          └──requires──> Confidence triage (3-seed variance)
                                                             └──requires──> Colour-correction view (one-click reassignment)
                                                                                └──requires──> PSD export (3 granularities)

Metrics instrumentation ──must exist from day one, cannot be retrofitted into any of the above
```

### Dependency Notes

- **Panel polygon editor requires panel polygon detection:** editing needs
  something to start from, even if the detector is wrong on open/diagonal panels
  — the editor exists precisely because the detector is known to be incomplete.
- **Protected masking requires the panel coordinate space:** bubble/SFX masks are
  scoped per panel in the data model (`ProtectedMask.panel_id`), so panel
  boundaries must be settled (or at least editable) before masking makes sense.
- **Relying on the off-the-shelf detector conflicts with the guaranteed-fallback
  decision:** the shortlist above shows no candidate validated across this
  project's full style range — treating the detector as sufficient on its own
  would contradict the Key Decision that manual masking is guaranteed, not
  optional.
- **CIELAB snap requires mode extraction, which requires a colour proposal:** the
  whole colour pipeline is a strict chain — there is no shortcut from "Cobra
  runs" to "colour-correction view" that skips snapping or triage without
  reintroducing the silent-wrong-colour risk the spec explicitly warns against.
- **Confidence triage enhances but does not gate export:** in principle a
  colourist could export without reviewing flagged zones, but doing so defeats
  the project's own value proposition and metric (post-correction minutes/page)
  — triage should be presented as expected practice, not a hard technical gate.

---

## MVP Definition

### Launch With (v1)

This mirrors the Active requirements already scoped in `PROJECT.md`; restated here
with the research rationale attached.

- [ ] Persistent project with cross-page palette accrual — validated as table
      stakes by FlatMagic's F7 Load Swatch feature
- [ ] Swatch-image upload → palette entries — matches actual pre-production
      practice (a prepared colour board per project)
- [ ] Character-sheet palette proposal with accept/reject/edit — a proposal
      layer, never authoritative
- [ ] Manual palette entry add/edit/name — baseline correction path
- [ ] Panel polygon detection + full editing (drag/add/delete/draw-from-scratch)
      — the editable boundary *is* the answer to "panel segmentation isn't
      solved," not a better detector
- [ ] Protected bubble/SFX masking (detector-assisted, manual-guaranteed) — see
      shortlist; integrate `ogkalu/comic-text-and-bubble-detector` boxes against
      existing region segmentation, keep manual masking first-class
- [ ] Zone click-merge and trace-split — CVAT/FlatMagic-precedented cheap
      gestures
- [ ] Cobra colour proposal, never shown raw to the artist — avoids the
      VAE-roundtrip artifacts that are the documented reason research demos
      haven't displaced hand-flatting
- [ ] Per-region mode extraction + CIELAB snap with reject-before-snap — the
      professional "flat consistency" bar, plus the "silent wrong snap is worse
      than nothing" principle
- [ ] Confidence triage over 3 seeds — converts first-pass saving into
      *measured* post-correction saving
- [ ] One-click colour reassignment in colour-correction view — the cheapest
      possible correction gesture, matches FlatMagic's F1/F2
- [ ] PSD export, 3 granularities, one group per panel — the literal deliverable,
      confirmed against a working colourist's actual practice
- [ ] Metrics instrumentation from day one — cannot be retrofitted per spec §5

### Add After Validation (v1.x)

- [ ] Colour-hint painting before a Cobra run (Cobra's own demo already exposes
      hint mask/hint colour) — add only if triage-and-snap alone leaves too many
      regions ambiguous on real pages
- [ ] A dedicated Franco-Belgian-tuned bubble/SFX detector fine-tune — add only
      if the off-the-shelf detector's precision on Franco-Belgian/ligne
      claire/thick-line pages proves materially worse than on manga pages (a
      cheap benchmark against the existing four style-regime pages would confirm
      this before committing to a fine-tune)
- [ ] Shadow-mask layer (Tier 2 per spec) — a discardable, per-pixel deviation
      layer, only once flats themselves are validated as reliable

### Future Consideration (v2+)

- [ ] Cross-page character identity propagation — deliberately deferred; hard
      research problem, high risk of silent misassignment
- [ ] Point-based hint control (MangaNinjia-style) — a stronger but heavier
      interaction model than v1 needs
- [ ] American comics adapter, hatching adapter — both explicitly deferred in
      `PROJECT.md`, needing a retrained extractor / genuine research respectively

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---|---|---|---|
| Panel polygon editor | HIGH | MEDIUM-HIGH | P1 |
| Protected bubble/SFX masking (detector + manual fallback) | HIGH | MEDIUM | P1 |
| Zone click-merge / trace-split | HIGH | MEDIUM | P1 |
| CIELAB snap with reject-before-snap | HIGH | MEDIUM | P1 |
| Confidence triage | HIGH | MEDIUM | P1 |
| One-click colour reassignment | HIGH | LOW | P1 |
| PSD export (3 granularities) | HIGH | LOW-MEDIUM | P1 |
| Persistent palette + swatch upload | HIGH | LOW-MEDIUM | P1 |
| Character-sheet palette proposal | MEDIUM | MEDIUM | P1 (as a proposal layer, not gating) |
| Metrics instrumentation | MEDIUM (invisible to artist, critical to project) | LOW | P1 |
| Colour-hint painting pre-proposal | MEDIUM | MEDIUM | P2 |
| Franco-Belgian-tuned detector fine-tune | MEDIUM | HIGH | P2 (conditional on benchmark) |
| Shadow-mask layer | MEDIUM | MEDIUM | P2 |
| Cross-page identity propagation | LOW-MEDIUM (high risk if wrong) | HIGH | P3 |
| Point-based hint control | LOW (v1), MEDIUM (later) | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Clip Studio Paint | Krita (LazyBrush) | FlatMagic | Petalica Paint | ComicColor's approach |
|---|---|---|---|---|---|
| Boundary source | Manual reference-layer fill | Hint-stroke graph-cut (approximate) | Neural redraw + trapped-ball post-process | Fully learned, opaque | Exact trapped-ball (LineFiller), deterministic |
| Colour proposal | Optional, opaque "Colorize" | None (manual stroke colour) | None (manual bucket per region) | Fully automatic, opaque | Cobra proposer, never shown raw; snapped to palette |
| Intermediate stage visibility | None for AI Colorize | Stroke layer only | Full — neural lines + region overlay, togglable | None | Full — every stage is an inspectable layer (core thesis) |
| Palette persistence across pages | Manual, per-document | None built-in | JSON swatch file (F7) | None | Persistent, versioned, palette-entry-referenced (never baked RGB) |
| Region merge/split | Manual redraw of line art | Re-stroke and re-update | Bucket-click (F1/F2) + Tweak-draw (F3) | Not applicable | Click-merge + trace-split, label-map-only |
| Confidence signal on AI output | None | None | None | None | 3-seed variance-based triage — no surveyed competitor has this |
| Bubble/SFX protection | Manual only | Not applicable | Not addressed | Not applicable | Detector-assisted (Apache-2.0 RT-DETR-v2), manual-guaranteed |

## Sources

- Yan, Chung, Yoon, Gingold, Adar, Hong. **FlatMagic: Improving Flat Colorization
  through AI-driven Design for Digital Comic Professionals.** CHI 2022.
  `https://johnr0.github.io/assets/publications/CHI2022-flatmagic.pdf` (read
  directly, HIGH confidence — primary source for the workflow study, F1-F7
  feature set, and quantitative results throughout this document)
- Sýkora et al. **LazyBrush.** Eurographics 2009 (cited within FlatMagic; MEDIUM
  confidence, not read directly)
- Clip Studio Paint official user guide and tips articles on reference layers,
  fill tool modes, and Colorize (Technology Preview) —
  `help.clip-studio.com`, `tips.clip-studio.com`, `clip-studio.com` (MEDIUM
  confidence, official docs)
- Krita official manual, Colorize Mask — `docs.krita.org` (MEDIUM confidence,
  official docs)
- `zhuang2002/Cobra` (SIGGRAPH 2025) GitHub repo and demo `app.py` (HIGH
  confidence, primary source already cited in `flatting-pipeline-spec.md`)
- `ali-vilab/MangaNinjia` (CVPR 2025 Highlight) GitHub repo and CVPR paper
  (HIGH confidence)
- Petalica Paint discontinuation — multiple third-party tool-status pages
  (MEDIUM confidence on the fact of discontinuation, LOW confidence on causal
  attribution to professional rejection)
- `ogkalu/comic-text-and-bubble-detector`, `ogkalu/comic-speech-bubble-detector-yolov8m`,
  `ogkalu/comic-text-segmenter-yolov8m` — Hugging Face model cards (MEDIUM-HIGH
  confidence, official model cards)
- `ShadowB/Manga109-panel-balloon-text-yolov26-segmentation` — Hugging Face
  model card, including accuracy metrics (MEDIUM-HIGH confidence)
- `kitsumed/yolov8m_seg-speech-bubble` — Hugging Face model card (MEDIUM
  confidence)
- `dmMaze/comic-text-detector`, `dmMaze/BallonsTranslator` — GitHub repos and
  READMEs (MEDIUM confidence)
- `ragavsachdeva/magi` (v1/v2/v3, "The Manga Whisperer" CVPR 2024, "Tails Tell
  Tales" ACCV 2024) — GitHub repo and Hugging Face licence text (HIGH
  confidence on licence terms, directly quoted)
- Manga109 / Manga109-s licence terms — `manga109.github.io`, arXiv:2005.04425
  (MEDIUM confidence, third-party summary of licence conditions, not the
  original licence text)
- eBDtheque — `ebdtheque.univ-lr.fr`, IAPR TC10 (LOW confidence on
  redistribution/commercial-ML terms — flagged as needing direct verification,
  not stated as fact)
- CVAT changelog and docs on Join/Slice tools —
  `cvat.ai/resources/changelog`, `docs.cvat.ai` (MEDIUM-HIGH confidence,
  official docs)
- WebSearch coverage on 2024-2026 AI-art industry backlash (Comic-Con AI-art
  ban, DC Comics statement) — multiple news sources (MEDIUM confidence,
  context/colour rather than a load-bearing product claim)

---
*Feature research for: comic/manga colour flatting application, professional colourists*
*Researched: 2026-08-02*
