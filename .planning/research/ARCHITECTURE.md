# Architecture Research

**Domain:** Local-first web application wrapping a deterministic image-segmentation
pipeline plus a diffusion colour proposer (comic/manga flatting tool)
**Researched:** 2026-08-02
**Confidence:** MEDIUM-HIGH (grounded in the existing validated codebase, verified
library capabilities, and well-established local-inference architecture patterns;
LOW-confidence items are flagged individually)

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────────┐
│  frontend/  (separate npm project, canvas-based editor)                   │
│  - panel/zone geometry editor   - palette editor   - colour-correction UI │
│  - decodes label-map raster client-side for zero-latency hover/click      │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 │ HTTP + WebSocket (JSON, PNG rasters)
┌───────────────────────────────▼───────────────────────────────────────────┐
│  comiccolor.web  (FastAPI, NEW — the only new component with UI-facing    │
│  I/O; imports pipeline/model, never imports torch/diffusers directly)    │
│  - project/page/panel/palette CRUD routers                                │
│  - GET  panel label-map raster (packed 16-bit PNG)                        │
│  - POST edit-commit: split / merge / palette-assign / geometry edit       │
│  - WS   push notifications: "these panels changed, refresh"               │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 │ calls (in-process, same interpreter)
┌───────────────────────────────▼───────────────────────────────────────────┐
│  comiccolor.pipeline  (NEW — orchestration backbone)                      │
│  - stage registry (declarative: name, upstream deps, params)              │
│  - PanelStageRun table (SQLite): status, params_hash, upstream_rev        │
│  - runner: given a stale stage, invoke the existing composable function   │
└──────┬───────────────┬──────────────┬───────────────┬─────────────────────┘
       │               │              │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼───────────┐
│segmentation/│ │  protect/   │ │  colour/   │ │    export/       │
│extract/     │ │  (NEW)      │ │  (NEW)     │ │    (NEW)         │
│(EXISTING —  │ │ bubble/SFX  │ │ Cobra call │ │ render.py: numpy │
│ untouched)  │ │ masks; v1 = │ │ (via       │ │  compositing     │
│             │ │ manual only │ │ worker/)   │ │ psd.py: assembly │
│             │ │             │ │ snap+triage│ │  (psd-tools)     │
└─────────────┘ └─────────────┘ └─────┬──────┘ └──────────────────┘
                                       │ HTTP/IPC, separate OS process
                                ┌──────▼──────────────┐
                                │  comiccolor.worker   │
                                │  (NEW, optional      │
                                │  extra: [diffusion]) │
                                │  long-lived; Cobra/  │
                                │  PixArt resident in  │
                                │  VRAM; job queue      │
                                └──────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────┐
│  comiccolor.model  (EXISTING, untouched — entities.py, masks.py,        │
│  store.py). SQLite + .npz label maps on disk. Sole persistence layer.   │
│  ALL new components read/write through this; none duplicate its schema. │
└───────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Status |
|-----------|----------------|--------|
| `model/` | §3 entities, label-map storage, SQLite persistence, invariant enforcement | Existing — untouched |
| `segmentation/`, `extract/` | Deterministic geometric stages (panels, closure, region segmentation, line extraction) | Existing — untouched |
| `protect/` | Bubble/SFX protected masks; v1 ships manual-masking only, no model | New — no ML dependency |
| `pipeline/` | Stage registry + per-panel-per-stage run tracking + invalidation/runner | New — backbone, build first |
| `colour/` | Cobra wrapper, mode extraction + CIELAB snap, confidence triage | New — GPU-adjacent, testable via CLI without web layer |
| `worker/` | Long-lived process holding Cobra/PixArt resident in VRAM; job queue | New — thin wrapper around `colour/` |
| `export/` | PSD compositing (numpy) + assembly (psd-tools), read-only over the data model | New — no dependency on web/colour |
| `web/` | FastAPI app: routers, label-map raster endpoint, edit-commit, websocket push | New — the only UI-facing process |
| `frontend/` | Canvas-based editor (separate npm project, built to static assets served by `web/`) | New |

