# Project Research Summary

**Project:** ComicColor
**Domain:** Local-first web application layer over an already-validated comic/manga colour-flatting core
**Researched:** 2026-08-02
**Confidence:** MEDIUM-HIGH

## Executive Summary

ComicColor adds an artist-facing web layer on top of a deterministic segmentation core already validated (LineFiller + MangaLineExtraction, proven across four style regimes). Research converges on FastAPI backend, Konva.js canvas editors, psd-tools for export, and Cobra (SIGGRAPH 2025 diffusion model) wrapped as an isolated black-box colour proposer never shown raw to the artist. FlatMagic (CHI 2022, peer-reviewed) independently validates the core thesis: professionals reject opaque auto-colourization but want inspectable, editable intermediate stages and a persistent cross-page swatch.

The single most consequential fact: Cobra pins `numpy==1.26.4`/`torch==2.5.1` exactly, hard-conflicting with this project's `numpy>=2.0`. This requires a fully isolated environment invoked via subprocess or a long-lived local-HTTP worker, never imported in-process — all four research docs agree this is also the right crash-isolation boundary. Two things need empirical spikes, not assumptions: Cobra's VRAM footprint (undocumented upstream) and psd-tools' group/layer write API robustness at this project's real layer counts (documented upstream as less mature than its read path).

The main risk is quietly reintroducing failure modes the architecture was designed to prevent: reading diffusion pixels directly instead of region-wide mode extraction (VAE drift), client-owned geometry breaking the label-map exclusivity/exhaustiveness invariant, or treating region count as a quality score (the exact mistake already made and reversed in the P3/AB spike). Mitigations converge: one enforced mode-extraction call site, server-authoritative label map with client-side PNG-packed read caching, and metrics instrumented from first commit.

## Key Findings

### Recommended Stack (resolved — do not re-litigate)
- **Backend: FastAPI** — async-native, doesn't fight a bespoke canvas editor like NiceGUI/Streamlit/Gradio.
- **Frontend canvas: Konva.js** on vanilla TS/Vite (no React/Svelte for the two editors — imperative event-driven state fights virtual-DOM reconciliation).
- **PSD writing: psd-tools 1.17.4** — verified write-capable (`create_pixel_layer`, `create_group`, `.append()`), MIT, no numpy pin. Supersedes abandoned `pytoshop`/`psd_tools2/3`.
- **Label-map transport: RGB-packed PNG**, client-decoded via `getImageData()` for O(1) local hit-testing; mutations (merge/split) always round-trip server-side through `masks.py`.
- **Diffusion worker: separate long-lived local process**, not in-process singleton (crash-couples web server) nor subprocess-per-job (pays multi-GB load every job).
- **Bubble/SFX detector: `ogkalu/comic-text-and-bubble-detector`** (Apache-2.0, broadest style coverage) primary; `ShadowB/Manga109-...-yolov26-segmentation` (MIT, real masks, manga-only) secondary. GPL-3.0 and non-commercial candidates disqualified. No candidate validated on Franco-Belgian/ligne claire styles — manual masking stays first-class, not fallback.
- **Background jobs: `ThreadPoolExecutor(max_workers=1)` + SQLite job status** — Celery/Redis/arq rejected for v1 (Redis has no clean Windows story).

**Open empirical questions requiring a Phase 0 spike:** Cobra VRAM requirement (no public figure; ~12GB a reasonable floor to test, not verified); psd-tools group/layer write API robustness at real per-panel layer counts.

### Expected Features
FlatMagic (CHI 2022, read directly) is load-bearing: flatting is ~50% of colouring labour, professionals reject opaque AI results not automation itself.

**Must have (P1, mirrors PROJECT.md Active):** persistent project + cross-page palette accrual; swatch upload and character-sheet proposal (never authoritative); panel polygon detection + full editing; protected bubble/SFX masking (detector-assisted, manual guaranteed fallback); zone click-merge/trace-split; Cobra proposal never shown raw; mode extraction + CIELAB snap with reject-before-snap; 3-seed confidence triage; one-click colour reassignment; PSD export (3 granularities); metrics from day one.

**Differentiators:** confidence-triage review queue (no competitor has this); palette-referenced never-baked-RGB model enabling instant global recolour; reject-before-snap CIELAB matching.

**Defer:** full auto-colourize (explicitly rejected by FlatMagic's own participants; CSP's version still "Technology Preview," Petalica discontinued 2025); auto shading/lighting; SAM-based segmentation (anti-pattern); cross-page identity propagation; point-based hint control; pre-proposal hint painting.

