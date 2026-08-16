# ComicColor

## What This Is

A layered colour-flatting application for comic and manga production. An artist
uploads their line art pages, character sheets and palette; the app segments
panels and colour zones deterministically, proposes colours with a generative
model, and returns an editable, layered PSD that drops straight into Photoshop
or Clip Studio. Every stage boundary is inspectable and correctable by the
artist — that is the product, not a feature of it.

For v1 the users are professional colourists, observed rather than served: the
app runs on one machine (Raph's), and testing happens live over video call with
the artist watching their own page go through the pipeline.

## Core Value

An artist gets flats they can actually use, and every place the machine got it
wrong is one click to fix.

## Requirements

### Validated

<!-- Inferred from the existing codebase and the resolved spec prerequisites. -->

- ✓ §3 data model — `Series → Volume → Page → Panel → Region`, palette entries
  referenced by ID with no RGB field to bake into, region exclusivity enforced
  structurally by a single per-panel label map — existing
  (`model/entities.py`, `model/masks.py`, `model/store.py`)
- ✓ §1.4 trapped-ball region segmentation — `hepesu/LineFiller` (MIT) with
  `merge_fill`, behind a swappable `Segmenter` protocol — existing and
  **visually validated** across four style regimes (Franco-Belgian hatching,
  thin-line manga, ligne claire, thick idiosyncratic)
- ✓ §7 line extraction — `MangaLineExtraction` (MIT) wrapped as
  `MangaLineExtractor`, on by default as a hatching absorber — existing
  (`extract/manga_line.py`)
- ✓ §1.3 line gap closure — adaptive-radius trapped ball plus skeleton endpoint
  bridging — existing (`segmentation/closure.py`)
- ✓ Panel gutter detection — existing (`segmentation/panels.py`), but not yet
  validated against diagonal or open panels
- ✓ Evaluation harness — P3 region-count benchmark and segmenter A/B with
  persisted reports — existing (`spike/p3.py`, `spike/ab.py`, `reports/`)
- ✓ P1–P4 prerequisites resolved — licence chain clear of AGPL, export format
  and structure decided, segmentation viability proven
- ✓ Artist creates a persistent project and adds pages to it over time, with
  the palette accumulating across pages — Phase 1 (PROJ-01..05)
- ✓ Artist uploads a swatch image and the app builds palette entries from it —
  Phase 1 (PAL-01)
- ✓ App proposes palette entries extracted from an uploaded character sheet;
  artist accepts, rejects or edits each one — Phase 1 (PAL-02), proposals
  ephemeral and re-derived server-side, bound only at accept time
- ✓ Artist adds or edits palette entries by hand, and names them — Phase 1
  (PAL-03/PAL-04); a recolour propagates without re-running any stage
- ✓ Pipeline stage registry, screen↔label-map coordinate transform, and the
  label-map exclusivity/exhaustiveness invariant check — Phase 1, built and
  unit-tested before any editor depends on them

### Active

<!-- v1 scope. Hypotheses until a colourist uses them on a real page. -->

- [ ] App detects panels as polygons and the artist can drag, add and delete
      vertices, or draw a panel from scratch
- [ ] App masks speech bubbles and SFX lettering as protected regions, with
      in-app manual masking as the guaranteed fallback
- [ ] Artist sees the zone segmentation and merges zones by clicking
- [ ] Artist splits a zone by tracing a cut, which changes the label map only
      and never appears in any output
- [ ] Cobra proposes colours per panel at 384–512px, never shown to the artist
- [ ] Per-region mode extraction and CIELAB snap to palette entries with L*
      downweighted; out-of-range distances create flagged entries rather than
      snapping silently
- [ ] Confidence triage over 3 seeds surfaces the zones worth the artist's
      attention
- [ ] Artist reassigns a zone's colour in one click in a colour-correction view
- [ ] Artist exports PSD with one layer group per panel, in three granularities:
      single flat layer, layer per colour (default), layer per zone
- [ ] App measures post-correction minutes per page, hints per fillable region,
      auto-accept rate and flagged-region precision from the first run

### Out of Scope

- **Hosting, accounts, multi-user, upload plumbing** — v1 runs on one machine
  and is demonstrated over video call. Deferred deliberately; the decision was
  "let's keep it ultra simple."
- **Running on tester hardware** — no tester is ever left alone with the app in
  v1, so no CPU fallback, no remote inference seam, no Mac support.
- **Shading, lighting, effects, halftone** — Tier 2/4. Flats are the product.
- **Painted or lineless art** — no line means no line art means no product.
- **Text rendering, lettering, translation** — never in scope.
- **Cross-page character identity propagation** — Tier 2. v1 carries the palette
  across pages but not automatic identity resolution.
- **American comics adapter** — needs a retrained extractor (§7). Untested and
  acknowledged as such.
- **Hatching adapter** — Tier 3, and it stays there: P3's alarm turned out to be
  our own segmenter, not the art.
- **Latency and throughput work** — LineFiller runs 15–66s per page and scales
  with pixel count. Explicitly not a concern at this stage.
- **Modifying Cobra's DiT** — forfeits the pretrained weights and buys nothing.

## Context

**The spec is the source of truth for pipeline internals.**
`flatting-pipeline-spec.md` carries the full architecture, the resolved
prerequisites P1–P4, the metrics list, the anti-patterns and the known hard
cases. This document scopes the product around it; it does not restate it.

**The central architectural claim** is that the generative model is a colour
*proposer*, not the output path. Exactness comes from deterministic
segmentation before and after. Diffusion output is never the deliverable — VAE
round-trip introduces colour drift, gradients where uniformity was required,
and halos at line edges, which is the entire reason research demos have not
displaced hand-flatting.

**Why the editor matters more than the model.** FlatMagic (CHI 2022) documented
that professionals reject auto-colorisation specifically because intermediate
stages are opaque and uncontrollable. A pipeline whose every boundary is an
editable layer answers that objection by construction. The region editor is the
differentiator, not a nicety.

**The deterministic front half already exists and is validated.** What v1 adds
is the model integration, the snapping, the two editing surfaces, the export and
the instrumentation.

**Prior exploration.** The P3 region-count spike and the follow-up segmenter A/B
live in `src/comiccolor/spike/` with reports in `reports/p3/` and `reports/ab/`.
P3's raw verdict (HATCHING DOMINATES on Moebius) was reversed by the A/B — it
was measuring our own trapped-ball implementation, not the artwork. Do not cite
P3 without the A/B alongside it.

**Working practice informs the export decision.** A professional colourist Raph
has worked with already works one layer per colour, which is why that is the
default rather than a compromise.

**Panel segmentation is not solved and this is known.** Artists routinely draw
open panels, characters and bubbles crossing panel borders, and large SFX
lettering overlaying several panels at once. v1's answer is not a better
detector — it is making the polygon editable.

**Build from existing tools first.** For each pipeline stage, search for an
existing library and check its licence before proposing to write one. Custom
code is for the seams, the data model, and gaps nothing fills. This is a
standing instruction, learned the expensive way on the trapped-ball
implementation.

## Constraints

- **Deployment**: Single machine, local web app — Testing is supervised over
  video call; nobody else runs it. Later hosting is a separate, deliberately
  deferred concern.
- **Hardware**: Local NVIDIA GPU — Cobra needs it. No CPU path in v1.
- **Tech stack**: Python 3.11+, numpy/opencv/scipy/pillow, SQLite, pytest —
  Established by the existing codebase; the web layer is the only open choice.
- **Licence**: OpenRAIL++-M via Cobra's runtime PixArt pull — Its use-based
  restrictions propagate to derivatives. Keep the dependency pinned to the
  diffusers repo; the raw-`.pth` mirror is AGPL and "research purpose only".
- **Licence**: Project is intended to be open-source — Vendored dependencies
  (LineFiller, MangaLineExtraction) are MIT, which is compatible.
- **Export**: PSD only — `.clip` is an undocumented SQLite container; CSP
  imports PSD with groups intact, so one path serves both applications.
- **Data model**: Regions store `palette_entry_id`, never RGB — This is what
  makes "change the hair colour everywhere" a single-row update. Non-negotiable.
- **Evaluation**: Real ink layers, never extracted lines — Extracted lines are
  closed, gap-free and uniformly weighted. Real ink is none of those, and an
  evaluation set of extracted lines measures nothing.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Local web app rather than desktop or hosted | Same codebase deploys to a server later without a rewrite; hosting stays trivial by construction | — Pending |
| Single machine, supervised video-call testing | "Let's keep it ultra simple" — removes auth, uploads, tester hardware and remote inference from v1 entirely | — Pending |
| Two editing surfaces, not one | Geometry editor before colourisation, colour-correction view after; cleaner flow at the cost of more UI | — Pending |
| Persistent project as the unit of work | Palette accumulates across pages, which is what makes the §5 hint-collapse metric measurable at all | ✓ Good — Phase 1; one project per folder, enforced by `project.id CHECK (id = 1)` |
| One SQLite database per project folder, WAL + checkpoint on close | A project is a folder the artist can copy, and a checkpointed WAL means the copy is never a partial database | ✓ Good — Phase 1 |
| No Save button anywhere; every edit commits synchronously | PROJ-05 is "a refresh or crash loses no work"; a write buffer is the thing that would break it | ✓ Good — Phase 1 |
| Character-sheet proposals are ephemeral, re-derived server-side | The client sends an index, never an RGB value, so it cannot inject a colour under a character's name; nothing persists until accept | ✓ Good — Phase 1 (D-05) |
| Stage registry declares, never orchestrates | `run_stage` refuses unimplemented stages and never walks the chain, so forward-only-with-confirmation stays true by construction | ✓ Good — Phase 1 (D-10/D-11) |
| Palette from a separate swatch image upload | Artists already have a palette prepared for the whole project; extraction from character sheets is a proposal layer on top, not the source | — Pending |
| Panel polygons are editable by the artist | Open panels and border-crossing art are unsolved; making the boundary editable sidesteps the research problem | — Pending |
| Traced splits cut the label map only | The artist's line art is returned untouched; `masks.py` already makes split a relabel | — Pending |
| Manual bubble masking is the guaranteed fallback | Removes research risk from the critical path; an OSS detector is an upgrade, not a dependency | — Pending |
| LineFiller + MangaLineExtraction, merge on | Decided 2026-08-02 on visual comparison of renders, not region counts; ours shatters thin corridors, LineFiller's merge step collapses them | ✓ Good |
| PSD, one group per panel, layer per colour | Confirmed against a professional colourist's working practice; per-panel matches how Cobra is run anyway | ✓ Good |
| Cobra wrapped as a black box | Modifying the DiT forfeits pretrained weights and buys nothing | — Pending |
| Metrics instrumented from the first commit | Post-correction time is the only number worth quoting to a studio, and it cannot be retrofitted | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-16 after Phase 1*