## Recommended Project Structure

```
ComicColor/
├── src/comiccolor/
│   ├── model/            # EXISTING — untouched
│   ├── segmentation/      # EXISTING — untouched
│   ├── extract/           # EXISTING — untouched
│   ├── spike/             # EXISTING — keep for research, not on the product path
│   ├── protect/           # NEW — §1.2 protected masks (manual-only in v1)
│   │   ├── base.py        #   Protocol mirroring LineExtractor/Segmenter style
│   │   └── manual.py       #   Persists artist-drawn masks; no detector yet
│   ├── colour/             # NEW — §1.6–1.8
│   │   ├── cobra.py        #   Wraps Cobra as a black box, call signature only
│   │   ├── snapping.py     #   Mode extraction + CIELAB snap
│   │   └── triage.py       #   3-seed variance → confidence
│   ├── pipeline/           # NEW — orchestration backbone (build first)
│   │   ├── stages.py       #   Declarative registry: stage name, reads, writes, deps
│   │   ├── runs.py         #   PanelStageRun CRUD (SQLite table alongside model/store.py)
│   │   └── runner.py       #   Given a page/panel, compute stale set, execute in order
│   ├── export/             # NEW — §1.10, read-only over model/
│   │   ├── render.py       #   Label map + palette → per-colour RGBA rasters (numpy only)
│   │   └── psd.py          #   Assembles PSDImage via psd-tools; depends on render.py
│   ├── worker/             # NEW — optional extra "diffusion"
│   │   ├── process.py      #   Long-lived entrypoint; loads Cobra once
│   │   └── jobs.py         #   Thin job table reusing pipeline/runs.py pattern
│   ├── web/                 # NEW — optional extra "web"
│   │   ├── app.py            #   FastAPI app factory
│   │   ├── routers/          #   project, page, panel, palette, export routers
│   │   ├── schemas.py        #   Pydantic request/response models
│   │   └── raster.py         #   Label map → packed-PNG encoder (shared by routers)
│   └── cli.py               # EXISTING — gains `serve` subcommand
├── frontend/                # NEW — separate npm project (not a Python package)
│   ├── src/editor/          #   panel/zone canvas editor, decodes packed PNG client-side
│   ├── src/palette/         #   palette editor + colour-correction view
│   └── dist/                #   build output, served as static files by web/app.py
├── third_party/             # EXISTING — LineFiller, MangaLineExtraction
├── tests/                   # Mirrors src/comiccolor/ layout, one dir added per new package
└── pyproject.toml           # Gains [project.optional-dependencies]: web, diffusion
```

### Structure Rationale

- **Core stays dependency-light.** `model/`, `segmentation/`, `extract/`, `protect/`,
  `colour/`, `export/`, `pipeline/` depend only on numpy/opencv/scipy/pillow/sqlite
  (plus `torch`/`diffusers` for `colour/cobra.py` specifically, and `psd-tools` for
  `export/psd.py`). None of them import FastAPI, uvicorn, or websockets. This is
  what makes the "library + CLI + web app in one repo, going open source" framing
  work: someone who wants only the segmentation library installs `pip install
  comiccolor` and gets a clean dependency set; `pip install comiccolor[web]` adds
  the server; `pip install comiccolor[diffusion]` adds the multi-GB torch/diffusers
  stack. This mirrors how the existing `pyproject.toml` already separates
  `dev` from core.
- **`web/` is a thin shell, not where logic lives.** Every router calls into
  `pipeline/`, `colour/`, `export/`, or `model/` directly; the FastAPI layer does
  request/response marshalling and the packed-PNG raster encoding only. This keeps
  the CLI and the web app as two equally-thin front ends over the same library —
  neither is privileged, both can be tested without the other running.
- **`pipeline/` sits beside, not inside, `model/`.** It adds one new table
  (`PanelStageRun`) to the same SQLite database `store.py` already owns, following
  the existing pattern of `Volume.palette_revision` (a revision counter, not an
  event log). It does not touch `entities.py`'s dataclasses or `masks.py`'s
  label-map format — no §3 schema change required.