### Architecture Approach
New packages (`protect/`, `colour/`, `pipeline/`, `export/`, `worker/`, `web/`) sit beside existing untouched `model/`, `segmentation/`, `extract/` — additive schema only, no `entities.py` changes. Core stays dependency-light; FastAPI/torch imports isolated to `web/` and `colour/cobra.py`.

**Major components:** `pipeline/` — declarative stage registry over a SQLite run table (`PanelStageRun`), marks only downstream stages stale after an edit, build first; `web/` — thin FastAPI shell, no logic; `colour/` — Cobra wrapper, mode extraction, CIELAB snap, triage, testable via CLI; `worker/` — separate OS process holding Cobra resident in VRAM; `export/` — split `render.py` (numpy, golden-image testable) and `psd.py` (assembly, round-trip testable); `protect/` — manual masking v1, same `Protocol` pattern as `Segmenter`.

**Confirmed patterns:** server-authoritative label map, client read-only cache (never client-owned geometry as source of truth); revision counters for cache invalidation, not recomputation; Cobra loaded once in a resident worker, never per-request or in-process.

### Critical Pitfalls
1. **Diffusion raster read as anything but mode-extraction source (P1)** — VAE colour-shift artifacts; enforce one mode-extraction call site, unit-test with synthetic noise first.
2. **Boundary-adjacent bleed into mode extraction (P2)** — erode region mask before extracting mode; diffusion decode doesn't respect exact label boundaries.
3. **Undo/redo permitting invalid label-map states (P8)** — snapshot whole label maps, not inverted ops; runtime invariant check after every transition is non-negotiable (highest recovery cost pitfall in the list).
4. **PSD structure diverging between Photoshop and Clip Studio (P4)** — keep export minimal (plain layers/groups, normal blend); dual-app round-trip test as a hard release gate.
5. **Region count treated as quality score, not health alarm (P11)** — project already made and reversed this mistake once (P3/AB); no phase success criteria should cite region count alone.

Also foregrounded: **coordinate-space/hit-testing bugs (P7)** — one shared, unit-tested screen↔label-map transform before either editor is built; **overstated first-pass savings (P12)** — post-correction timing must be built into the colour-correction view's first version, not retrofitted.

## Implications for Roadmap

### Where researchers agree (signal)
ARCHITECTURE.md and PITFALLS.md independently converge: build the pipeline backbone and shared coordinate-transform layer before either editor; the label-map invariant check must exist before, not after, the zone editor; Cobra/diffusion integration is an isolated spike-first concern with the worker boundary built once, remote-ready, single-worker queue from the initial wrapper; metrics instrumentation is cross-cutting and front-loaded, never appended.

### Phase 1: Pipeline backbone + shared coordinate/invariant infrastructure
**Rationale:** Prerequisite every later editor/stage depends on; retrofitting invariant checks after an editor exists is far costlier.
**Delivers:** `pipeline/` stage registry + `PanelStageRun` table; shared screen↔label-map transform module; exclusivity/exhaustiveness invariant-check function.
**Avoids:** Pitfall 7, 8; sets up detection for Pitfall 6.

### Phase 2: Panel polygon editor + protected (manual) masking
**Rationale:** Protected masks need the panel coordinate space settled first; lowest model risk (no GPU).
**Delivers:** Panel polygon detection + drag/add/delete/draw-from-scratch editing; manual bubble/SFX masking as first-class UI.
**Uses:** Konva.js/vanilla TS; Phase 1 transform module. **Implements:** `protect/manual.py`.

### Phase 3: Zone editor (click-merge, trace-split)
**Rationale:** Requires panel coordinate space + invariant infrastructure; highest invariant-risk surface (Pitfalls 6/7/8 concentrate here) — harden before colour data depends on stable regions.
**Delivers:** Click-merge/trace-split, coverage/gap visibility with one-click fix, undo/redo via whole-map snapshotting + invariant check per transition.
**Avoids:** Pitfalls 6, 7, 8, 13 (viewport-scoped rendering), 15 (persist-on-edit).

### Phase 4: Cobra integration spike + colour proposal pipeline
**Rationale:** Highest-uncertainty phase; spike in isolation before downstream work assumes a call shape or batch size.
**Delivers:** Isolated Cobra environment + worker-HTTP boundary; validated VRAM measurement; `worker/` process wired to `web/`.
**Avoids:** Pitfall 14 (GPU OOM/concurrency). **Research flag:** VRAM figure and environment isolation unverified upstream — spike required.

