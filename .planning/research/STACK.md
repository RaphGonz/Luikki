# Stack Research

**Domain:** Local-first web application layer (canvas-heavy editors, GPU colour-proposer integration, layered PSD export) on top of an already-validated Python colour-flatting core
**Researched:** 2026-08-02
**Confidence:** MEDIUM-HIGH (backend/PSD/colour findings verified against PyPI/GitHub/official docs; Cobra VRAM figures and exact frontend performance numbers are LOW confidence estimates flagged below)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **FastAPI** | 0.115+ | Backend API: uploads, project/palette CRUD, job orchestration, streaming progress | Async-native (SSE/WebSocket for progress without extra libraries), Pydantic validation for the §3 data model at the API boundary, and — critically — it does not force a UI paradigm onto a bespoke canvas editor. It is also the literal foundation of NiceGUI and Reflex, so choosing it directly loses nothing and keeps the option to bolt on a real frontend. Deploys unchanged to a Linux server later (`uvicorn`/`gunicorn`, same ASGI app). HIGH confidence. |
| **Vite + TypeScript** (vanilla, no reactive framework for the canvas view) | Vite 6.x / TS 5.x | Build tooling and the two editor screens (panel-polygon editor, zone editor) | The editors are imperative, event-driven canvas code (drag vertex, trace freehand stroke, click-to-merge) — exactly the case where a virtual-DOM reactive framework (React/Svelte) adds translation overhead for no benefit. A thin Vite+TS SPA served as static files by FastAPI keeps the whole app in one deployable unit. MEDIUM confidence (opinionated, not the only valid choice — see Frontend Framework Choice below). |
| **Konva.js** | 9.x | 2D canvas engine for both editors (polygon vertices, zone-merge clicks, freehand split strokes) | Purpose-built for exactly this interaction model: object-based hit-testing, drag handles, and a stage/layer event system, on top of the plain 2D Canvas API (no WebGL context management to fight). Community consensus (2026 comparisons) is consistent: Konva for interactive editing UIs, PixiJS/WebGL for animation-heavy rendering. HIGH confidence for the *interaction* layer; see the Label-Map Transport pattern below for how the large raster itself should be handled (not as thousands of Konva shapes). |
| **psd-tools** | 1.17.4 (current, released 2026) | Write the layered PSD export: nested groups (one per panel), many layers per group, Photoshop/CSP compatibility mode | **Confirmed via PyPI wheel metadata and official docs: this is a WRITE-capable library, not read-only.** `PSDImage.new()`, `create_pixel_layer()`, `create_group()`, `Group.append()`, and `PSDImage.save()` form a complete authoring API, merged in PR #428 (Sept 2024) and released starting at 1.10.0. `PSDImage.compatibility_mode` lets you target Photoshop or CLIP Studio Paint compositing conventions explicitly — directly answers the P4 "PSD, one group per panel" requirement. MIT licence. No numpy version pin (verified in wheel METADATA: `Requires-Dist: numpy` with no constraint) — safe alongside the existing `numpy>=2.0`. HIGH confidence. |
| **skimage.color** (scikit-image) | 0.24+ (0.25 as of late 2025) | RGB→CIELAB conversion for palette snapping | Already an effective transitive dependency (`scikit-image` provides `skeletonize()`, used in `segmentation/closure.py`, per existing STACK.md) — using its `rgb2lab`/`lab2rgb` avoids adding a second colour-science dependency for a conversion this codebase already has installed. BSD-3-Clause, numpy>=2.0 compatible. The custom "L\* downweighted ~0.3" distance in §1.7 is **not** a standard Delta E formula (CIE94/CIEDE2000 have their own built-in L-weighting curves, not a flat scalar) — hand-roll a weighted Euclidean distance in Lab space (`sqrt((0.3*dL)**2 + da**2 + db**2)`) directly with numpy; this is a 5-line seam, not a library problem. HIGH confidence. |
| **opencv-python-headless** (already a dependency) | >=4.10 (existing pin) | Swatch-chip grid detection: contour/connected-component extraction of flat colour chips from an uploaded swatch strip | No purpose-built "extract colour chips from a gridded swatch image" library was found on PyPI — this is a seam, not a gap in the ecosystem, and it is a straightforward application of tools already in the stack: threshold the swatch image, find external contours or connected components (`cv2.findContours` / `cv2.connectedComponentsWithStats`), take the per-chip modal colour (same mode-extraction pattern as §1.7's per-region colour, for consistency). Do not add a new dependency here. HIGH confidence (absence of a purpose-built library verified by search; approach follows an established, well-documented OpenCV pattern). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sse-starlette` or FastAPI's native `StreamingResponse` | 2.x | Push job progress (Cobra inference, PSD export) to the browser | Server-Sent Events are simpler than WebSockets for one-directional progress updates and need no extra client library beyond `EventSource`. Use a WebSocket only if the zone editor ever needs true bidirectional low-latency traffic (it currently does not — merges/splits are request/response). |
| `python-multipart` | 0.0.9+ | FastAPI file upload support (pages, character sheets, swatch images) | Required by FastAPI's `UploadFile` — easy to forget, install explicitly. |
| `Pillow` (existing dependency) | >=11.0 (existing pin) | PIL Image objects are what `psd-tools`'s `create_pixel_layer()` consumes directly | No new dependency — reuse the existing pin. |
| `subprocess` + a **second, isolated virtual environment** for Cobra | stdlib | Run Cobra's exact pinned dependency set (`torch==2.5.1`, `numpy==1.26.4`) without touching the main interpreter | See Cobra Integration section below — this is a hard requirement, not a style preference. |
| `concurrent.futures.ThreadPoolExecutor(max_workers=1)` or a single dedicated worker thread + `queue.Queue` | stdlib | Background job runner for GPU inference and PSD export | See Background Jobs section below. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `esbuild`/Vite dev server | Frontend hot-reload during development | Vite proxies API calls to the FastAPI dev server (`uvicorn --reload`) on a different port; in production, FastAPI serves the built static assets directly via `StaticFiles`, so there is exactly one process to run. |
| `httpx` | Testing the FastAPI routes | Already the natural pairing with FastAPI's `TestClient`; add to `dev` extras alongside `pytest`. |

---

## PSD Writing — Answered Definitively

This was the highest-uncertainty question and needed to be resolved without ambiguity, since grouped-layer **write** support is a hard requirement.

| Library | Read | Write pixel layers | Write nested groups | Maintenance | Licence | Verdict |
|---|---|---|---|---|---|---|
| **psd-tools** 1.17.4 | Yes | **Yes** (`create_pixel_layer`) | **Yes** (`create_group`, `.append()`) | Active — latest release 2026, PyPI shows continuous 1.17.x line through 2025-2026, write support merged Sept 2024 | MIT | **Use this.** |
| pytoshop | Yes | Yes (lower-level, packbits-based) | Awkward — no first-class group/append API comparable to psd-tools 1.10+ | **Inactive** — no PyPI release in 12+ months per package-health scan (Snyk); a community fork `pytoshop-fix-packbits` exists but only patches a packbits bug, does not add features | MIT | Do not use — superseded by upstream psd-tools now that psd-tools itself gained write support. |
| psd_tools2 / psd_tools3 | Yes | Partial (community forks of pre-1.0 psd-tools) | No dedicated group-creation API found | Low-activity forks that existed to patch gaps in old psd-tools; those gaps are now closed upstream | MIT (inherited) | Do not use — historical forks, now redundant. |
| Hand-rolled packbits writer | N/A | Full control | Full control | N/A (your own code) | N/A | Not needed — psd-tools' documented write API already covers one-group-per-panel, many-layers-per-group. Only fall back to this if a specific PSD feature (unlikely for flat colour layers) proves unsupported in practice. |

**One caveat to carry forward, not a blocker:** psd-tools' own *compositing/preview* renderer (`PSDImage.composite()`) is explicitly documented as producing output that "is likely different from Photoshop's rendering" — this refers to psd-tools' own Python-side preview flattening (used if you want a thumbnail without opening Photoshop), **not** to whether Photoshop/CSP will correctly read and composite files this library writes. Since psd-tools writes a structurally-correct native PSD, and Photoshop/CSP do their own compositing when the artist opens the file, this caveat does not block the P4 requirement. It does mean: do not rely on `psd_tools`' own `.composite()` for any in-app preview of the exported file — render your own preview from the source layers before export instead, if a preview is ever needed.

Set `PSDImage.compatibility_mode` explicitly per export target (Photoshop vs CLIP Studio Paint) since P4 established both applications must open the file correctly and they handle group/clipping semantics differently.

---

## Frontend Approach for the Editors

### The two editing surfaces have different demands

1. **Panel-polygon editor** — small vertex count (tens, not thousands), needs drag/add/delete-vertex and draw-from-scratch. This is comfortably within Konva's design centre: vector shapes with per-point drag handles.
2. **Zone editor** — operates over a *raster* (the per-panel int32 label map), not a small vector shape list. A region can be one of hundreds of irregular blobs at up to 3500×5000px. This is the harder case and needs its own pattern.

### Library comparison

| Library | Rendering | Fit for polygon editor | Fit for zone editor (label-map hit-test) | Maintenance | Licence |
|---|---|---|---|---|---|
| **Konva.js** | 2D Canvas, object model | **Best fit** — built-in drag/transform handles, event bubbling, hit-testing per shape | Good, if the label map itself is *not* represented as thousands of Konva shapes (see pattern below) | Active (regular releases through 2025-2026) | MIT |
| Fabric.js | 2D Canvas, object model | Good — comparable object model, historically stronger for full "design tool" feature sets (SVG import/export, richer text/image handling) | Same caveat as Konva — not meant to hold a full-resolution label raster as individual objects | Active | MIT |
| PixiJS | WebGL | Weak — its interaction/hit-testing framework is comparatively minimal; it exists to push pixels fast (animation/games), not to manage draggable editing handles | Good for *raw draw throughput* of the underlying raster/texture, poor for building the merge/split UI on top | Active | MIT |
| paper.js | 2D Canvas, vector-math focused | Reasonable for polygon math (boolean ops on the roadmap, not confirmed shipped) | Not suited — no raster/label-map story | Low-activity but not abandoned (issues still triaged into 2026) | MIT |
| OpenSeadragon + Annotorious | Tiled deep-zoom viewer | Overkill | Overkill — this stack exists for gigapixel whole-slide/map imagery (tens of thousands of px); a 3500×5000 comic page does not need tile pyramids | Active | BSD-3 (OSD) / BSD-3 (Annotorious) |

**Recommendation: Konva.js for both editors**, but the zone editor must NOT model the label map as one Konva shape per region — see the transport/hit-test pattern below, which is the actual answer to "how should this work at 3500×5000px."

### Label-map transport and hit-testing — the actual design question

Do not send the raw int32 label array to the browser as JSON (a 3500×5000 page is ~17.5M cells; even at 4 bytes each that's 70MB uncompressed and pointless to parse in JS). Do not create one interactive Konva shape per region either (a page can have hundreds of regions per panel; per-shape overhead compounds badly, and Konva's own performance guidance is explicit that object count is the main cost).

The established pattern (used by segmentation/annotation tools generally, e.g. Segments.ai's mask format) is:

1. **Server-side**: keep the int32 label array as the single source of truth (already the case per the existing `masks.py` model — do not change this).
2. **Encode for transport**: pack each label id into the RGB channels of a PNG (24 bits = up to ~16.7M distinct ids, far beyond what one panel needs), alpha channel fixed at 255, background/protected pixels at id 0. PNG's lossless run-length-friendly compression is a very good fit for label maps — flood-fill segmentation produces large flat-colour blobs, which PNG compresses aggressively (typically far under 1MB even at full page resolution, verify empirically per page).
3. **Client-side hit-testing**: decode the PNG once into a `<canvas>` and read pixels via `getImageData()`; a click event does an O(1) local lookup (unpack the RGB triplet back into the id) with zero network round-trip. This is what makes click-to-merge feel instant.
4. **Freehand split-stroke**: the browser only needs to render the stroke path for feedback — send the traced polyline (a few hundred points, not pixels) to the server, and let the server (which already has scipy/opencv/numpy) rasterize the cut against the authoritative label array and return an updated PNG. This matches the invariant that a split "changes the label map only" — the authoritative mutation happens server-side, never in client state.
5. **Merge**: client already knows both ids from local hit-testing; send a small `{a_id, b_id}` request, server relabels and returns the updated PNG.

This design keeps the browser's canvas layer doing exactly two things — rendering the current PNG as a texture/background and doing local pixel-lookup hit-tests — while all label-map mutation logic stays server-side, reusing code that's already validated (existing `masks.py` relabel-on-split logic per PROJECT.md). Confidence: MEDIUM — this is a synthesis of established patterns (segmentation-mask PNG encoding is well precedented) applied to this specific project's data model, not a single authoritative source; validate PNG size empirically on a real 3500×5000 page during Phase 0 of the relevant phase.

### Frontend framework choice (React/Svelte vs vanilla)

Vanilla TypeScript is recommended for the two canvas-editor views specifically, because their state (current tool, selected vertex, drag origin, undo stack) is naturally imperative and event-driven — wrapping Konva in React's reconciliation model (`react-konva`) adds a translation layer for state that changes on every `mousemove`. For the surrounding application shell (project list, palette manager grid, colour-correction view — all of which are much more "forms and lists"), a lightweight component framework (Svelte is a reasonable choice if the shell grows past a handful of views) is fine and does not need to share a rendering model with the canvas — mount the vanilla Konva editor as a self-contained component/custom element inside whichever shell is chosen. Do not default to React for this project: its ecosystem weight buys nothing here and the canvas code fights it more than plain Vue/Svelte/vanilla.

**Do not use a pure-Python UI framework (NiceGUI, Streamlit, Gradio, Reflex) for the canvas editors specifically.** All of them either run Python-side event handlers over a network round-trip per interaction (fine for buttons/forms, too slow/awkward for continuous drag/freehand-stroke feedback) or require "escape hatches" (`ui.run_javascript` + `add_head_html` script injection, confirmed as NiceGUI's own documented pattern for third-party JS libraries) to embed a real canvas library at all — at which point you are still writing and maintaining the Konva/JS code directly, just through an extra indirection layer that adds friction without adding capability. This is a case where the "standard 2026 stack" genuinely is FastAPI + a real frontend, not a Python-only shortcut; save NiceGUI/Streamlit for internal tooling (e.g. an ops dashboard for the metrics in §5) where their form-first model is a good fit, not for the product's core interactive surface.

---

## Cobra Integration Surface

Verified directly from `github.com/zhuang2002/Cobra`'s `requirements.txt` (fetched 2026-08-02) and README:

```
torch==2.5.1
torchvision==0.20.1
numpy==1.26.4
transformers==4.48.3
accelerate==1.5.2
peft==0.15.0
diffusers   ← installed as `-e ./diffusers`, i.e. an editable install of a VENDORED FORK
             bundled inside the Cobra repo itself, not the stock `pip install diffusers` package
gradio==5.22.0
opencv-python==4.11.0.86
Pillow==11.1.0
```
Python: 3.11.11 (pinned via conda in the README's setup instructions). Licence of Cobra's own code: Apache-2.0 (the model weights/deltas are what carry OpenRAIL++-M via the PixArt pull, per the already-resolved P1 in the spec — code licence and weight licence are separate).

### Hard dependency conflict — confirmed, not hypothetical

**`numpy==1.26.4` is pinned exactly**, directly conflicting with this project's `numpy>=2.0`. This is not resolvable by "just installing a compatible range" — Cobra pins an exact old version, almost certainly because its vendored `diffusers` fork or `transformers==4.48.3` era code relies on pre-2.0 numpy behaviour somewhere in the dependency chain. `torch==2.5.1` and `transformers==4.48.3` are also exact pins, and the `-e ./diffusers` editable install means Cobra is not using stock `diffusers` at all — it has patched the library itself (very likely to add the LoRA/ControlNet delta-loading and the causal-sparse-attention KV-cache described in the paper). None of this can safely coexist in the same Python interpreter/virtualenv as the existing `numpy>=2.0` / `opencv-python-headless>=4.10` / `scipy>=1.14` stack.

**Required architecture: isolate Cobra in its own virtual environment (or conda env), invoked as a subprocess, never imported in-process.** This is not extra ceremony for its own sake — it is the only way to satisfy both dependency sets simultaneously, and it is also exactly what the spec's "wrap as a black box, do not modify the DiT" instruction already implies architecturally. Concretely:
- Create a second environment (`conda create -n cobra python=3.11.11` per the README, or a `venv` if conda is avoided) with Cobra's exact `requirements.txt`.
- Communicate across the boundary via the filesystem (write input line-art/reference images + a small JSON config to a temp path, invoke the Cobra environment's Python as a subprocess pointed at a small wrapper script, read back the output raster) — the simplest possible IPC, appropriate for "job takes minutes" latency, not a message bus.
- This isolation boundary is also a natural fit for the background-job design below: the "job" the job runner tracks *is* the subprocess call into the Cobra environment.

### VRAM — LOW confidence, not documented upstream

Neither the Cobra README, GitHub issues, nor the PixArt-XL-2-1024-MS model card state a VRAM figure. What is verifiable: the PixArt-XL-2-1024-MS transformer itself is ~0.6B parameters (confirmed on the HF model card) — small by DiT standards — but PixArt's default pipeline also loads a T5-XXL text encoder (~4.3B params), which is normally the dominant memory cost (commonly ~9-11GB in fp16 on its own for PixArt-alpha style pipelines). Whether Cobra's reference-image-conditioned mode still runs a live T5 branch, or bypasses/caches it (since Cobra's inputs are described as reference images and colour hints, not text prompts), is **not established from public documentation** — flagging as a genuine open question, not an assumption either way. Running at 384–512px (per this project's own plan, an order of magnitude cheaper than PixArt's native 1024px) reduces activation memory substantially regardless. Given "no CPU path in v1" is a firm constraint and this is the single highest-risk unknown in the whole stack, **treat VRAM measurement as a Phase 0 spike for whichever phase integrates Cobra** — do not size hardware or plan batch sizes against an assumed number. A single modern NVIDIA GPU with **at least 12GB VRAM** is a reasonable starting floor to test against, not a verified requirement.

---

## Background Job Handling

| Approach | Fit for this project | Notes |
|---|---|---|
| **`concurrent.futures.ThreadPoolExecutor(max_workers=1)` (or an equivalent single dedicated worker thread + `queue.Queue`), driven from FastAPI, with job status persisted in SQLite** | **Recommended for v1** | Single GPU means work is serialized anyway (`max_workers=1` mirrors physical reality, not an artificial limit) — there is no throughput to gain from a distributed queue on one machine with one user. FastAPI's own `BackgroundTasks` is not enough on its own for GPU-minutes-long jobs (it runs in the same process/event loop and offers no persistence across a restart), so use it only as the trigger that hands off to the thread-pool/queue, with job state (queued/running/done/failed, progress) written to the existing `Store` (SQLite) so a page refresh or crash mid-job is recoverable/inspectable. |
| Celery + Redis | Not recommended for v1 | Needs its own broker, result backend, and worker process management — real operational weight for a single-user, single-machine app. The complexity buys nothing until there are multiple concurrent users or multiple GPUs to schedule across. |
| `arq` | Not recommended for v1, reconsider at hosting-tier milestone | Technically the best async-native fit for FastAPI, but it requires Redis, and **Redis has no first-class native Windows support** (WSL2, Docker, or the newly-available Memurai Enterprise port are the only current options per Redis's own 2026 guidance) — unnecessary infrastructure friction on the Windows development machine this project runs on for v1. Revisit `arq` when/if the project moves to a hosted Linux server, where Redis is trivial; the job-status abstraction recommended above (submit/poll/status against a store) should be designed so swapping the worker implementation later is an internal change, not an API rewrite. |
| Plain `FastAPI BackgroundTasks` alone | Not recommended as the sole mechanism | Fine for genuinely short fire-and-forget work (e.g. a cleanup task), but GPU-minutes jobs block the same process, and nothing survives a server restart. Use it only as glue into the queue/thread-pool above. |

**Bottom line: the simplest thing that survives the later move to a server is exactly the thing that also matches this app's actual hardware (one GPU, one user) — a single-worker in-process queue with SQLite-backed job status, not a message broker.**

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Backend framework | FastAPI | NiceGUI | Good for the non-canvas screens in isolation, but its Python-side event model actively fights a bespoke drag/freehand canvas editor (confirmed: third-party JS libraries require `ui.run_javascript` + `add_head_html` escape hatches, not first-class support) — better to build the real frontend directly than to route around a framework built for a different problem. |
| Backend framework | FastAPI | Streamlit / Gradio | Script-rerun-on-interaction model (Streamlit) and component-slot model (Gradio, which Cobra's own demo already uses) are built for dashboards/model demos, not stateful multi-tool canvas editors with per-pixel interaction. |
| Backend framework | FastAPI | Flask | Comparable simplicity for basic routes, but native async/streaming (SSE for job progress) is a first-class FastAPI feature and an add-on in Flask; no reason to give this up when starting fresh. |
| Backend framework | FastAPI | Django | Batteries (ORM, admin, auth) are all solving problems this project has deliberately deferred (no accounts, no multi-user, existing hand-rolled SQLite `Store`) — Django's weight buys nothing here and its ORM would compete with the already-built data model. |
| Canvas library | Konva.js | Fabric.js | Comparable fit; Fabric leans slightly more "design-tool" (richer text/SVG import) which this project doesn't need. Either is defensible — Konva is chosen for its more explicit stage/layer separation, which maps cleanly onto "background raster layer + interactive vector overlay layer." |
| Canvas library | Konva.js | PixiJS (WebGL) | WebGL buys raw draw speed for animation-heavy scenes; this app's bottleneck is interaction/hit-testing UX, not frame-rate, and Konva's interaction model is the stronger fit for that. |
| CIELAB conversion | skimage.color | colour-science | colour-science (0.4.7, numpy 2.0 compatible, BSD-3) is a fine, more comprehensive alternative if the project later needs additional Delta E formulas (CIE94/CIEDE2000) as an actual metric rather than the custom weighted-Euclidean distance in §1.7 — but it's an extra dependency for a conversion scikit-image already provides. Switch if a future phase needs standardized Delta E reporting. |
| Job runner | Single-worker thread pool + SQLite status | `arq` + Redis | Reconsider specifically at the hosting-tier milestone, on a Linux server, where Redis is a non-issue — not for v1 on the Windows dev machine. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `pytoshop` | No PyPI release in 12+ months, effectively inactive; lacks psd-tools' first-class group/append write API | `psd-tools` >= 1.10 |
| `psd_tools2` / `psd_tools3` | Community forks that existed to patch gaps in pre-1.0 psd-tools; those gaps are closed upstream now | `psd-tools` (upstream) |
| `colormath` | Unmaintained since ~2014; broken under modern numpy (relies on `numpy.asscalar`, removed in numpy 1.17+, let alone numpy 2.0) — do not add this to a numpy>=2.0 codebase under any circumstance | `skimage.color` (primary) or `colour-science` (if richer Delta E formulas are needed later) |
| Importing Cobra's Python package directly into the main `comiccolor` interpreter | `numpy==1.26.4` / `torch==2.5.1` exact pins hard-conflict with `numpy>=2.0`; Cobra also uses a patched, non-stock `diffusers` fork (`-e ./diffusers`) | Isolated venv/conda env, invoked as a subprocess, per Cobra Integration section above |
| Celery + Redis for v1 | Broker/result-backend/worker-process operational weight with zero payoff on a single-machine, single-user, single-GPU app; Redis also has no clean native Windows story | `concurrent.futures.ThreadPoolExecutor(max_workers=1)` + SQLite-backed job status |
| One Konva shape per label-map region | Konva's own performance guidance flags object count as the primary cost driver; hundreds of regions per panel as live interactive shapes will not scale to 3500×5000px smoothly | RGB-packed label-id PNG + client-side `getImageData()` hit-testing (see pattern above) |
| OpenSeadragon + Annotorious | Built for gigapixel/tile-pyramid imagery (whole-slide microscopy, maps); a 3500×5000 comic page doesn't need deep-zoom tiling infrastructure | Konva.js directly on the full-resolution raster |
| A pure-Python UI framework as the home for the canvas editors specifically (NiceGUI/Streamlit/Gradio/Reflex) | All require network-round-trip or JS-escape-hatch patterns for anything beyond forms/buttons; confirmed via each framework's own docs/community consensus | FastAPI backend + a real (vanilla TS or thin-framework) frontend using Konva |

## Stack Patterns by Variant

**If the surrounding app shell (project list, palette manager, colour-correction view) grows past a handful of screens:**
- Introduce Svelte (or another lightweight component framework) for those screens only
- Because they are genuinely list/form-shaped and benefit from component reactivity, unlike the two canvas editors — mount the vanilla-TS Konva editor as an isolated component/custom element inside whichever shell framework is chosen, don't force one rendering model across both halves of the app

**If/when the project reaches the hosting-tier milestone (multi-user, remote GPU):**
- Swap the in-process thread-pool job runner for `arq` + Redis (trivial on a Linux server)
- Because the job-status abstraction (submit/poll/status against a store) should already be designed as an internal seam, not because the v1 choice was wrong for v1

**If Cobra's actual VRAM usage during the Phase 0 spike exceeds the local GPU's capacity:**
- Fall back to reducing reference-image count per call (Cobra's own headline feature is scaling to 200+ references — fewer references trades identity-consistency quality for memory) before reaching for model quantization/offloading, since Cobra's README already mentions CPU-offloading-style options exist in the diffusers/PixArt lineage as a lever if needed
- Because this is architecturally free (it's a call-site parameter, not a dependency change) whereas quantization risks output-quality regressions in a component whose whole job is to be a *reliable* colour proposer

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `psd-tools==1.17.4` | `numpy>=2.0`, `Pillow>=11.0` | Verified directly from the published wheel's METADATA: `numpy` has no version constraint at all; `Pillow>=10.3.0` is satisfied by the existing `pillow>=11.0` pin. No conflict. |
| `skimage (scikit-image)` | `numpy>=2.0`, `scipy>=1.14` | Already implied by the existing use of `skeletonize()` in `segmentation/closure.py`; should be added to `pyproject.toml` explicitly rather than relying on it arriving transitively. |
| `colour-science==0.4.7` | `numpy>=2.0` | Confirmed: numpy 2 support has been present since the library resumed active releases; only relevant if adopted later per the Alternatives table above. |
| Cobra's pinned set (`torch==2.5.1`, `numpy==1.26.4`, `transformers==4.48.3`, editable `diffusers` fork) | **Incompatible** with `numpy>=2.0` / this project's main interpreter | Exact pins, not ranges — must live in a fully separate environment. See Cobra Integration section. |
| `colormath` (any version) | **Incompatible** with `numpy>=1.20`+ | Relies on removed numpy API (`numpy.asscalar`); do not install into this codebase at all. |

## Sources

- `github.com/zhuang2002/Cobra` — `requirements.txt` (fetched directly, 2026-08-02) and README setup instructions — HIGH confidence, primary source
- `huggingface.co/PixArt-alpha/PixArt-XL-2-1024-MS` — model card, transformer parameter count — HIGH confidence for the 0.6B figure; VRAM figure not stated, LOW confidence estimate only
- `psd-tools` PyPI wheel METADATA (`psd_tools-1.17.4-cp314-cp314-win_amd64.whl`), downloaded and inspected directly — HIGH confidence
- `github.com/psd-tools/psd-tools` PR #428 ("Layer structure edition and Group/PixelLayer Creation") — merged Sept 24, 2024 — HIGH confidence, primary source
- `psd-tools.readthedocs.io/en/latest/usage.html` and API reference (via Context7 `/psd-tools/psd-tools` and direct fetch) — HIGH confidence
- Snyk package-health advisor page for `pytoshop` — MEDIUM confidence (third-party aggregator, but consistent with GitHub's own inactivity signal)
- `github.com/colour-science/colour` releases and PyPI page (0.4.7, numpy 2 support) — MEDIUM-HIGH confidence
- Konva.js official performance-tips docs (`konvajs.org/docs/performance/All_Performance_Tips.html`) — HIGH confidence, primary source
- `redis.io/blog/redis-on-windows-10` and related 2026 Windows-Redis coverage — MEDIUM confidence (multiple independent sources agree: no clean native Windows path as of 2026)
- NiceGUI official docs (`nicegui.io/documentation/run_javascript`) and GitHub discussions on third-party JS integration — MEDIUM confidence (confirms escape-hatch pattern via primary docs)
- General WebSearch synthesis (FastAPI/NiceGUI/Streamlit comparisons, Konva/Fabric/PixiJS comparisons, arq/Celery/BackgroundTasks comparisons) — MEDIUM confidence, cross-checked against multiple 2026-dated sources; treated as ecosystem-consensus rather than single-source claims
- Segments.ai label-format docs (RGBA-encoded segmentation bitmap pattern) — MEDIUM confidence, used as precedent for the label-map transport design, not a direct dependency recommendation

---
*Stack research for: local-first web application layer for comic/manga colour flatting (ComicColor)*
*Researched: 2026-08-02*