- **`worker/` is physically separate from `web/`** (a different OS process), so a
  CUDA crash or OOM in a colourisation job cannot take down panel/zone editing,
  which has nothing to do with the GPU.
- **`frontend/` is not a Python package.** Keeping it a separate npm project with
  a build step avoids coupling the web server's Python dependency tree to a JS
  toolchain, and matches how virtually every FastAPI+SPA project is structured.

## Architectural Patterns

### Pattern 1: Declarative stage registry over a SQLite run table (not a DAG engine, not event sourcing)

**What:** Each pipeline stage (protect, closure, segment, colour_propose, snap,
triage) is registered with: a name, the composable function it calls (reusing
`segmentation/`, `colour/` functions unchanged), the artifacts/params it reads,
and the artifacts it writes. A new `PanelStageRun` table tracks, per
`(panel_id, stage)`: `status` (done/stale/running/failed), `params_hash`,
`upstream_rev`, `output_ref`, `updated_at`. A runner walks the registry in
topological order and executes only rows marked `stale`.

**When to use:** Whenever an upstream artifact changes (panel polygon edited,
zone split/merged, segmenter params changed) — the runner marks only the
downstream rows for that panel stale and re-executes those, leaving every other
panel and every other stage untouched.

**Trade-offs:** Heavier than "just call functions from a service layer" for the
simplest case, but that simplicity breaks the hard requirement (re-run only
downstream stages after an edit) the moment there is more than one panel per
page. Far lighter than adopting Airflow/Prefect/Dagster, which assume
multi-machine, multi-tenant scheduling this project will never need — v1 is
single-user, single-machine, and the existing codebase already prefers hand-built,
inspectable code over frameworks (see `store.py`'s hand-written SQLite schema
vs. an ORM). Not event-sourced: the label map and the palette table remain the
sole source of truth; there is no replay log to reconstruct state from, which
keeps the mental model identical to what `masks.py`'s docstring already
describes ("merge is a relabel, split is a relabel").

**Example (illustrative, not literal API):**
```python
# pipeline/stages.py
STAGES = [
    Stage("closure", reads=["page.line_art"], writes=["panel.closed_line"]),
    Stage("segment", reads=["panel.closed_line", "panel.protected_masks"],
          writes=["panel.label_map"], upstream=["closure"]),
    Stage("colour_propose", reads=["panel.label_map", "entity.references"],
          writes=["panel.proposal_raster"], upstream=["segment"]),
    Stage("snap", reads=["panel.proposal_raster", "volume.palette"],
          writes=["region.palette_entry_id"], upstream=["colour_propose"]),
]

# pipeline/runner.py
def invalidate_from(panel_id: int, stage: str) -> None:
    """Mark `stage` and everything downstream of it, for this panel, stale."""
    for s in downstream_of(stage):
        runs.set_status(panel_id, s.name, "stale")

def run_stale(panel_id: int) -> None:
    for stage in topological_order(STAGES):
        if runs.status(panel_id, stage.name) == "stale":
            stage.execute(panel_id)   # calls the existing segmentation/colour function
            runs.set_status(panel_id, stage.name, "done")
```

### Pattern 2: Server-authoritative label map, client-decoded raster for zero-latency reads, vector strokes for commits

**What:** The label map never leaves the server as the writable source of truth.
For each opened panel, the server packs the current int32 label map into a
16-bit-per-pixel PNG (label id split across the R and G channels of an 8-bit
RGBA PNG, since browser canvas `ImageData` is always 8-bit/channel) and sends it
once. The client decodes this into a typed array purely for **read** operations —
hover highlighting, click-to-select, and drawing the live preview of a freehand
stroke — all zero-round-trip, O(1) array lookups. Any **mutating** operation
(split, merge, palette reassignment) is committed by sending the *stroke
description* (a short list of path coordinates, or a region id + target palette
id) to the server, which performs the actual relabeling using the existing
`masks.py` utilities (extended with `split_region`/`merge_regions`), re-checks
`check_coverage`, persists, bumps `panel.label_map_revision`, and returns an
updated raster (or a bounding-box patch for large panels).

