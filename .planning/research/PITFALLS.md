# Pitfalls Research

**Domain:** Comic/manga flatting application layer (interactive editors, diffusion colour proposer integration, CIELAB palette snapping, PSD export, metrics) built on top of an already-validated deterministic segmentation core.
**Researched:** 2026-08-02
**Confidence:** MEDIUM-HIGH overall — architecture-level claims (VAE drift, PSD limits, AA halo, evaluation bias) are corroborated by official specs and peer-reviewed/HCI sources; a few numeric thresholds (exact deltaE cutoffs, exact layer-count breakpoints) are MEDIUM/LOW and flagged individually.

This file is scoped to mistakes not yet made — the application layer (editors, diffusion integration, snapping, export, metrics) that sits on top of the validated `LineFiller`/segmentation core. It does not restate `.planning/codebase/CONCERNS.md`.

---

## Critical Pitfalls

### Pitfall 1: Treating the diffusion raster as anything other than a mode-extraction source

**What goes wrong:**
Any code path that samples individual pixels from the Cobra output raster (rather than aggregating a whole region into one mode colour) will pick up VAE artifacts as if they were intended colour: local gradients, hue drift toward blue/desaturated tones, and colour differences between two visually-identical regions that should be identical for identity purposes (e.g., a character's shirt in panel 2 landing at a slightly different hue than panel 1 with no colour-table difference to explain it).

**Why it happens:**
Latent-diffusion VAE decoders are documented to introduce color shift as one of a taxonomy of five recurring artifact types (color shift, grid patterns, blur, corner artifacts, droplet artifacts), and the shift compounds under iterative/repeated encode-decode passes — exactly the "downscale line art → run diffusion → read colour back" round trip this pipeline performs once per panel, and potentially more than once if a panel is re-run with different hints. Separately, image-editing/inpainting literature documents color-inconsistency between generated and surrounding regions as a general failure of latent diffusion models. This is architecture, not a Cobra-specific bug — it is the reason the spec's central claim ("diffusion output is never the deliverable") is correct, and it is also a reason to distrust *any* single-pixel read, not just naive ones. (MEDIUM confidence — corroborated by VAE-artifact taxonomy papers and inpainting color-consistency literature; exact magnitude in Cobra specifically is unverified — no public deltaE numbers found for Cobra.)

**How to avoid:**
- Never read a pixel value directly from the proposal raster anywhere in the codebase — enforce "mode extraction is the only read path" as a lint-level invariant (one function, one call site, tested).
- Extract the mode over the *entire* region mask, not a cropped bounding box or a sampled subset — a bounding-box sample will straddle a boundary and pick up edge-adjacent drift (see Pitfall 2).
- Treat regions that come back with high spread within their own mode bin (i.e., the "coarse bin" the mode falls into is wide, or the top bin's share of the region is low) as symptomatic of VAE noise, not real bimodal shading — this is a different signal than the seed-variance confidence triage in §1.8, and both should probably exist. A region with low top-bin share is a segmentation/extraction health check; high seed-to-seed variance is a triage-for-review check. Conflating them will make the triage metric noisy.
- When re-running a panel (new hint, corrected reference), never diff the new proposal raster against the old one pixel-for-pixel to decide "did this change" — diff post-snap palette IDs instead. Raw raster diffs will show phantom differences purely from a different VAE decode, even with an unchanged hint.

**Warning signs:**
- Two structurally identical regions (verified same palette entry visually) get different mode colours from the same panel on repeated runs with no hint change.
- Confidence-triage "high variance" regions cluster near panel edges or near thin corridors rather than near genuinely ambiguous semantic content (shadow/highlight boundaries) — that pattern says decode noise, not model uncertainty.
- Region colours drift by small deltaE (a handful of units) between two panels that reference-locking should have made identical.

**Phase to address:**
Diffusion integration phase (spec §1.6, Cobra wrapping) and the mode-extraction/snapping phase (spec §1.7) together — the mode-extraction function is the enforcement point, so it should be built and unit-tested (synthetic proposal rasters with injected per-pixel gradient noise → assert stable mode) before real Cobra output is wired in.

---

### Pitfall 2: Reading region colour at the label-map's true boundary instead of its eroded interior

**What goes wrong:**
The label map from `LineFiller` is exact and boundary-tight against the (closed) line art. The diffusion proposal raster, in contrast, is generated and decoded through a VAE at 384–512px and is not obliged to respect that boundary — colour bleeds across it, and the effect is worst exactly at thin corridors and small regions, which this project's own segmentation is already known to produce in quantity (structural counts of 68–87 per page, many of them thin). If mode extraction samples the full region mask including the 1–3px nearest the boundary, a meaningful fraction of a small region's pixels can be contaminated by the neighbouring region's colour bleeding across the (correctly placed) label boundary — pulling the mode toward an average of two colours, or in the worst case flipping which bin is "largest."

**Why it happens:**
This is the same VAE-bleed phenomenon as Pitfall 1 but stated as a boundary-geometry problem instead of a raster-fidelity problem: the label map is drawn from line art at full resolution; the proposal raster is decoded from a 384–512px latent and necessarily has soft, low-frequency boundaries after upsampling back to full resolution. Two different coordinate-precision regimes are being composited, and the seam is exactly where flatting quality is judged.

**How to avoid:**
- Erode each region mask by a small margin (a few pixels, tuned empirically per the panel's working resolution) before mode extraction, and only fall back to the full mask if the eroded mask goes empty (this will happen on genuinely thin regions — log it, since a region too thin to erode is also a region likely to be an artifact of the segmenter, not real content).
- Weight the mode histogram by distance-to-boundary (interior pixels count more) rather than a hard erosion cutoff, if erosion proves too lossy on already-thin regions — cheaper to implement as a first pass, but erosion is more defensible and testable.
- Test explicitly on thin-corridor regions from the Moebius-style hatching-adjacent pages already in the report set — these are exactly the regions where this failure mode will show up first, since the segmentation core is already validated against them.

**Warning signs:**
- Small/thin regions systematically snap to a colour "between" their two neighbours' palette entries rather than either neighbour's actual colour.
- Confidence-triage variance correlates with region area (smaller = more variance) more than with genuine semantic ambiguity — that correlation is the boundary-bleed signature, not model uncertainty.

**Phase to address:**
Mode-extraction/snapping phase (spec §1.7). This should be validated with a synthetic test: render a two-colour proposal raster with a soft gradient at a label-map boundary and confirm mode extraction on each side returns the correct colour, not an average.

---

### Pitfall 3: Flats fringing or haloing under anti-aliased line art at export/composite time

**What goes wrong:**
When a flat colour layer is composited under an anti-aliased ink layer at full working resolution, the boundary pixels of the ink layer are semi-transparent blends of ink-colour and background. If the flat fill stops exactly at the *opaque* extent of the line (the naive case, and the case a single-resolution label map produces), a thin ring of background/canvas colour shows through the AA fringe of the line — the "halo" the spec's §10 explicitly calls out. Artists doing this by hand already know to paint "far enough under the line" to avoid it; a pipeline that only fills to the pixel-exact line boundary reproduces the amateur mistake by construction.

**Why it happens:**
Trapped-ball / flood-fill segmentation is run against a *binarized* or thresholded line raster (opaque vs not), which discards the AA gradient information entirely. The label map is therefore always slightly smaller than the ink's true visual footprint. Community sources (Krita's own flat-coloring documentation, deviantArt inking/coloring discussions) confirm this is the standard, well-known failure and the standard fix: work at higher resolution than final output (2–4×) and downsample, and/or explicitly extend flat fills a pixel or two under the line before compositing. (MEDIUM confidence — corroborated by Krita's official flat-coloring tutorial and independent artist-community discussion; this is a well-established craft practice, not a single source's opinion.)

**How to avoid:**
- Confirm segmentation and label-map generation already runs at a resolution where this is a non-issue (spec notes segmentation is exact/deterministic against the closed line raster — the open question is what happens at the *composite* step at export, not inside segmentation itself). If flats are generated/label-mapped at native page resolution (spec implies pages are ~3500×5000px per the codebase concerns) and only the diffusion proposal runs at 384–512px, the segmentation-side resolution is probably already adequate — the risk is specifically at PSD compositing, not at region extraction.
- At export, dilate each flat-colour fill by a small margin (matching or slightly exceeding the ink layer's AA fringe width) before writing the flat layer, so the flat colour extends slightly under the ink rather than stopping at its opaque core. This is the deterministic equivalent of "paint far enough under the line."
- Test with a real AA line art page (not a binarized/idealized one) and zoom to 400%+ on a curve to visually inspect for background showing through the ink's semi-transparent fringe.
- Do not solve this by anti-aliasing the flat layer's own edges to match the line — that reintroduces exactly the soft, non-exhaustive boundary problem the label map is designed to avoid. Extend the flat under the opaque line instead; let the ink layer's own transparency do the blending on top.

**Warning signs:**
- Zoomed-in visual QA on any curved or diagonal line shows a thin light/background-coloured ring between ink and flat.
- Studio colourist feedback specifically uses the word "halo" or "fringing" (the spec already anticipates this vocabulary from FlatMagic-adjacent literature).

**Phase to address:**
Layered export phase (spec §1.10) — this is a compositing/export-time concern, not a segmentation-time one, so it belongs with PSD export work, verified against a page with genuinely soft (non-binarized) ink.

---

### Pitfall 4: PSD group/layer structure that Photoshop opens cleanly but Clip Studio mangles, or vice versa

**What goes wrong:**
"PSD in, PSD out" does not mean "identical fidelity in both apps." Clip Studio's own support documentation acknowledges concrete, specific breakage on import: layers that are transparency-locked *and* inside a group can become hidden or erased on open; Photoshop layer *effects* (any blending styles) are dropped entirely and CSP recommends rasterizing before export specifically because effects don't survive; and CSP explicitly changes any layer type it doesn't understand (3D layers, PS-specific border/frame layers, "layer color" tags) into flattened raster layers rather than failing loudly. (HIGH confidence — sourced directly from Clip Studio's own official support articles, not third-party speculation.) This is a real, asymmetric risk given the project's stated goal of "one export path serves both apps" (spec §2.3) — the assumption should be tested, not assumed.

**Why it happens:**
PSD is Adobe's format; CSP's PSD *importer* is a best-effort compatibility layer, not a native implementation, and does not claim full fidelity for anything beyond flat raster/group structure and basic pixel layers. Any export path that leans on PS-specific features (blending modes beyond normal, adjustment layers, layer effects, locked transparency inside groups) is at risk the moment a colourist opens the file in CSP instead of Photoshop.

**How to avoid:**
- Keep the exported layer structure deliberately minimal: plain raster layers in plain groups, normal blend mode, no locked transparency flags on layers inside groups, no layer effects/styles. The spec's own decided structure (group per panel, raster layer per colour or per zone) is already inside this safe subset — the risk is scope creep during implementation (e.g., adding a lock-transparency flag as a "convenience" for the colourist, or an adjustment layer for a shadow pass in Tier 2).
- Round-trip test every export against *both* applications as a release gate, not just Photoshop, since Photoshop is more likely to be the developer's own daily tool and CSP regressions will otherwise go unnoticed until a professional colourist (the actual user) hits them.
- If Tier 2's shadow-mask layer (spec §6) is ever implemented as a blend-mode layer (e.g., Multiply) rather than a plain raster layer, treat that as a specific, separate compatibility test — blend modes are exactly the kind of feature with the most cross-app divergence risk.

**Warning signs:**
- Export testing only ever happens in Photoshop (the more common developer default) and never in Clip Studio.
- Any export code path sets a Photoshop-specific flag (transparency lock, layer effect, adjustment layer, clipping mask) "to make the file nicer to work with."

**Phase to address:**
Layered export phase (spec §1.10). Add explicit dual-app round-trip verification to that phase's definition of done — not just "PSD opens," but "PSD opens with identical layer/group structure in both."

---

### Pitfall 5: PSD size/count limits silently hit at realistic page/palette scale

**What goes wrong:**
PSD (not PSB) caps out at 30,000px per dimension and roughly 2GB file size (HIGH confidence — this is Adobe's documented format limit, corroborated across multiple independent format-reference sources). Studio pages are typically much smaller than 30,000px (the codebase concerns doc estimates ~3500×5000px at 300dpi), so the *dimension* cap is unlikely to bite directly — but the combination of full-resolution art, a full alpha-channel protected-mask layer, and a "layer per zone" export granularity (which can run into the hundreds of regions per panel across many panels, per the segmentation core's own measured counts of up to ~600 raw regions on hatching-heavy pages) can plausibly approach the file-size ceiling well before any artist expects it, especially if 16-bit is used per layer. Layer *count* itself has no hard documented spec limit, but Photoshop's practical layer budget is reported around thousands before performance degrades (one reported case: sluggishness at ~4,400 layers with 24GB RAM) — well within reach if "layer per zone" (not the default "layer per colour") is chosen on a page with many panels and a hatching-adjacent page's true region count. (MEDIUM confidence on the practical-degradation number — single community report, not an official spec, but directionally consistent with "large layer counts degrade performance" being common knowledge among Photoshop power users.)

**How to avoid:**
- Compute projected file size and layer count *before* export, using each panel's actual region/colour count, and warn (or auto-switch to PSB, or auto-recommend "per colour" over "per zone") before the artist waits through a failed or bloated export.
- Treat "layer per zone" as the risky option it is by design — the spec already frames it as an option, not the default, for exactly this reason (the default is "layer per colour," which per spec's own estimate lands around ~100 layers per page — safely inside normal studio-file territory). Document clearly, in the export UI, that "per zone" scales with segmentation region count, which the project already knows can spike into the hundreds on hatching-dense pages (§2.2's own numbers: 612 raw regions on Moebius).
- Switch to PSB automatically (or refuse export with a clear message) if projected size exceeds a safety margin under 2GB, rather than producing a file that appears to export successfully but that Photoshop or CSP then fails to open or opens corrupted.
- Confirm bit depth choice deliberately: 8-bit is very likely sufficient for flat colour (no gradients by construction — flats are literally uniform-fill regions), and using 16-bit "for safety" roughly doubles per-layer size for no quality benefit here, unlike the Tier 2 shadow-mask layer where 16-bit precision on a gradient might actually matter.

**Warning signs:**
- Export succeeds but the resulting file is reported as corrupted, slow to open, or missing layers in either target app.
- No pre-export size/count estimate exists in the code, so the first time this is discovered is when an artist's actual hatching-heavy page (already known to produce ~600 regions) hits "per zone" export.

**Phase to address:**
Layered export phase (spec §1.10) — build the pre-export size/layer estimator alongside the three granularity options, since the option that's riskiest ("per zone") is being built at the same time.

---

### Pitfall 6: Unassigned/leaked pixels from LineFiller's known exhaustiveness defect silently reaching export

**What goes wrong:**
The spec already documents `merge_fill`'s known defect: coverage measured at 0.997 on Moebius (i.e., ~0.3% of pixels belong to no region), 1.000 on the other three test pages. If export code (or the colour-correction view) simply iterates over known regions and paints them, unassigned pixels are left as whatever the canvas default is — likely transparent or black — which in a *flat* colour layer reads as a small hole or dark speckle exactly where texture density was highest (per the correlation the spec notes between coverage loss and texture density). This is the kind of defect that is invisible in a full-page preview but visible the moment a colourist zooms in on a heavily-inked area, which is precisely where they are most likely to be paying close attention.

**Why it happens:**
This is a genuine, uncharacterized-fix defect in a vendored, MIT-licensed dependency (`LineFiller`), not something this project's application layer created — but the application layer is exactly where it either gets surfaced and handled, or silently ships to the artist. Since the defect scales with texture density, it will not show up on the manga/ligne-claire test pages that already validated cleanly at 1.000 coverage — it is specifically a hatching-adjacent-page problem, and the roadmap should not assume the four already-validated pages represent the defect's full range.

**How to avoid:**
- Decide explicitly, at the data-model/editor level, what an "unassigned" pixel *is*: not a region with a null palette entry (that already has a meaning — flagged/new colour), but a genuinely separate state, since conflating "unassigned by the segmenter" with "flagged as a new colour by the snapper" would corrupt the flagged-region-precision metric (spec §5) by mixing two unrelated causes into one bucket.
- At export, either (a) assign unassigned pixels to their nearest neighbouring region by simple morphological dilation/nearest-label fill before the label map is considered final, or (b) render them as a highlighted "gap" layer/overlay in the editor so the artist can 1-click-assign them, consistent with the project's stated philosophy that every machine mistake should be one click to fix. Silently leaving them as transparent holes in the exported flats layer is the one option that violates that philosophy outright and should be treated as a defect, not a default.
- Make coverage-below-1.0 a per-panel, per-page visible metric in the editor (not just a report artifact like the current `reports/p3` output), since the whole point of the invariant in §3 ("mutually exclusive and exhaustive") is that violations should be visible to the person who can fix them, not just to the engineer running an eval script.
- Do not attempt to "fix" `merge_fill` itself as part of the application-layer work — the spec explicitly frames it as "bounded and characterized, not yet fixed," and the application layer's job is to handle its output gracefully, not to patch a vendored algorithm mid-milestone.

**Warning signs:**
- Exported flats show dark/transparent speckling concentrated in high-detail/hatching-adjacent areas.
- The exhaustiveness invariant from §3 has no runtime check anywhere in the editor or export path — if coverage is only ever measured in a spike script and never in the production code path, this will regress silently as new test pages are added.

**Phase to address:**
Zone editor phase (spec §1.9, merge/split) is the natural home for surfacing and one-click-fixing gaps, and the export phase (spec §1.10) is where a hard gate ("do not export with >X% unassigned pixels without artist acknowledgement") belongs.

---

### Pitfall 7: Coordinate-space and hit-testing bugs between the displayed (possibly zoomed/scaled) image and the underlying label map

**What goes wrong:**
The editor displays a page at some on-screen scale (fit-to-window, or an artist-controlled zoom) that is virtually never 1:1 with the underlying full-resolution label map. Any click-to-select, click-to-merge, or freehand-stroke-to-split interaction that maps screen coordinates back to label-map coordinates is a classic source of off-by-one and rounding bugs: a click that lands one screen-pixel from a boundary maps, after scale-and-round, to the wrong region entirely at high zoom-out ratios, and a freehand stroke drawn at a coarse on-screen resolution and then upscaled to label-map resolution either fails to fully close a cut (leaving a leak that lets a merge/split bleed into an unintended neighbour) or overshoots and eats a sliver of an unrelated region.

**Why it happens:**
This class of bug is domain-general (any zoomable-canvas editor faces it), but it is unusually consequential here specifically because the region label map is the ground truth for the data model's core invariant (mutual exclusivity/exhaustiveness, §3) — a coordinate bug elsewhere in a typical app degrades UX; here it can silently corrupt the very structure the whole product's value proposition depends on (one-click colour correction requires that clicking on what looks like "the shirt" actually selects the shirt's region, every time, at every zoom level).

**How to avoid:**
- Keep exactly one coordinate transform function (screen ↔ label-map), unit-tested independently of any rendering code, and route every interaction through it — do not let hit-testing and stroke-rasterization implement their own ad hoc scaling.
- Do hit-testing and freehand-stroke rasterization directly against the full-resolution label map (transform the input point/stroke *up* to full resolution before testing), never against a downsampled on-screen bitmap — the downsampled bitmap is a rendering convenience, not a data structure to reason against.
- For freehand split strokes specifically: rasterize the stroke at full label-map resolution with a minimum stroke width in label-map pixels (not screen pixels), and explicitly close the stroke to the panel/region boundary at both ends before using it as a cut — an open stroke that doesn't reach a boundary produces a cut that doesn't actually separate two exhaustive sub-regions, silently reintroducing a §3 violation identical in kind to Pitfall 6's.
- Test at extreme zoom ratios deliberately (both far zoomed out, where sub-pixel screen movement crosses many label-map pixels, and far zoomed in, where a single screen pixel is many label-map pixels) — bugs at the two extremes are different (aliasing vs precision) and a mid-zoom-only test suite will miss both.

**Warning signs:**
- Bug reports of the form "I clicked on X but it selected the region next to it" that only reproduce at specific zoom levels.
- A split operation that "looks closed" on screen but leaves a hairline gap that a subsequent coverage check reveals as unassigned pixels — this is the interactive-editor version of Pitfall 6's failure, produced by the artist's own tool rather than the segmenter.

**Phase to address:**
Zone editor phase (spec §1.9) and the panel-polygon editor (Active requirement: "artist can drag, add and delete vertices") both need this coordinate-transform layer built once and shared, not reimplemented per editing surface — build it as a small, independently-tested module before either editor's interaction code.

---

### Pitfall 8: Undo/redo over a label map that silently permits an invalid intermediate or final state

**What goes wrong:**
Undo/redo implementations for raster/label-map data commonly work by snapshotting or diffing whole-map states (this is in fact the documented approach in comparable tools — 3D Slicer's segment editor saves the full segmentation state before each effect and caps history at a fixed depth). A naive command-pattern undo/redo built for this project could instead try to invert individual operations (un-merge, un-split) rather than snapshot state, and an inverted merge/split is not guaranteed to reconstruct the exact prior label assignment if the forward operation was lossy (e.g., a merge that also silently fixed some unassigned pixels per Pitfall 6, or a split whose freehand stroke was regularized/smoothed before being applied) — the redo path can then diverge from what the artist actually saw, or worse, land in a state that violates exclusivity/exhaustiveness because the "inverse" operation was approximated rather than exact.

**Why it happens:**
Snapshotting full label maps is simple and correct but memory-heavy at full page resolution across a long edit history; inverting individual operations is memory-cheap but requires every forward operation to be exactly, losslessly invertible, which is a much stronger engineering requirement than it initially appears, especially once operations start interacting with the unassigned-pixel handling from Pitfall 6.

**How to avoid:**
- Default to whole-label-map snapshotting for undo/redo (matching the precedent above), accepting the memory cost, and only optimize to diffs/deltas later if profiling shows it's actually a problem at real page sizes — do not build the diff-based version first on a "premature optimization" instinct, since correctness of the core invariant matters more here than in most editors.
- Cap undo history depth deliberately and make the cap visible to the artist (a silently-dropped-oldest-undo-state is confusing; a labeled "undo history: 20 steps" is not).
- Whatever the mechanism, add an invariant check (regions within a panel mutually exclusive and exhaustive minus protected masks, per §3) that runs after every undo/redo transition in development/test builds, and fail loudly if violated — this is cheap insurance against exactly the "approximated inverse" failure mode above, and doubles as a regression check against Pitfall 6 recurring through a different code path.
- Persist undo state to disk incrementally rather than only in memory, given Pitfall 12 below (browser refresh/crash) — an in-memory-only undo stack that's also the only record of an artist's edits is a double point of failure.

**Warning signs:**
- Redo-after-undo ever produces a visibly different result than what was undone (even subtly, e.g., a slightly different boundary after an undo-redo round trip on a split).
- No automated test exercises "merge, undo, redo, split, undo" as a sequence and checks the final label map against an expected exact state.

**Phase to address:**
Zone editor phase (spec §1.9). Build the invariant-check assertion alongside the first merge/split implementation, not after — it is far cheaper to catch a violating operation at the moment it's introduced than to debug a corrupted label map days later.

---

### Pitfall 9: CIELAB nearest-neighbour snapping without deliberate lightness downweighting confuses shadow and adjacent-hue regions

**What goes wrong:**
Raw Euclidean CIELAB distance (and even more so raw RGB distance) is dominated by lightness differences unless deliberately corrected, because human lightness sensitivity is non-uniform (small differences matter more in the mid-tones than at extremes) and CIE76/plain-Euclidean CIELAB does not model that. This is exactly why CIEDE2000 exists — it applies specific corrections (SL, SC, SH weighting functions) on top of raw CIELAB precisely to compensate for these known perceptual non-uniformities, lightness chief among them (MEDIUM-HIGH confidence — this is the CIE's own documented rationale for CIEDE2000's lightness-weighting fix, corroborated by multiple independent colour-science sources). In this project's specific case, a shadowed skin region and an unrelated darker adjacent tone (hair, a dark garment) can be closer in raw distance than shadowed skin is to its own base skin tone, because the shadow moves L* a lot while a/b (hue/chroma) barely move — the spec's own §1.7 pseudocode already asserts this ("shading moves L, not a/b") but the risk is in *how much* to downweight and whether it's tuned per-palette or hardcoded.

**How to avoid:**
- Do not hand-roll a "downweight L* by a flat 0.3 factor and use Euclidean distance" scheme without validating it against actual bimodal-shaded regions from real pages — the factor is a hypothesis (the spec proposes ~0.3), and it should be validated empirically against cases where shadow and an unrelated dark hue are both candidates, not assumed correct because it appears in the spec.
- Consider CIEDE2000 (or at minimum a weighted formula informed by it) rather than a single hand-tuned scalar on plain Euclidean CIELAB — CIEDE2000's lightness/chroma/hue weighting functions are specifically designed to fix the failure mode described here and are a well-studied, off-the-shelf improvement over ad hoc weighting (implementations exist in common colour libraries; this is not a research problem to solve from scratch).
- Whatever distance formula is chosen, build a small labelled test set from real project pages specifically containing the known-hard cases the spec already calls out in §10 (shadow-side skin vs. hair where the reference is genuinely ambiguous) and use it as a regression suite for the snapping function — this is cheap because the palette-entry ground truth already exists once an artist has colour-corrected a page once.

**Warning signs:**
- Snapping accuracy (measured against artist corrections, once instrumented per Pitfall 10) is systematically worse on regions the artist marks as "shadow" or "shaded" than on base-tone regions.
- Two palette entries that are visually very different in hue but similar in lightness get confused by the snapper more often than two entries that are visually similar in hue but different in lightness — that asymmetry is the signature of insufficient L* downweighting.

**Phase to address:**
Mode-extraction/CIELAB-snapping phase (spec §1.7). This is exactly the phase where the distance formula and its tuning are implemented — treat the L* downweight factor (or CIEDE2000 adoption) as a parameter to validate against real data, not a spec value to implement as given without checking.

---

### Pitfall 10: Reject threshold tuned wrong — either silently coercing new colours or flagging everything

**What goes wrong:**
The snapping step's reject threshold is a single scalar with an asymmetric cost structure: set too loose, a genuinely new colour (new outfit, unregistered prop, back-of-head skin the reference never showed) silently snaps to the nearest existing palette entry, and — critically, as the spec itself flags — the artist will very likely *not notice*, because a wrong-but-plausible colour reads as correct at a glance in a way an empty/flagged region does not. Set too tight, every minor rendering variance (including the VAE colour drift from Pitfall 1) trips the threshold and creates a flood of spurious flagged/new palette entries, which defeats the entire point of confidence triage (§1.8) by making "flagged" mean "everything," collapsing the hint-collapse metric's signal.

**Why it happens:**
A single global threshold is being asked to separate two very different populations — "this is genuinely the same colour, decoded slightly noisily" (should snap) vs. "this is genuinely a different colour that happens to be nearby in CIELAB" (should flag) — using only a distance measurement, with no other signal available to disambiguate them. This is inherently a precision/recall tradeoff, not a bug to eliminate, but the cost asymmetry (silent-wrong is worse than flagged-empty, per the spec's own explicit statement) means the threshold should be tuned conservatively (biased toward over-flagging) rather than symmetrically.

**How to avoid:**
- Do not pick the threshold once from a formula or a single test page and leave it static — instrument flagged-region precision (already in spec §5's metrics list) from day one specifically so the threshold can be tuned against real artist accept/reject decisions once volume accumulates, per the project's own metrics philosophy.
- Bias the threshold deliberately toward over-flagging rather than symmetric error, consistent with the spec's explicit statement that silent wrong-snapping is worse than an empty region — this is a case where "more artist clicks" is the safer failure mode, not a UX cost to be minimized in isolation.
- Consider the reject decision as depending on more than a single region's distance in isolation — e.g., a region's neighbourhood (is this region isolated or part of a larger colour-consistent area that already snapped confidently?) or its size (a single stray pixseudocode-scale region flagging as "new" is lower-stakes than a large, prominent region doing so) could inform whether the threshold should be adjusted per-case, though a single global threshold is a reasonable, defensible v1 starting point as long as it's instrumented and revisited.
- Watch specifically for the interaction with Pitfall 1 (VAE colour drift) — if the reject threshold is tuned against clean, non-drifted synthetic proposals and only tested against real Cobra output late, the threshold chosen in isolation will be wrong once real decode noise is present.

**Warning signs:**
- Flagged-region precision (spec §5's own metric) trends low (artist frequently accepts a flagged region as-is rather than genuinely correcting it, meaning it didn't need to be flagged) or trends toward "everything gets flagged" (threshold too tight) or toward artist-caught silent-wrong-snaps showing up as manual corrections in a pattern that should have been caught by triage (threshold too loose).
- The hint-collapse metric (§5) fails to trend downward across a volume even after many pages — an over-tight threshold defeats this metric by keeping flagged-region count high regardless of how much the palette has stabilized.

**Phase to address:**
Mode-extraction/CIELAB-snapping phase (spec §1.7) for the initial threshold and its instrumentation; the metrics-instrumentation work (spec §5) needs to exist early enough (first commit, per the spec's own instruction) that threshold-tuning has real data to tune against rather than being guessed once and never revisited.

---

### Pitfall 11: Treating "regions per panel" (or any single count) as a quality score rather than a health alarm

**What goes wrong:**
The project's own A/B evaluation already surfaced this concretely: cases existed where a *higher* region count read as visually better flatting, because what matters is where the boundaries fall, not how many there are (spec §1.4's own stated finding). If the metrics-instrumentation work (or, worse, the roadmap/success-criteria language for a future phase) treats "reduce regions per panel" as an optimization target in itself, it will optimize for the wrong thing — a merge-happy segmenter that collapses real, semantically-distinct zones into fewer regions would score well on this metric while producing worse flats.

**Why it happens:**
Counts are cheap to compute and instinctively feel like progress metrics ("fewer regions = simpler = better"), but the actual product metric — post-correction time — depends on whether boundaries are *correct*, which a count cannot distinguish from "collapsed." This is a generalizable trap in any segmentation-adjacent metric design, but the project has already been burned by exactly this reasoning once (the original P3 verdict was reversed specifically because it was measuring the segmenter's own artifact, not the art, per the spec's §2.2).

**How to avoid:**
- Keep "regions per panel" explicitly framed, in code comments, dashboards, and any roadmap success criteria, as an *alarm threshold* (flag pages/panels for visual review when count spikes far outside the observed viable range, ~68–87 structural per the existing P3/AB data) rather than a number to minimize.
- Never let a phase's "definition of done" cite a region-count target as a pass/fail criterion in isolation — pair it with a visual-review gate (as P3/AB already correctly did) whenever region count is used at all.
- Similarly guard "auto-accept rate" (spec §5) against the same trap in reverse: a very high auto-accept rate could mean the pipeline is genuinely good, or it could mean the confidence-triage threshold (Pitfall 10) is too loose and isn't flagging things it should — auto-accept rate alone cannot distinguish these, and should always be read alongside flagged-region precision, not in isolation.

**Warning signs:**
- Any roadmap phase or success criterion written as "reduce regions per panel to X" without an accompanying visual-quality check.
- A change that improves the region-count metric but that no one has visually reviewed on a real page.

**Phase to address:**
This is a metrics-design concern that should be settled once, early (spec's own instruction: instrument from the first commit), and then enforced as a review-process rule for every subsequent phase's success criteria — it isn't a single phase's problem to solve, but every phase's success criteria should be checked against it.

---

### Pitfall 12: Headlining first-pass time savings instead of post-correction time, overstating value the way prior auto-colourisation products have

**What goes wrong:**
The spec is explicit that post-correction minutes per page is "the only number worth quoting to a studio" and warns against carrying a headline "60% saved" figure. This is not a hypothetical concern — published auto-colourisation and auto-inbetweening work has documented exactly this overstatement pattern: research notes that measured speed for automatic colorization methods often does not reflect actual cost when segmentation/colour information has to be supplied in advance (i.e., the "savings" figure is measured only over the part of the workflow the tool automated, excluding the setup and correction labour still required), and animation-production accounts describe acceptable automatic colourisation as one that still requires meaningful manual correction time on every batch of frames, not "free" output. (MEDIUM confidence — corroborated across a research survey observation and a separate professional-workflow account describing the same shape of overstatement, though neither is Cobra-specific.)

**Why it happens:**
First-pass time is trivially easy to measure and looks impressive ("colourized a page in 8 seconds"), while post-correction time requires actually instrumenting the correction workflow and waiting for real usage data — the cheap, flattering number is always available first, and the expensive, honest number arrives late, creating organizational pressure to lead with the flattering one even when everyone agrees post-correction is what matters.

**How to avoid:**
- Instrument post-correction time from the very first real artist session (the spec already says this explicitly — "cannot be retrofitted") — this means the correction UI (colour-correction view, spec §1.9-adjacent) needs timing instrumentation built in from its first version, not added once the UI stabilizes.
- Never report or display a first-pass-only time/percentage figure anywhere the artist or a studio stakeholder will see it, even informally in a demo — if a number is going to anchor expectations, make it the honest one from the start, since anchoring is hard to walk back later (this is the FlatMagic lesson generalized: professionals' trust, once lost to an overstated or opaque claim, is expensive to rebuild).
- When reporting hint-collapse (hints required ÷ fillable regions, tracked across a volume, per §5), be explicit about what counts as a "hint" — if manual correction clicks in the colour-correction view aren't counted the same way flagged-region triage clicks are, the metric can be gamed by shifting correction burden from one UI surface to another without actually reducing total artist effort.

**Warning signs:**
- Any internal or demo report leads with a first-pass number ("processed in N seconds") rather than post-correction minutes.
- Post-correction timing instrumentation is added as an afterthought once the colour-correction UI already exists, rather than built into its first version — at that point, no baseline data exists for the sessions that already happened.

**Phase to address:**
Metrics-instrumentation work (spec §5) must land alongside — not after — the colour-correction view (an Active requirement) and the confidence-triage feature, since both are where "correction" actually happens and both need timing hooks from their first implementation.

---

## Moderate Pitfalls

### Pitfall 13: Serving full-resolution studio pages to a browser causes memory blowups per request

**What goes wrong:** Studio pages at ~3500×5000px are roughly tens of MB uncompressed per channel, and a browser canvas holding a full-resolution page plus a full-resolution label-map overlay plus an undo history (per Pitfall 8) can hit real memory ceilings — the codebase concerns already flag that `trapped_ball_segment()` has no memory-bounding tiling (unlike the line extractor's tile parameter), and the interactive editor is exactly where full-resolution arrays are most likely to be held client-side, repeatedly, across a session. Separately, browsers impose hard canvas limits regardless of available RAM — iOS Safari specifically caps around 4096×4096px and ~384MB of canvas memory on some versions, and even desktop browsers have per-canvas area limits well below what a naive "draw the label map as a canvas at native resolution" approach would need for a large page. (HIGH confidence on the browser canvas limits themselves — documented directly by browser engine sources; MEDIUM on how this specific project's memory pattern will behave, since that depends on implementation choices not yet made.)

**Why it happens:** The natural way to build an interactive per-pixel editor is "load the full image, draw it on a canvas, do pixel operations against it" — this works fine in local testing on a fast desktop with one page open, and breaks down exactly at the scale (real studio pages, multiple pages open across a session, long undo history) that only shows up once real artists are using it.

**How to avoid:** Decide the label-map representation strategy deliberately before building the editor: keep a compact label-index representation server-side (or in a worker) and only ever send/rasterize a *viewport-scoped* region to the browser canvas at the current zoom level, rather than holding a full-resolution RGBA canvas per label. Given the "local web app, single machine" constraint (v1 explicitly runs on one machine over video call), this is lower-stakes than it would be for a hosted multi-tenant product, but it is not zero-stakes — a crash mid-session on the one machine being used for a live demo is exactly the failure mode that would be most visible and costly to this project specifically.

**Phase to address:** Zone editor and panel editor phases (spec §1.9 and the panel-polygon requirement) — decide the client/server data-transfer boundary once, before either editor is built, so both share it.

---

### Pitfall 14: GPU OOM or silent queuing failures under concurrent Cobra jobs

**What goes wrong:** Diffusion inference workers do not share GPU memory across processes the way CPU memory can be shared copy-on-write — each concurrent job effectively needs its own memory footprint, and naive "just call Cobra per request" code will either OOM outright under any concurrency or silently serialize with no user feedback about why a second request is slow. (MEDIUM-HIGH confidence — this is well-documented general GPU-serving behaviour, though the project's stated "single machine, one artist" v1 scope substantially lowers the practical risk versus a multi-tenant deployment.)

**Why it happens:** V1 is explicitly single-user/single-machine (PROJECT.md Out of Scope), so true concurrent-job contention is unlikely in normal use — but it is easy to accidentally create anyway: an artist re-running a panel while a previous run hasn't finished, a background metrics/report job (like the existing `spike/ab.py`, already flagged as slow) running at the same time as an interactive session, or a naive retry-on-timeout path that fires a second job without cancelling the first.

**How to avoid:** Serialize Cobra invocations behind an explicit single-worker queue even in v1, rather than assuming "only one request will ever happen at once" as an implicit invariant nothing enforces — this is cheap insurance given the stated single-GPU, no-CPU-fallback constraint, and it turns a potential OOM crash during a live supervised demo into a visible "processing, please wait" state instead.

**Phase to address:** Diffusion-integration phase (spec §1.6) — build the queue/serialization as part of the initial Cobra wrapper, not as a later hardening pass.

---

### Pitfall 15: Losing artist edits to a browser refresh, tab close, or crash

**What goes wrong:** An artist's merge/split/colour-correction edits, if held only in browser memory or an in-progress client-side undo stack (per Pitfall 8), vanish on an accidental refresh, a crashed tab, or a browser update mid-session — in a live, supervised, single-session demo context (the explicit v1 testing model), this is a uniquely bad failure mode: there is no "come back tomorrow," the artist is watching, and a lost session directly damages the credibility of "every mistake is one click to fix" if that one click itself isn't safe from ordinary browser behaviour.

**Why it happens:** Persisting every edit incrementally is more implementation work than holding state in memory and saving "at the end" or "on demand" — the latter is a natural first-pass shortcut that works in every manual test the developer runs (who won't accidentally refresh) and fails in exactly the real-usage scenario it needs to survive.

**How to avoid:** Persist every meaningful edit (region reassignment, merge, split, palette edit) to the SQLite store immediately as it happens, not on an explicit "save" action or only at session end — the existing data model (spec §3) is already structured around a persistent store, so this should be a property of how the editor talks to that store from the start, not a resilience feature bolted on later.

**Phase to address:** Zone editor and colour-correction view phases — persistence-on-every-edit should be a stated requirement of both, verified with an explicit "refresh mid-session, confirm state survives" test.

---

### Pitfall 16: Windows-specific path and upload handling gaps

**What goes wrong:** Windows' legacy `MAX_PATH` (260 character) limit still affects many Win32-backed file APIs even though the OS itself supports much longer paths, and Python's own long-path support depends on both the Python installer version and OS-level opt-in — a project deployment path with deeply nested folders (e.g., a `Series/Volume/Page` directory structure mirroring the data model, plus vendored third-party directories already present in this repo) is a plausible way to accidentally exceed it, especially combined with descriptive filenames. (MEDIUM confidence — this is well-documented Windows/Python behaviour, though modern Python 3.11+ installers on modern Windows 10/11 largely mitigate it by default; the project's own environment is Windows 10, where this is more likely to bite than on 11.)

**Why it happens:** Development and testing happening on the same single Windows machine as production (the explicit v1 deployment model) means path-length issues that would surface immediately in a CI matrix covering multiple OSes can instead go unnoticed for a long time, then surface unpredictably on a specific deeply-nested project/volume/page path during a live demo.

**How to avoid:** Keep generated file/directory names short and flat where possible (e.g., ID-based rather than title-based paths, matching the existing entity-ID-first data model already in place), and test at least once with a realistically deep path before relying on it. Given the single-machine deployment, this is a low-effort, low-priority check rather than a structural redesign — but worth a deliberate five-minute test rather than an assumption.

**Phase to address:** Project/palette persistence phase (the Active requirement for a persistent project with accumulating palette) — worth a quick explicit test once file/directory naming conventions are decided.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reading proposal-raster pixels directly instead of always going through a mode-extraction function | Faster to prototype a "does Cobra even work" spike | Reintroduces VAE drift (Pitfall 1) as soon as any code path bypasses the enforced read path | Only in a throwaway exploratory script never wired into the product path |
| In-memory-only undo/edit state during early editor prototyping | Faster initial editor build | Data loss on refresh (Pitfall 15), and a harder retrofit once artists are actually testing live | Acceptable for the very first non-demo internal prototype; must be fixed before any artist-facing session |
| Flat scalar reject threshold with no instrumentation | Ships snapping quickly | Cannot be tuned against real data later without having logged the inputs needed to tune it (Pitfall 10) | Never — log the distances and outcomes from day one even if the threshold itself starts as a guess |
| PSD export tested only in Photoshop | Faster export-phase development, matches developer's own tooling | Silent Clip Studio breakage discovered only once a professional colourist opens the file (Pitfall 4) | Never as a release gate; acceptable only for the earliest in-progress export code before the first colourist test session |
| 16-bit-per-channel export "for safety" on flat (uniform) colour layers | Avoids worrying about precision | Roughly doubles file size for zero visual benefit on genuinely flat regions, worsening the PSD size ceiling risk (Pitfall 5) | Acceptable only for a Tier 2 gradient/shadow-mask layer, never for the flat colour layers themselves |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| Cobra (diffusion proposer) | Treating its output raster as directly displayable/editable content | Always route through mode extraction per region; never display or diff the raw proposal raster in the UI (spec already mandates "never shown to the artist") |
| Clip Studio Paint (PSD import) | Assuming Photoshop-clean export implies Clip-Studio-clean import | Explicit dual-app round-trip test as an export-phase release gate (Pitfall 4) |
| Vendored `LineFiller` | Assuming its output always satisfies the §3 exhaustiveness invariant | Treat coverage <1.0 as an expected, characterized input to the application layer, and design the editor/export path to surface and fix gaps rather than assume the invariant holds (Pitfall 6) |
| SQLite persistence layer | Buffering edits in memory and writing back only periodically | Write every meaningful edit immediately; treat the store as the single source of truth the moment an edit happens, not at save/session-end (Pitfall 15) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-resolution canvas held client-side per open page | Browser tab slows down or crashes after several pages/edits in one session | Viewport-scoped rendering; keep authoritative label map server-side (Pitfall 13) | A handful of full-resolution studio pages open across one working session, or one page with a long undo history |
| Naive concurrent Cobra invocation | GPU OOM or unexplained hang when a second job fires while one is running | Explicit single-worker queue around Cobra calls, even in single-user v1 (Pitfall 14) | Any accidental double-invocation — re-run during a still-running job, a background eval script overlapping an interactive session |
| "Per zone" PSD export granularity on hatching-dense pages | Export takes a long time, produces a very large file, or fails to open cleanly | Pre-export size/layer-count estimate with a warning or PSB fallback (Pitfall 5) | Pages with region counts in the hundreds per panel (already observed on Moebius-style hatching-adjacent pages) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Treating "single machine, supervised demo" as a reason to skip all input validation on uploaded images | A malformed/corrupted upload during a live session crashes the pipeline mid-demo (already flagged generally in CONCERNS.md, but worth restating as a live-demo-specific risk, not just a code-quality one) | Validate uploaded images (dimensions, colour mode, bit depth) before they enter the pipeline, even though v1 has no untrusted external users — the risk here is a bad file, not a malicious actor |
| Assuming OpenRAIL++-M's use-based restrictions are purely a legal/contract concern with no product-code implications | If a later hosted tier is built without carrying Attachment A's restrictions into terms of service (already flagged as future work in the resolved P1), the licence chain breaks silently | Track this as an explicit pre-hosting checklist item, not something assumed handled because it was "resolved" at the research stage — resolution here means "understood," not "implemented" |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Flagging too many regions as "new colour" (loose CIELAB threshold miscalibration) | Artist stops trusting/reading flags, defeating the entire point of confidence triage (Pitfall 10) | Bias the threshold toward over-flagging deliberately but validate against real accept/reject data early, and keep flagged-region precision visible so miscalibration is caught quickly |
| Silent colour-drift differences between panels that should be identical (Pitfall 1) | Artist perceives inconsistent, "off" colouring without an obvious single thing to fix, which is worse than an overtly wrong but explainable error | Enforce reference-locking/palette-snap as the actual source of truth for repeated content, and treat any drift after snapping as a bug, not "the model being creative" |
| Halo/fringing under AA line art in exported flats (Pitfall 3) | Artist immediately reads the export as amateurish, regardless of how good the underlying colour choices are | Extend flat fills slightly under the ink's AA fringe at export time; verify visually at high zoom on curved lines before considering export "done" |
| Exported PSD that opens differently in Clip Studio than in Photoshop (Pitfall 4) | Artist loses trust in the deliverable itself, the actual product surface | Dual-app round-trip test as a hard release gate for the export phase |

## "Looks Done But Isn't" Checklist

- [ ] **Mode extraction:** Often looks done once it returns *a* colour per region — verify it's tested against boundary-adjacent bleed (Pitfall 2) and multi-modal/shaded regions specifically, not just uniform synthetic test regions.
- [ ] **CIELAB snapping:** Often looks done once it snaps *most* colours correctly on a happy-path test page — verify against the spec's own explicitly-named hard cases (§10: shadow-side skin vs. hair, two characters in similar uniforms) before considering it validated.
- [ ] **PSD export:** Often looks done once it opens correctly in Photoshop — verify it also opens correctly, with the same structure, in Clip Studio Paint (Pitfall 4), and verify against a realistic hatching-dense page's actual region/layer count, not just a clean test page (Pitfall 5).
- [ ] **Merge/split editor:** Often looks done once a merge or split visually appears correct on screen — verify the §3 exhaustiveness/exclusivity invariant programmatically after the operation, not just visually, and verify at multiple zoom levels (Pitfall 7).
- [ ] **Metrics instrumentation:** Often looks done once numbers are being logged somewhere — verify post-correction time specifically (not just first-pass time) is captured from real artist sessions, and verify "regions per panel" is never used as a standalone pass/fail gate (Pitfall 11, Pitfall 12).
- [ ] **Undo/redo:** Often looks done once undo/redo visibly works for a single operation — verify a multi-step undo/redo sequence returns to bit-identical label-map states, not just visually similar ones (Pitfall 8).
- [ ] **Unassigned-pixel handling:** Often looks unnoticed entirely, since it's invisible on the four already-validated test pages — verify explicitly against a hatching-dense page, since that's where the known `merge_fill` defect actually manifests (Pitfall 6).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Diffusion colour drift reaching the deliverable (Pitfall 1/2) | LOW | Because regions store `palette_entry_id` and never RGB (§3 invariant), a drift bug is fixable by re-running mode extraction/snapping against already-segmented regions without re-running Cobra or re-touching the artist's edits — this is exactly the payoff of the data-model decision already made |
| PSD cross-app incompatibility discovered late (Pitfall 4) | MEDIUM | Export structure is isolated to the final export stage; fixing it means adjusting the export writer, not the data model — but requires re-testing every prior "done" export-phase work in both apps |
| Unassigned-pixel gaps discovered in already-exported files (Pitfall 6) | LOW–MEDIUM | Because the label map (not the export) is the source of truth, a fill/gap-highlight pass can be added and re-exported from existing project data without re-running segmentation or diffusion |
| Undo/redo corruption discovered after artist sessions already happened (Pitfall 8) | HIGH | If undo/redo actually corrupted a persisted label map (not just an in-memory session), recovering the artist's true intended state may not be possible without their manual re-review — this is the single most expensive recovery case in this list, which is the argument for the invariant-check-on-every-transition prevention being non-negotiable rather than a nice-to-have |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Diffusion raster read as deliverable (1) | Diffusion integration + mode extraction | Unit test: synthetic proposal raster with injected per-pixel gradient noise → mode extraction returns stable colour |
| Boundary bleed into mode extraction (2) | Mode-extraction/snapping | Synthetic two-colour boundary test; validate against real thin-corridor regions from hatching-adjacent pages |
| AA halo/fringe at export (3) | Layered export | Visual QA at 400%+ zoom on a curved AA line, comparing haloed vs. under-extended flat fill |
| PSD cross-app structural breakage (4) | Layered export | Dual-app (Photoshop + Clip Studio) round-trip open test as a release gate |
| PSD size/layer ceiling (5) | Layered export | Pre-export size/layer estimator; test against a hatching-dense page's actual region count under "per zone" granularity |
| Unassigned-pixel export leakage (6) | Zone editor + layered export | Coverage check visible in-editor; export gate blocking on unacknowledged sub-100% coverage |
| Coordinate-space/hit-testing bugs (7) | Zone editor + panel editor | Shared, independently unit-tested screen↔label-map transform; tests at extreme zoom ratios both directions |
| Undo/redo invariant violations (8) | Zone editor | Automated multi-step undo/redo sequence test asserting bit-identical label-map states; runtime invariant assertion after every transition |
| CIELAB L*-downweight miscalibration (9) | Mode-extraction/snapping | Regression test set built from real known-hard cases (shadow-skin vs. hair, similar uniforms) |
| Reject-threshold miscalibration (10) | Mode-extraction/snapping + metrics | Flagged-region precision tracked from first real session; threshold revisited against real accept/reject data |
| Region-count-as-quality-score (11) | Metrics instrumentation (cross-cutting) | Roadmap/phase success criteria reviewed to ensure no phase cites region count alone as a pass/fail gate |
| Overstated first-pass savings (12) | Metrics instrumentation + colour-correction view | Post-correction timing instrumented in the colour-correction view's first version, not retrofitted |
| Browser memory blowups (13) | Zone editor + panel editor | Viewport-scoped rendering verified against a real full-resolution studio page, not a downscaled test asset |
| GPU OOM under concurrency (14) | Diffusion integration | Explicit single-worker queue built into the initial Cobra wrapper |
| Lost edits on refresh/crash (15) | Zone editor + colour-correction view | Explicit "refresh mid-session" test confirming persisted state survives |
| Windows path handling (16) | Project/palette persistence | One-time deep-path test once naming conventions are set |

## Sources

- Adobe / Photoshop official and reference documentation on PSD/PSB size limits (30,000px PSD ceiling, 2GB PSD ceiling, PSB up to 300,000px) — https://docs.fileformat.com/image/psb/, https://www.lenovo.com/us/en/glossary/psb/
- Clip Studio Paint official support articles on PSD import compatibility (locked-transparency-in-group loss, layer effects dropped, non-native layer types rasterized) — https://ask.clip-studio.com/en-us/detail?id=121207, https://ask.clip-studio.com/en-us/detail?id=17327, https://ask.clip-studio.com/en-us/detail?id=72718
- Adobe Photoshop official color-management documentation on embedded ICC profile handling and mismatch policy — https://community.adobe.com/t5/photoshop-ecosystem-discussions/an-embedded-color-profile-that-does-not-match-the-current-rgb-working-space/td-p/9023300, https://www.colourphil.co.uk/photoshop-assign-profile.shtml
- Community reports on practical Photoshop layer-count performance degradation (8,000 technical cap; reported slowdown near thousands of layers) — https://community.adobe.com/questions-712/i-need-to-have-more-than-8-000-layers-in-my-photoshop-document-1158780
- VAE reconstruction artifact taxonomy (color shift, grid, blur, corner/droplet artifacts) in latent diffusion models, and color-inconsistency in inpainting/iterative editing — REED-VAE (arXiv 2504.18989, CGF 2025), "Towards Enhanced Image Inpainting" (arXiv 2312.04831 / CVPR 2025), Vivat VAE artifact-mitigation paper
- CIEDE2000 color-difference formula rationale, including its specific lightness/chroma/hue weighting corrections over plain CIELAB Euclidean distance, and its use in skin-tone matching — CIE CIEDE2000 development literature, colormemorygame.com explainer, skin-tone-matching application papers
- FlatMagic (CHI 2022) — ACM listing and abstract confirming flatting as a documented professional bottleneck and the basis for AI-driven flatting support tooling — https://dl.acm.org/doi/10.1145/3491102.3502075 (full text access blocked; abstract-level confirmation only, consistent with PROJECT.md's own citation)
- Krita official flat-coloring documentation and independent artist-community discussion on AA-line halo/fringing and the 2-4x-then-downsample practice — https://docs.krita.org/en/tutorials/flat-coloring.html, deviantArt forum discussion
- Manga line-art segmentation research on synthetic-vs-real generalization gap (near-perfect AP on synthetic contour data vs. materially lower performance on data simulating real hand-drawn, open-contour line art) — arXiv 2509.09501 (Region-Wise Correspondence Prediction between Manga Line Art Images)
- General GPU-serving literature on per-process VRAM footprint and lack of copy-on-write sharing across concurrent inference workers — Triton Inference Server documentation, industry write-ups on GPU concurrency costs
- Browser canvas memory/size limits (iOS Safari ~4096px/384MB constraints, 32-bit coordinate ceilings) — WebKit engineering commit notes, pqina.nl canvas-memory-limit explainers
- Windows MAX_PATH / long-path Python behaviour — Python documentation on Windows path handling, Microsoft long-path removal notes
- Automatic colorization time-savings overstatement pattern in research and production accounts (measured speed excluding setup/correction cost; animator-reported acceptable correction overhead) — general survey observations in recent manga/anime colorization literature (arXiv sources on colorization ambiguity and correction cost)
- Project's own resolved spec and codebase artifacts: `flatting-pipeline-spec.md` §§1.4, 1.6–1.10, 2.2, 3, 5, 7, 9, 10; `.planning/codebase/CONCERNS.md` (memory/tiling, LineFiller `merge_fill` coverage figures)

---
*Pitfalls research for: Comic flatting application (editors, diffusion integration, palette snapping, PSD export, metrics)*
*Researched: 2026-08-02*