### Phase 5: Mode extraction, CIELAB snapping, confidence triage
**Rationale:** Strictly downstream of Phase 4; reject threshold needs tuning against real Cobra decode noise, not synthetic-only data.
**Delivers:** Eroded-interior mode extraction, CIELAB snap with reject-before-snap and validated L* downweighting, 3-seed triage.
**Avoids:** Pitfalls 1, 2, 9, 10. **Research flag:** needs validation against real hard-case data (shadow-skin vs. hair, similar uniforms) — L* factor is a hypothesis, not a given.

### Phase 6: Colour-correction view + metrics instrumentation
**Rationale:** Downstream of triage; where the core value proposition becomes measurable; timing instrumentation cannot be retrofitted.
**Delivers:** One-click colour reassignment; post-correction minutes/page, hints/fillable-region ratio, auto-accept rate, flagged-region precision from first commit.
**Avoids:** Pitfalls 11, 12, 15.

### Phase 7: Layered PSD export
**Rationale:** Read-only over the data model, independent of all editors; deliberately last since it's the literal deliverable and benefits from stable upstream data.
**Delivers:** `render.py` (AA-halo-avoiding dilation) then `psd.py` (psd-tools assembly, 3 granularities) plus pre-export size/layer estimator.
**Avoids:** Pitfalls 3, 4, 5. **Research flag:** psd-tools' write API needs validation against a hatching-dense page's actual region count under "per zone" granularity, not just a clean test page.

### Research Flags
Needs deeper research/spike: Phase 4 (Cobra VRAM/isolation), Phase 5 (CIELAB tuning against real data), Phase 7 (psd-tools robustness at scale).
Standard patterns, skip research-phase: Phase 1 (stage-registry pattern fully specified), Phase 2 (Konva's core documented use case), Phase 3 (RGB-packed-PNG transport pattern precedented), Phase 6 (mechanically straightforward, risk is process discipline not technical uncertainty).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Backend/PSD/colour findings verified against PyPI/GitHub/official docs; Cobra VRAM and frontend perf numbers explicitly LOW-confidence estimates. |
| Features | MEDIUM-HIGH | Anchored by directly-read peer-reviewed FlatMagic paper; MEDIUM on bubble/SFX detector accuracy — unbenchmarked on this project's four style regimes. |
| Architecture | MEDIUM-HIGH | Grounded in existing validated codebase read directly; psd-tools group/layer API explicitly flagged experimental upstream. |
| Pitfalls | MEDIUM-HIGH | Critical claims corroborated by official docs/peer-reviewed sources; some numeric thresholds MEDIUM/LOW and flagged for empirical validation. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address
- Cobra VRAM requirement undocumented upstream — mandatory Phase 0 spike within Phase 4.
- No bubble/SFX detector benchmarked on this project's four style regimes — run top two candidates against existing P3/AB test pages before deciding manual-masking UI weight.
- psd-tools' write API documented as less mature than its read path — validate against realistic hatching-dense layer counts before considering export done.
- CIELAB L* downweight factor and reject threshold are unvalidated hypotheses — build a labelled hard-case test set before treating snapping as production-ready.
- Whether Cobra's reference-conditioned mode loads a live T5-XXL text encoder is unresolved — folds into the Phase 4 VRAM spike.

## Sources

### Primary (HIGH confidence)
- `github.com/zhuang2002/Cobra` requirements.txt/README, fetched directly
- `psd-tools` PyPI wheel METADATA, PR #428, read directly
- Existing codebase: `masks.py`, `entities.py`, `store.py`, read directly
- `flatting-pipeline-spec.md`, `.planning/PROJECT.md`
- FlatMagic (CHI 2022), read directly in full
- Clip Studio Paint official PSD import compatibility docs
- Adobe/Photoshop official PSD/PSB size-limit docs

### Secondary (MEDIUM confidence)
- Konva.js performance docs; CVAT Join/Slice/Brush docs
- HuggingFace model cards for bubble/SFX detector shortlist
- VAE artifact-taxonomy and inpainting colour-consistency literature
- CIEDE2000 rationale; ComfyUI/Automatic1111 architecture comparisons; FastAPI+GPU deployment guides
- Krita flat-coloring documentation on AA-line halo/fringing

### Tertiary (LOW confidence, flagged for validation)
- Cobra VRAM figures (no public source)
- eBDtheque licence terms (unverified)
- Practical Photoshop layer-count degradation figure (single community report)
- Petalica Paint discontinuation causal attribution (fact confirmed, cause inferred)

---
*Research completed: 2026-08-02*
*Ready for roadmap: yes*