**When to use:** This is the pattern for every interaction that touches the
label map. See "Data Flow" below and the dedicated analysis in Anti-Patterns for
why the two alternatives (pure client-side geometry ownership; pure
server-round-trip-per-event) are rejected.

**Trade-offs:** Requires exactly one new server-side operation
(`split_region`/`merge_regions` in `masks.py`) beyond what exists today, and a
small client-side decoder/renderer. In exchange: there is exactly one
implementation of "how a freehand cut becomes a relabel" (in Python, reusing the
already-validated array representation), so the §3 exclusivity/exhaustiveness
invariants can never drift between a client and server implementation of the
same operation. The cost is that every commit requires a round trip before the
UI shows the "official" result — acceptable because commits are discrete,
human-paced actions (mouse-up), not per-frame events.

### Pattern 3: Revision counters for cache invalidation, not re-computation

**What:** `Volume.palette_revision` and (new) `Panel.label_map_revision` are
monotonic counters, already partly implemented in `store.py`
(`update_palette_rgb` already bumps `palette_revision`; `panels_affected_by`
already exists to compute the precise affected set). A render cache for
panel previews is keyed by `(panel_id, label_map_revision, palette_revision)`.
Editing a palette entry's RGB never touches a `Region` row or a label map —
it only bumps the counter, invalidating the *rendered pixel cache*, never a
*pipeline stage output*.

**When to use:** Any time a change only affects how existing data is displayed,
not what the data means. This is the mechanism behind "edit one palette entry
→ every affected panel updates" (§6) without re-running any stage.

**Trade-offs:** `palette_revision` is volume-global, so it invalidates every
panel's render cache on any single palette edit, even panels that don't
reference the edited entry — a deliberately coarse, cheap-to-check
invalidation. Use the existing `panels_affected_by(palette_entry_id)` query
only for the *precise* set when actively pushing a "please refresh" WebSocket
notice to open editor tabs; do not use it for cache-key correctness, where the
coarse counter is sufficient and requires no query.

## Data Flow

### Geometry edit → invalidation → re-run

```
Artist drags a panel-polygon vertex (web UI)
    ↓ POST /panels/{id}/polygon  {vertices: [...]}
web/routers/panel.py
    ↓ model.store.update_panel_polygon(...)      [existing Store method, extend]
    ↓ pipeline.runner.invalidate_from(panel_id, "segment")
pipeline/ marks segment, colour_propose, snap, triage rows STALE for this panel only
    ↓ (background) pipeline.runner.run_stale(panel_id)
segmentation/segmenter.py → model/masks.py (new label map) → colour/ (re-propose) → snap
    ↓ WS push: "panel {id} updated"
frontend refetches label-map raster + colour preview for that panel only
```

### Freehand split ("trace to split")

```
Artist drags a freehand stroke inside a zone (canvas, client-side)
    ↓ live preview drawn on a separate canvas layer — no network call
Artist releases mouse (commit)
    ↓ POST /panels/{id}/regions/split  {label: N, stroke: [[x,y], ...]}
web/routers/panel.py
    ↓ model.masks.split_region(label_map, label=N, stroke=...)   [NEW function]
      — rasterises stroke onto the panel's label-map array, clips it to the
        target region's footprint, runs connected-components on the remainder,
        assigns two new sequential labels
    ↓ model.masks.check_coverage(...)   [existing — re-verify exhaustiveness]
    ↓ store.set_label_map_path / persist updated .npz
    ↓ pipeline.runner.invalidate_from(panel_id, "colour_propose")
      (new zone has no palette_entry_id yet — surfaces in triage as unassigned)
    ↓ response: updated label raster (patch for the stroke's bounding box)
frontend updates only the affected pixels of its decoded typed array
```

### Palette edit → propagation (no pipeline re-run)

```
Artist edits a PaletteEntry's rgb (colour-correction view)
    ↓ POST /palette/{id}  {rgb: [r,g,b]}
web/routers/palette.py
    ↓ model.store.update_palette_rgb(entry_id, rgb)   [EXISTING — already bumps
      palette_entry.revision and volume.palette_revision]
    ↓ affected = model.store.panels_affected_by(entry_id)   [EXISTING]
    ↓ WS push to each affected panel_id: "recompute preview"
frontend / export.render.py: rgb_image = palette_lut[label_map]   (pure numpy,
  milliseconds; no stage in pipeline/ is touched, no label map is touched)
```

### Export

```
Artist clicks Export
    ↓ POST /pages/{id}/export  {mode: "per_colour" | "flat" | "per_zone"}
web/routers/export.py
    ↓ export.render.py: for each Panel, label_map + palette → per-colour RGBA
      rasters at 2-4x working resolution, feathered under line art, downsampled
    ↓ export.psd.py: psd-tools PSDImage — one create_group() per panel, one
      PixelLayer.frompil() per colour, positioned at panel bbox
    ↓ .psd file written; download link returned
(No pipeline/ involvement — export is a pure read over model/ + a
 deterministic render, safely re-run any number of times.)
```

## Anti-Patterns

### Anti-Pattern 1: Client-owned polygon geometry as the editable source of truth

**What people do:** Vectorise the label map (marching squares / `cv2.findContours`)
once, ship polygons to the browser, let the client perform all edits (including
freehand splits) as client-side polygon boolean operations, and sync the final
polygon set back to the server.

**Why it's wrong:** A freehand "trace to split" stroke is not a clean polygon —
it can self-intersect, run off the region's boundary, or leave gaps, and turning
it into a valid split requires exactly the connected-components/relabel logic
`masks.py` already implements on arrays. Reimplementing that as client-side
polygon clipping (a notoriously fragile class of computational geometry —
robustness/winding-rule bugs are why dedicated libraries like Clipper exist)
means maintaining two independent implementations of the same operation, one of
which (the client's) cannot itself enforce §3's exclusivity/exhaustiveness
invariant, since that invariant is structural to the *array* representation, not
to a polygon set. The server would still need to rasterise the client's final
polygons back into a label map to persist and to run downstream stages —
making the polygon round trip a lossy, redundant detour rather than a
simplification.

**Do this instead:** Vector polygons are fine as a *read-only rendering aid*
(e.g., drawing crisp boundary outlines at any zoom level) but the array stays
authoritative and server-side for every mutation. See Pattern 2.

### Anti-Pattern 2: Round-tripping every hover/mousemove event to the server

**What people do:** Keep the label map exclusively server-side and query it for
every UI interaction, including continuous events like hover-highlight or a
freehand-stroke drag, over HTTP or WebSocket per event.

**Why it's wrong:** A freehand stroke fires pointer events at up to 60/s; even
on localhost, per-event request/response (interpreter dispatch, (de)serialisation,
numpy array indexing) adds latency that is very perceptible for a drawing
interaction, and either throttling the events (making the stroke feel laggy) or
flooding the local server thread are both worse than the alternative below.
Verified precedent: annotation tools with brush/freehand tools (CVAT's Brush/Mask
tool) render the stroke client-side and only commit the result, rather than
round-tripping the paint operation itself.

**Do this instead:** Decode the label raster client-side once per panel open
(cheap: even a worst-case whole-page panel at ~17.5M pixels packs into a small,
highly-compressible PNG, and unpacks to at most ~35MB as a `Uint16Array`, well
within a browser tab's budget for the single panel currently open). Use it for
all read/hover/preview interactions; reserve the network round trip for the
discrete commit action only.

### Anti-Pattern 3: Loading Cobra/PixArt inside the FastAPI process

**What people do:** Import `torch`/`diffusers` and instantiate the Cobra
pipeline directly inside the same process that serves HTTP requests, as a
module-level singleton.

**Why it's wrong:** Couples a multi-GB CUDA context's lifetime to the web
server's process lifetime — a crash or OOM in a colourisation job (a real risk
given VRAM pressure is explicitly a concern) takes down panel/zone editing too,
even though those share nothing but the OS process. Any dev-mode autoreload of
the web server (common during iteration) reloads the multi-GB model
unnecessarily. It also fights FastAPI's async model: GPU inference must be
pushed off the event loop (thread pool or subprocess) regardless, so
in-process placement buys nothing over a separate process and loses crash
isolation. This is also the direction opposite to the stated future move to a
remote server — an in-process singleton has to be *removed* to add a network
seam later, whereas a separate worker process already speaks over a boundary
that can be pointed at a remote host with no code change.

**Do this instead:** A long-lived `worker/` process, started independently,
that loads Cobra once and exposes a narrow job interface (submit / poll) that
the web server calls over local HTTP. See "Where the diffusion model lives"
below.

## Explicit Invariant Preservation

Every new component must preserve these, unmodified, from the existing codebase:

- **Regions store `palette_entry_id`, never RGB.** `colour/snapping.py` writes
  only `palette_entry_id` (creating a new flagged `PaletteEntry` when distance
  exceeds threshold, never writing RGB onto a `Region`). `export/render.py`
  is the *only* place a `Region` is ever resolved to a pixel colour, and it does
  so by joining through `PaletteEntry` at render time — it must never cache an
  RGB value on the `Region` row itself, only in an ephemeral, revision-keyed
  render cache external to the data model (Pattern 3).
- **Regions within a panel are mutually exclusive via one label map.** The new
  `split_region`/`merge_regions` operations in `masks.py` must remain relabels
  of the single int32 array — never introduce a second parallel mask
  representation (e.g., per-region boolean layers) anywhere in `pipeline/`,
  `web/`, or `export/`. The label map on disk (`.npz`) remains the one and only
  persisted geometry; the client's decoded typed array is a disposable, refetch-
  able read cache, never itself persisted or treated as authoritative.
- **Segmenters stay swappable behind the `Segmenter` protocol.** `pipeline/`'s
  `segment` stage must invoke segmentation through the existing protocol
  (`TrappedBallSegmenter` / `LineFillerSegmenter`, or a future Tier 3 adapter)
  rather than hardcoding a call to one implementation — the stage registry
  entry should take a `Segmenter` instance as a parameter, exactly as
  `spike/ab.py` already does.
- **No new component modifies `entities.py`'s dataclass shapes.** All new
  functionality — stage tracking, job status, render caching — is additive
  (new tables such as `PanelStageRun`, new columns such as
  `Panel.label_map_revision`) alongside the existing schema, never a change to
  the §3 shapes themselves. Confirmed feasible for every question posed: no
  recommendation above requires an `entities.py` or SQLite schema change beyond
  pure additions.

## Where the Diffusion Model Lives (Q4 detail)

**Recommendation: a separate, long-lived local worker process — not an
in-process singleton, not a subprocess-per-job.**

| Option | Model load cost | Crash isolation | Fit with future remote move |
|---|---|---|---|
| In-process singleton in `web/` | Paid once, but reload on every dev autoreload/crash | None — a CUDA fault takes the whole app down | Must be removed/refactored later |
| Subprocess per job | Paid **every job** (multi-GB load, tens of seconds) — unacceptable given dozens of panels/page | Good | Poor — still needs a persistent-process rewrite for real throughput |
| **Separate long-lived worker process (recommended)** | Paid once per app session | Worker crash leaves editing fully usable | The worker already speaks over a boundary; pointing it at a remote host is a config change |

Confirmed pattern: local Stable-Diffusion-family UIs (Automatic1111, ComfyUI)
universally keep the model resident in a persistent process and serve inference
over a local API rather than reloading per request (MEDIUM confidence,
verified via current comparisons of the two tools' architectures). FastAPI's
own guidance for long GPU jobs is the same shape: a POST that enqueues and
returns immediately, a GET that polls status, with the actual inference in a
worker rather than the request-handling thread (MEDIUM confidence, verified via
current FastAPI-plus-GPU deployment guides).

For v1 (single-user, single-machine): no message broker (Redis/Celery) is
justified — reuse the same SQLite job-table pattern already recommended for
`pipeline/` (Pattern 1) for the worker's queue, keeping the "ultra simple"
constraint from `PROJECT.md` intact. The worker's request/response shape
(Pydantic models over local HTTP) should be designed as if the worker were
already remote, so that adding a hosted tier later is a deployment change, not
an architecture change — directly serving the "Local web app rather than
desktop or hosted" key decision already logged in `PROJECT.md`.

## Export Composition (Q6 detail)

**Library:** `psd-tools` (verified, MEDIUM confidence — its group/layer creation
API is documented as experimental, not its read path). It supports
`PSDImage.create_group()` for groups and creating a `PixelLayer` from a PIL
image, and `psd.save()` to write the file back out. `pytoshop` was also
surveyed and rejected: its nested-layer-group write support is less mature and
less documented than psd-tools' higher-level API (MEDIUM confidence).

**Split into two modules with different testability profiles:**
- `export/render.py` — pure numpy/opencv, no PSD dependency. Takes a label map
  + palette lookup + line art, produces per-colour RGBA rasters at 2-4x working
  resolution (per spec §10's anti-aliasing guidance), with a small dilation/
  feather under line-art pixels before downsampling to avoid the same
  fringing/halo problem the spec explicitly warns diffusion output causes
  (§9) — here applied to the flat-fill edge rather than model output.
  **Testable with golden-image / numeric assertions, no PSD or Photoshop
  involved:** e.g., assert no colour bleeds past N px of a line pixel, assert
  full opacity inside a region and zero outside.
- `export/psd.py` — assembly only: one `create_group()` per `Panel`
  (positioned at the panel's page-relative bbox), one `PixelLayer` per colour
  (or per zone, or a single flat layer, depending on export mode) inside each
  group, plus the panel's line-art layer.
  **Testable without opening Photoshop:** round-trip the written PSD back
  through `psd-tools`' own reader and assert structurally (group count equals
  panel count, layer count per group equals expected colour count, each
  layer's pixel data matches what was written). This is strong but not
  complete evidence, since `psd-tools` is an independent from-spec
  implementation, not Photoshop's engine (MEDIUM confidence) — recommend one
  manual Photoshop/Clip Studio smoke-test per milestone, not per commit, given
  Raph has both applications and no tester is ever unsupervised (`PROJECT.md`
  Out of Scope).

## Scaling Considerations

v1 is explicitly single-user, single-machine (`PROJECT.md` constraints), so
"scale" here means per-page/per-panel size, not concurrent users.

| Concern | Typical panel | Worst case (full-bleed page, 3500×5000) |
|---|---|---|
| Label-map raster to browser | Sub-megabyte packed PNG, well under 100ms decode | ~35MB decoded `Uint16Array`; still a single in-memory typed array, fine for one open panel |
| Canvas/WebGL size limits | No issue | Within Chrome's 16384px texture ceiling (MEDIUM confidence — Firefox has reported smaller limits on some hardware; verify on the actual target machine since v1 has exactly one) |
| Freehand split compute | Milliseconds (bounding-box-scoped connected components) | Still bounded by panel bbox, not full page, if scoped correctly in `split_region` |
| Diffusion worker VRAM | One panel in flight at 384-512px per spec §1.6 | No batching needed for a single-user queue; FIFO is sufficient |
| Export PSD layer count | ~10 colours × ~10 panels ≈ 100 layers (per spec §2.3, confirmed against a working colourist) | Not a volume concern per spec |

### Scaling Priorities

Given the deliberate "latency and throughput work" is Out of Scope
(`PROJECT.md`), the only priority worth flagging is: **panel size, not page
count or concurrent users, is the one dimension that could actually strain this
architecture** (a very large full-bleed splash panel pushes every number in the
table above to its ceiling simultaneously). If this becomes a real problem, the
mitigation is windowed/tiled fetch of the label raster (only the visible
viewport, not the whole panel) — deferred until it is observed to matter, not
built speculatively.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---|---|---|
| Cobra / PixArt (via `diffusers`) | Wrapped as a black box inside `colour/cobra.py`, invoked only from `worker/`; `from_pretrained` pulls PixArt weights from the `openrail++`-licensed HF repo per the spec's resolved P1 | Pin the dependency path deliberately (spec §2.1) — do not let it resolve to the AGPL raw-`.pth` mirror |
| `hepesu/LineFiller`, `MangaLineExtraction` | Already vendored in `third_party/`, wrapped behind existing protocols | No change needed for this milestone |
| `psd-tools` | New dependency, `export/psd.py` only | MIT-licensed (compatible with the open-source intent); confirm licence at add-time regardless |

### Internal Boundaries

| Boundary | Communication | Notes |
|---|---|---|
| `web/` ↔ `pipeline/` | Direct in-process function calls | `web/` never touches `model/` or `segmentation/` directly for anything the pipeline registry already governs |
| `web/` ↔ `worker/` | Local HTTP (or equivalent local RPC), designed remote-ready | Only boundary in the system deliberately built to survive being pointed at a different host later |
| `pipeline/` ↔ `segmentation/`, `extract/`, `colour/`, `protect/` | Direct calls through existing protocols (`Segmenter`, `LineExtractor`) and new ones (`ProtectedMaskDetector` if/when a real detector replaces manual masking) | Registry holds references to protocol instances, not concrete classes |
| `export/` ↔ `model/` | Read-only queries (`Store.regions_for_panel`, `Store.palette_for_volume`, `masks.load_label_map`) | Never writes back to `model/`; safe to re-run any number of times |
| Frontend ↔ `web/` | HTTP for CRUD/export/commit, WebSocket for push notifications on stage completion or palette propagation | The only network boundary exposed to the browser |

## Sources

- Existing codebase: `src/comiccolor/model/masks.py`, `model/entities.py`,
  `model/store.py` (read directly — HIGH confidence, these are ground truth)
- `flatting-pipeline-spec.md` §3 data model, §9 anti-patterns, §10 known hard
  cases, §2.3 P4 export resolution (HIGH confidence — resolved project spec)
- [psd-tools documentation](https://psd-tools.readthedocs.io/) — group/layer
  creation API (MEDIUM confidence, documented as experimental)
- [pytoshop nested_layers module](https://pytoshop.readthedocs.io/en/latest/_modules/pytoshop/user/nested_layers.html) — surveyed, less mature write support than psd-tools (MEDIUM confidence)
- [Mozilla Bugzilla — WebGL MAX_TEXTURE_SIZE variance across hardware/drivers](https://bugzilla.mozilla.org/show_bug.cgi?id=986871), [Canvas 2D coordinate/size limits](https://www.tutorialspoint.com/article/maximum-size-of-a-canvas-element-in-html) (MEDIUM confidence, hardware/browser-dependent — verify on the actual v1 machine)
- [CVAT segmentation annotation tooling — Brush/Mask tool vs. polygon tool as separate, purpose-specific interaction modes](https://www.cvat.ai/academy/brush-mask-annotation), [CVAT mask format](https://docs.cvat.ai/docs/dataset_management/formats/format-smask/) (MEDIUM confidence — used as precedent for raster-based freehand editing, not a direct architectural citation)
- [ComfyUI vs Automatic1111 architecture comparisons — persistent process, model resident in VRAM, API-first design](https://apatero.com/blog/comfyui-vs-automatic1111-complete-migration-guide-2025) (MEDIUM confidence — third-party comparison articles, not the projects' own architecture docs)
- [FastAPI + GPU inference deployment guidance — job queue pattern, async + thread pool for CUDA ops](https://hamel.dev/notes/serving/fastapi/) (MEDIUM confidence — practitioner guidance, not official FastAPI docs)

---
*Architecture research for: local-first web app over a deterministic segmentation + diffusion-proposer pipeline*
*Researched: 2026-08-02*
