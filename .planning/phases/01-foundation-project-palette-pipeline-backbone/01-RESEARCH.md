# Phase 1: Foundation — Project, Palette & Pipeline Backbone - Research

**Researched:** 2026-08-10
**Domain:** Local-first FastAPI + vanilla-TS web app over an existing SQLite/dataclass model; deterministic palette extraction; declarative pipeline-stage backbone
**Confidence:** MEDIUM-HIGH (backend/library findings verified live against PyPI/npm registries and official docs this session; a handful of design choices — schema shape for unbound reference images, exact adaptive-K merge threshold — are RESEARCH RECOMMENDATIONS for the planner to lock, not verified facts)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Project model**
- **D-01:** "Project" is the existing `Series` entity, renamed. The hierarchy becomes **Project → Volume → Page → Panel → Region**.
- **D-02:** **Palette and entities move up to project scope.** `palette_entry` and `entity` re-point from `volume_id` to `project_id`, and `volume.palette_revision` moves to the project row. This is a schema migration of `model/entities.py` + `model/store.py` + `tests/test_store.py`, not a rename.
- **D-03:** **Volume survives and is artist-visible.** No v1 requirement asks for volume grouping — this is a deliberate, user-confirmed addition. Keep its UI minimal: create, rename, delete, and assign pages.
- **D-04:** **Folder per project, database inside it.** A project is a directory the artist names, containing `project.db` plus asset subdirectories (pages, reference images, label maps). "Open project" is a folder pick. A small recent-projects list (outside any project, in app config) is a convenience index only and must never be authoritative over the folder.
- **D-05:** **Reference images bind to a character at accept time, not upload time.** Uploading a character sheet is one drag-and-drop with no prompts. The app asks for the character name only when the artist accepts palette proposals extracted from that sheet.

**Pipeline stage model**
- **D-06:** **The pipeline is forward-only with a confirmation gate at each stage.** No "stale downstream" concept anywhere in the system — the model never permits stale state to exist.
- **D-07:** **Gates are per page.** `page.stage` is a single value.
- **D-08:** **Going back is possible, but costed and explicit.** Before it happens the app states plainly what will be destroyed and re-run, in concrete terms, and requires confirmation.
- **D-09:** **Palette edits sit entirely outside the stage chain.** Recolouring a palette entry is never a stage regression at any stage. No warning, no confirmation, no re-run. Already implemented server-side by `store.update_palette_rgb()` + `store.panels_affected_by()`.
- **D-10:** **Declarative registry with a thin runner.** Each stage declares its name, its dependencies, what it produces, and a callable that runs it. Every stage stays individually triggerable and individually inspectable.
- **D-11:** **Phase 1 declares the full stage chain and implements only import.** Register import → panels → protected → zones → propose → snap → review → export with their dependencies and gates up front; only `import` has a working runner.

**Palette building**
- **D-12:** **Palette is built automatically by dominant-colour extraction over the whole image — not by chip/contour detection.** This explicitly supersedes `.planning/research/STACK.md`'s `cv2.findContours`/`connectedComponents` chip-detection approach for this requirement.
- **D-13:** **Use an existing library — do not hand-roll the extractor.** Evaluate at least Pylette, ColorThief/color-thief-py, colorgram.py, and Pillow's own `quantize()`/`convert("P", palette=ADAPTIVE)`. Adding no dependency at all is a legitimate winning outcome.
- **D-14:** **One extractor serves both PAL-01 and PAL-02, with a sheet-aware pre-pass.** The character-sheet path drops near-black ink and near-white paper before extracting. Everything after that is shared.
- **D-15:** **Extraction count is adaptive** — the extractor decides how many colours to return based on the image, not a fixed N or an artist-supplied N. Recovery path is PAL-03, reachable directly from the extraction result.
- **D-16:** **Entries are auto-named `Colour 1..N` and freely renameable.** No naming prompt blocks getting a working palette.

### Claude's Discretion

The user did not select **web shell architecture** for discussion. `.planning/research/STACK.md` is the default and is not re-litigated:
- **FastAPI** backend serving the app; the existing `Store` stays the data layer (no ORM).
- **Vite + TypeScript** frontend, served as static files by FastAPI in production — one process to run.
- Phase 1's screens are forms and lists — no canvas editor lands until Phase 2. A lightweight component framework for the shell is fine and expected; do **not** put the Phase 2/3 canvas editors inside a reactive framework's render model.
- Do **not** use NiceGUI / Streamlit / Gradio / Reflex.
- **Coordinate transform ownership** is Claude's call. The consumers are the browser-side editors in Phases 2–3, so the transform belongs in TypeScript with its own unit tests; if the server ever needs the same maths, that is a separate small Python function, not a shared abstraction stretched across the language boundary.

**Note — UI-SPEC.md narrows the shell decision further than STACK.md anticipated:** the approved UI-SPEC explicitly rejects *any* component framework (not just shadcn) — "none (hand-rolled component set over plain CSS custom properties)". STACK.md's fallback suggestion ("introduce Svelte if the shell grows past a handful of views") is superseded by the UI-SPEC for this phase; the shell is vanilla TypeScript + plain CSS, full stop. See Architecture Patterns below.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. **Noted for the planner:** artist-visible volumes (D-03) are a small, deliberate addition beyond the literal v1 requirements; keep the UI minimal.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROJ-01 | Create a named project and reopen it later with pages, palette and edits intact | D-04 folder-per-project design; SQLite persistence semantics section; `project` table replacing `series` |
| PROJ-02 | Upload line art pages to a project and add more over time | Page upload flow; `page.stage` default; multipart upload handling in Security Domain |
| PROJ-03 | Upload character sheet images as colour references | D-05 accept-time binding; reference-image storage recommendation in Persistence section |
| PROJ-04 | See each page's stage in the pipeline and open any page for editing | Pipeline stage registry section; `page.stage` column; `GET /pipeline/stages` metadata endpoint recommendation |
| PROJ-05 | Edits persist as they are made; refresh/crash loses no work | SQLite persistence semantics (WAL, commit discipline, per-request Store); Pitfall 15 cross-reference |
| PAL-01 | Upload a swatch image; app creates named palette entries from its colour chips | Palette Construction section; Pillow `quantize()` verified against a synthetic flat-chip test |
| PAL-02 | App proposes palette entries from a character sheet; accept/reject individually | D-14 sheet-aware pre-pass; ephemeral-proposal design (not persisted until accepted) |
| PAL-03 | Create, rename, recolour and delete palette entries by hand | Existing `Store` CRUD (`add_palette_entry`, `update_palette_rgb`) — additive only |
| PAL-04 | Change a palette entry's colour; every affected page updates, no pipeline re-run | Already implemented: `store.update_palette_rgb()` + `store.panels_affected_by()`; revision-counter pattern (ARCHITECTURE.md Pattern 3) |

</phase_requirements>

## Summary

Phase 1 is two things stapled together deliberately: an ordinary CRUD web app (projects, pages, palette) and a piece of foundational plumbing (stage registry, coordinate transform, invariant check) that has no working consumer yet but must exist in a shape later phases won't have to redesign. Both halves are now well-specified by CONTEXT.md and UI-SPEC.md; this research fills in the "how to implement it well" gaps the discretion areas and open technical questions left behind.

The web-shell decision is locked (FastAPI + Vite/TypeScript, no component framework at all per the approved UI-SPEC) but one piece of it changed materially since STACK.md was written eight days ago: **FastAPI 0.141.0/0.141.1 (released 2026-07-29, days before this research) shipped a first-class `app.frontend()` method** that serves a built SPA with correct client-side-routing fallback (missing assets 404, unmapped navigation routes fall back to `index.html`, API routes are matched first and can never be shadowed) — replacing the hand-rolled `StaticFiles(html=True)` catch-all pattern STACK.md assumed would be necessary. This directly answers the phase's "serve the app shell, later stream GPU work" question: FastAPI mounts the API routers, mounts `app.frontend("/", directory="frontend/dist")`, and Phase 4's worker process talks to this same process over local HTTP — nothing about that boundary changes.

For persistence, the existing `Store`'s "not thread-safe, one Store per thread" docstring is a real constraint against FastAPI's threadpool-per-sync-route execution model. The correct pattern (verified against community and FastAPI-team guidance) is a new `sqlite3.Connection` per request via a FastAPI dependency, not a shared global connection with `check_same_thread=False`. Combined with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout`, this gives PROJ-05's "no lost work" guarantee almost for free, since every `Store` method already calls `.commit()` synchronously before returning — there is no batching to add or remove. The one new pitfall this introduces (not previously documented anywhere in this project's research) is that WAL mode produces `-wal`/`-shm` side files that must travel with `project.db` for D-04's "copy the folder, hand it over" portability promise to hold; this needs an explicit checkpoint-on-close step.

For palette extraction, live verification this session overturns part of D-13's own candidate list: `Pylette` has moved from the "2.3.x" version CONTEXT.md cited to **6.0.0**, and none of the four candidates (Pylette, ColorThief, colorgram.py, Pillow's `quantize()`) natively support D-15's "adaptive count" requirement — every one of them takes a fixed N. The recommendation is **Pillow's `Image.quantize()` (zero new dependency, already pinned) run at a generous fixed ceiling, then a small custom merge pass in CIELAB space using `skimage.color` (already an undeclared transitive dependency this phase should declare regardless) to collapse near-duplicate clusters into the adaptive final count.** This was verified directly: `quantize(colors=16, method=MEDIANCUT, dither=NONE)` on a synthetic 4-chip flat-colour test image recovers the exact 4 source colours with zero invented pixels — the literal case D-12 describes ("if it was already an image with chips or uniform colour blobs, the script will get the right colours 100% of the time").

The three foundation primitives (stage registry, coordinate transform, invariant check) are all buildable now with no real consumer, which is unusual but intentional per the phase goal. The stage registry is simpler than `.planning/research/ARCHITECTURE.md`'s original `PanelStageRun`-table proposal — D-07 locked stage tracking to a single `page.stage` column, not a per-panel-per-stage run table, so that heavier design is explicitly superseded for this phase (flagged so the planner doesn't build it prematurely). The coordinate transform is pure, DOM-free TypeScript, testable in Vitest with no browser environment needed. The invariant check extends `masks.py`'s existing `check_coverage()` rather than replacing it.

**Primary recommendation:** Build the schema migration (Series→Project, palette/entity scope move, `page.stage` column) first as the lowest-risk, most mechanical piece; stand up FastAPI with per-request `Store` dependency injection and `app.frontend()` for the shell; implement palette extraction as Pillow `quantize()` + skimage CIELAB merge (zero new Python palette-library dependency); build the stage registry as a page-level (not panel-level) declarative list with only `import` wired to a runner; build the coordinate-transform module and invariant-check function as pure, independently unit-tested code with no live consumer yet.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Project/volume/page CRUD | API / Backend | — | `Store` already owns this pattern; FastAPI routers are thin marshalling only |
| Project folder picking, recent-projects list | Frontend Server (SSR-less; browser file dialog via native `<input type="file" webkitdirectory>` or an OS folder picker proxied through a backend endpoint) | API / Backend | Browsers cannot open an arbitrary local folder by path without a picker; backend validates the picked path and opens the `Store` |
| Page/character-sheet/swatch upload | Browser / Client (drag-drop UI) | API / Backend (multipart handling, validation, disk write) | Upload UI is client; every byte written to disk and every DB row is server-authoritative |
| Palette extraction (swatch, character sheet) | API / Backend | — | CPU-bound Pillow/numpy/skimage work; must never run client-side (no such library in the browser stack, and results must be deterministic/server-authoritative) |
| Palette entry CRUD, recolour | API / Backend | Browser / Client (colour picker UI, optimistic swatch update) | `update_palette_rgb`/`panels_affected_by` already exist server-side; UI is feedback-only per D-09 |
| Pipeline stage registry + `page.stage` | API / Backend | — | Registry is a Python data structure; no client-side pipeline logic should ever exist (UI only renders what the registry+page.stage report) |
| Stage-strip rendering, Go-Back dialog copy | Browser / Client | API / Backend (computes the concrete cost sentence) | UI-SPEC explicitly requires the "discards N edits" sentence be server-computed, never a static template |
| Coordinate transform (screen ↔ label-map) | Browser / Client (TypeScript) | — (Python only if/when the server ever rasterises a client stroke, not this phase) | Locked by CONTEXT.md discretion; consumers are Phase 2/3 browser editors |
| Label-map exclusivity/exhaustiveness invariant check | API / Backend | — | Extends `masks.py`; label maps are server-authoritative arrays, never client state |
| Project persistence (SQLite) | Database / Storage | API / Backend (connection lifecycle) | `Store` + `project.db` per D-04; WAL mode and per-request connections are a Backend-tier concern |

## Project Constraints (from CLAUDE.md)

These are treated with the same authority as CONTEXT.md's locked decisions:

- **Python 3.11+**, `numpy`/`opencv`/`scipy`/`pillow`, SQLite, pytest — established stack; the web layer is the only open choice (already resolved by CONTEXT.md discretion).
- **Single machine, local web app** — no accounts, no multi-user; the folder-per-project + per-request-`Store` design in this document assumes exactly one artist, one machine, at a time.
- **Local NVIDIA GPU, no CPU path** — not exercised in Phase 1 (no Cobra work here), but the `worker/` process boundary this phase's `app.frontend()`/FastAPI choice sets up must not be redesigned in Phase 4.
- **Export is PSD only** — not relevant to Phase 1.
- **Region stores `palette_entry_id`, never RGB** — Non-negotiable, and untouched by this phase (Phase 1 does not create `Region` rows at all; only `import` runs).
- **OpenRAIL++-M / vendored-dependency licence discipline** — not relevant to Phase 1's dependency set (FastAPI, Pillow, scikit-image, Vite/TypeScript/Vitest are all MIT/BSD/Apache-2.0/HPND, all open-source-compatible).
- **Naming/style conventions** (from `.planning/codebase/CONVENTIONS.md`, already read): snake_case, complete type hints, `X | None` unions, relative imports, dataclasses + enums for domain shapes, Protocol classes for swappable implementations, docstrings that explain *why* and cite § sections. New code in this phase (`pipeline/`, `web/`) should match this house style exactly — it is well-established across `model/`, `segmentation/`, `extract/`.

## Standard Stack

### Core

| Library | Version (verified 2026-08-10) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.141.1 [VERIFIED: PyPI, `pip index versions`] | Backend API: project/page/palette CRUD, uploads, static frontend serving | Async-native, Pydantic validation, and as of 0.141.x ships `app.frontend()` for SPA serving — see State of the Art below. Locked by CONTEXT.md discretion. |
| `uvicorn` | 0.52.1 [VERIFIED: PyPI] | ASGI server | Standard FastAPI pairing; `uvicorn[standard]` extra pulls `httptools`/`uvloop`-equivalent for dev reload. |
| `python-multipart` | 0.0.32 [VERIFIED: PyPI] | Required by FastAPI's `UploadFile` for multipart form uploads | Easy to forget — FastAPI does not vendor it. slopcheck flagged the name as "classic LLM naming pattern" but confirmed it is the genuine, established package (not a slopsquat) — see Package Legitimacy Audit. |
| `Pillow` | >=11.0 (existing pin; 12.1.1 installed locally) [VERIFIED: PyPI, existing project dependency] | Swatch/character-sheet palette extraction via `Image.quantize()`; general image I/O | Zero new dependency. Verified directly this session: `quantize(colors=N, method=MEDIANCUT, dither=Dither.NONE)` + `.convert("RGB").getcolors()` recovers exact source colours on a synthetic flat-chip test image with correct per-colour pixel counts. |
| `scikit-image` | 0.26.0 [VERIFIED: PyPI; already an **undeclared** transitive dependency via `segmentation/closure.py`'s `skeletonize()`] | `skimage.color.rgb2lab` + `deltaE_cie76`/`deltaE_ciede2000` for the adaptive-palette-count merge pass | Must be added to `pyproject.toml` explicitly this phase regardless of the palette-extraction decision (`.planning/codebase` and CONTEXT.md code_context both already flag this as owed). Reusing it for CIELAB distance now previews the exact pattern Phase 5 needs for snapping, at zero extra cost. |
| `Vite` | 8.2.1 [VERIFIED: npm, `npm view vite version`] | Frontend build tool, dev server with API proxy | STACK.md assumed 6.x (training-data-stale); confirm the planner pins a current major. Locked by CONTEXT.md discretion. |
| `TypeScript` | 7.0.x [VERIFIED: npm; officially GA 2026-07-08 per Microsoft DevBlogs] | Frontend language for the shell and (Phase 2+) canvas editors | **State-of-the-art note:** TypeScript 7 is a from-scratch Go-native port of `tsc`, not a rewrite — "faithful port... preserves identical type-checking semantics" (Microsoft's own announcement). No code-level migration needed; only the compiler binary changed. ~10x faster builds. Safe to adopt directly for a greenfield project. |
| `Vitest` | 4.1.10 [VERIFIED: npm] | Frontend unit tests — specifically the coordinate-transform module this phase must ship | Peer-dependency-verified compatible with Vite 8 (`peerDependencies: vite: "^6 \|\| ^7 \|\| ^8"`). No `jsdom`/`happy-dom` needed for Phase 1's tests (pure math, no DOM). |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | 0.28.1 [VERIFIED: PyPI] | Dev-only — `fastapi.testclient.TestClient` is built on `httpx.Client` (confirmed via FastAPI's own reference docs) | Add to the `dev` extra alongside `pytest`, for integration-testing the new `web/` routers. |
| `platformdirs` | — (NOT recommended, see Alternatives) | OS-correct app-config directory for the recent-projects list | Only reach for this if cross-platform config-directory correctness becomes a real requirement later; v1 is Windows-only and a `Path.home() / ".comiccolor"` dotfolder is simpler and needs no new dependency. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pillow `quantize()` for palette extraction | `Pylette` 6.0.0 (MIT, verified actively maintained — 159 commits, changelog, Dependabot, CLI) | Better out-of-the-box API for `palette_size`/`colorspace`/alpha handling and CLI batch mode, but is still fixed-N (no native adaptive count — same gap as Pillow), and is a new dependency for a capability Pillow already covers zero-cost. Reconsider if Pillow's median-cut quality proves visibly worse than KMeans on real (non-flat) character sheets during implementation. |
| Pillow `quantize()` | `ColorThief`/`color-thief-py` 0.2.1 | D-13 flagged "check maintenance status" — verified this session: last PyPI release 0.2.1 is old, GitHub shows 18 open issues / 7 pending PRs with limited recent activity. Do not use. |
| Pillow `quantize()` | `colorgram.py` 1.2.0 | Proportion-aware (returns `.rgb` + `.proportion` per colour), small and stable, but adds a dependency for something Pillow's `getcolors()` already returns via pixel counts. No adaptive-count support either. |
| Per-request `sqlite3.Connection` via FastAPI `Depends` | Single global `Store` with `check_same_thread=False` | Simpler to write, but the FastAPI team's own community guidance is explicit that sharing one connection across the sync threadpool "can lead to race conditions and inconsistent database state." Rejected. |
| Per-request `sqlite3.Connection` | Single dedicated worker thread + `queue.Queue` for all DB ops (mirrors the `ThreadPoolExecutor(max_workers=1)` pattern STACK.md already recommends for Cobra/export jobs) | Also correct and arguably more literally satisfies "one Store per thread" — genuinely a coin flip vs. per-request connections. Per-request is recommended because it needs no new infrastructure and SQLite's WAL mode already makes concurrent readers-during-a-write cheap; flagged as a legitimate alternative for the planner to choose instead. |
| `app.frontend()` for SPA serving | Hand-rolled `StaticFiles(html=True)` + custom catch-all route (STACK.md's original assumption) | `app.frontend()` is extremely new (days old as of this research — see State of the Art) and its GitHub PR history is thin. The hand-rolled pattern is the safe fallback if `app.frontend()` proves buggy or its `check_dir="auto"` dev-mode behaviour conflicts with the Vite dev-server-proxy setup. Recommend trying `app.frontend()` first with the fallback pattern documented as a fast escape hatch, not built defensively upfront. |

**Installation:**
```bash
pip install "fastapi>=0.141" "uvicorn[standard]>=0.52" "python-multipart>=0.0.32" "scikit-image>=0.26"
pip install "httpx>=0.28"  # dev extra

npm create vite@latest frontend -- --template vanilla-ts
cd frontend && npm install --save-dev vitest@^4.1
```

**Version verification performed this session:**
```
pip index versions fastapi          # 0.141.1
pip index versions uvicorn          # 0.52.1
pip index versions python-multipart # 0.0.32
pip index versions scikit-image     # 0.26.0
pip index versions Pylette          # 6.0.0 (checked — not adopted, see Alternatives)
pip index versions colorthief       # 0.2.1 (checked — not adopted)
pip index versions colorgram.py     # 1.2.0 (checked — not adopted)
npm view vite version               # 8.2.1
npm view typescript version         # 7.0.2
npm view vitest version             # 4.1.10
npm view konva version              # 10.3.0 (not installed this phase — see Don't Hand-Roll / Phase 2 note)
```
All versions materially newer than STACK.md's 8-day-old training-data-influenced estimates (e.g., Vite "6.x" → 8.2.1 current; Pylette "2.3.x" → 6.0.0 current). The planner should pin against these verified-current numbers, not STACK.md's, where they conflict.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads/Activity | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `fastapi` | PyPI | Since 2018, current 0.141.1 (2026-07-29) | Massive (billions of installs historically) | github.com/fastapi/fastapi | [OK] | Approved |
| `uvicorn` | PyPI | Long-established, current 0.52.1 | Standard FastAPI pairing, very high | github.com/encode/uvicorn | [OK] | Approved |
| `python-multipart` | PyPI | Long-established, current 0.0.32 | High (FastAPI's own documented upload dependency) | github.com/Kludex/python-multipart | [OK] (flagged: "Name starts with 'python-' — classic LLM naming pattern. Name looks like LLM bait but package is established.") | Approved — slopcheck's own heuristic false-positive, confirmed genuine by cross-reference with FastAPI's own docs |
| `httpx` | PyPI | Long-established, current 0.28.1 | High (Starlette/FastAPI TestClient dependency) | github.com/encode/httpx | [OK] | Approved |
| `scikit-image` | PyPI | Long-established (10+ years), current 0.26.0 | Very high | github.com/scikit-image/scikit-image | [OK] | Approved |
| `vite` | npm | Since 2020-04-21, current 8.2.1 | 6,600+ dependent projects reported by npm registry | github.com/vitejs/vite | not run (Python-only tool) — manually verified via `npm view` age/repo, well-known official org | Approved |
| `typescript` | npm | Since 2012-10-01, current 7.0.2 | Foundational ecosystem package | github.com/microsoft/TypeScript | not run — manually verified, Microsoft official | Approved |
| `vitest` | npm | Since 2021-12-03, current 4.1.10 | Standard Vite-ecosystem test runner | github.com/vitest-dev/vitest | not run — manually verified | Approved |

**Packages removed due to slopcheck `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** none. `python-multipart`'s naming-pattern flag was investigated and resolved as a false positive (it is FastAPI's own documented, required upload dependency, not a slopsquat) — no `checkpoint:human-verify` needed, but the planner may still choose to note the false-positive investigation in the plan for audit-trail completeness.

Konva (10.3.0, MIT, established since 2015) was checked for currency but is **not** part of this phase's install list — Phase 1 ships no canvas editor, so installing Konva now would be premature; defer to Phase 2's research/plan.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser                                                             │
│  Project picker → Project shell (sidebar) → Volume/Page grid →       │
│  Page detail (stage strip) → Palette grid (extraction + hand edit)   │
└───────────────────────────┬────────────────────────────────────────┘
                             │ HTTP (fetch), multipart uploads
┌───────────────────────────▼────────────────────────────────────────┐
│  FastAPI app (uvicorn, single process)                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ app.frontend("/", directory="frontend/dist")                 │   │
│  │   — serves the built Vite SPA; API routes matched first,     │   │
│  │     unmapped navigation falls back to index.html              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  routers/project.py   routers/page.py   routers/palette.py         │
│      │                     │                   │                    │
│      ▼                     ▼                   ▼                    │
│  Depends(get_store) ── new sqlite3.Connection per request ──────┐  │
│                                                                    │  │
│  pipeline/stages.py — declarative STAGES list (8 stages,          │  │
│  only "import" has a runner)                                      │  │
│  pipeline/runner.py — thin: on page-create, set page.stage        │  │
│                                                                    │  │
│  colour/extract.py — Pillow quantize + skimage CIELAB merge       │  │
│  (swatch path: extract → write PaletteEntry rows immediately)     │  │
│  (character-sheet path: pre-pass mask → extract → return          │  │
│   proposals in the HTTP response only, NOT persisted)             │  │
└───────────────────────────┬──────────────────────────────────────┘  │
                             │                                          │
┌───────────────────────────▼──────────────────────────────────────┐  │
│  model/store.py (EXISTING — extended, not replaced)  ◄─────────────┘
│  project.db (SQLite, WAL mode) inside the artist's chosen folder   │
│  + pages/, references/, label_maps/ subdirectories on disk         │
└──────────────────────────────────────────────────────────────────┘
```

A reader can trace PAL-02 end to end: browser drag-drops a character sheet → multipart POST → FastAPI router saves the file under `<project>/references/` and calls `colour/extract.py`'s sheet-aware pre-pass + quantize+merge → the response carries proposal colours (not yet in the DB) → browser renders proposal cards → artist accepts one → a second POST creates/reuses an `Entity` row and a real `PaletteEntry` row through `Store`, which commits immediately (WAL) → the palette grid re-fetches and shows the confirmed entry.

### Recommended Project Structure

```
src/comiccolor/
├── model/              # EXISTING — entities.py, store.py, masks.py all modified this phase
│   │                   #   (Series→Project rename+scope-move; page.stage column; no masks.py
│   │                   #    schema change, only a new invariant-check helper added)
├── pipeline/            # NEW — build first
│   ├── stages.py        #   PipelineStage enum + declarative STAGES list (8 stages)
│   └── runner.py        #   thin: run_import(page) sets page.stage after upload
├── colour/               # NEW — palette extraction only this phase (no Cobra/snapping yet)
│   └── extract.py        #   quantize + skimage CIELAB merge; sheet pre-pass mask
├── web/                   # NEW
│   ├── app.py             #   FastAPI app factory; app.frontend() mount
│   ├── deps.py            #   get_store() FastAPI dependency (per-request Store)
│   ├── routers/
│   │   ├── project.py     #   create/open/list-recent
│   │   ├── page.py        #   upload, list, stage
│   │   └── palette.py     #   swatch extract, sheet propose/accept/reject, hand CRUD
│   └── schemas.py         #   Pydantic request/response models
└── cli.py                 # EXISTING — gains a `serve` subcommand (uvicorn entrypoint)

frontend/                  # NEW — separate npm project, NOT a Python package
├── src/
│   ├── shell/              #   sidebar, project picker, volume/page grid — plain TS + CSS
│   ├── palette/             #   palette grid, proposal cards
│   └── geometry/
│       └── transform.ts     #   screen ↔ label-map coordinate transform (pure, no DOM)
├── tests/
│   └── transform.test.ts    #   Vitest — no canvas, no jsdom needed
└── dist/                    #   build output, served by app.frontend()

tests/
├── test_store.py            # EXISTING — extended for Project rename + scope move
├── test_masks.py            # EXISTING — extended with invariant-check wrapper tests
├── test_pipeline.py         # NEW — STAGES shape, page.stage transitions
├── test_extract.py          # NEW — quantize+merge on synthetic flat-chip and noisy images
└── test_web/                # NEW — FastAPI TestClient (httpx) integration tests
    ├── test_project_routes.py
    ├── test_page_routes.py
    └── test_palette_routes.py
```

### Pattern 1: Per-request SQLite connection via FastAPI dependency injection

**What:** A FastAPI dependency opens a fresh `sqlite3.Connection` (wrapped in the existing `Store` class) scoped to the currently open project's `project.db` path, and closes it when the request ends.

**When to use:** Every route that touches the database. This is the single mechanism that reconciles `Store`'s documented "not thread-safe, one Store per thread" constraint with FastAPI's default execution model (sync `def` routes run in a threadpool; a different worker thread may handle each request).

**Example:**
```python
# web/deps.py
from fastapi import Depends, HTTPException
from comiccolor.model import Store

def get_current_project_path(request: Request) -> Path:
    # resolved from app.state (set on "open project") — see Open Questions
    ...

def get_store(project_path: Path = Depends(get_current_project_path)) -> Iterator[Store]:
    with Store(project_path / "project.db") as store:
        yield store
```
```python
# web/routers/page.py
@router.post("/pages")
def upload_page(file: UploadFile, store: Store = Depends(get_store)):
    ...  # store.add_page(...) — commits immediately, same as today
```

**Trade-offs:** A fresh `sqlite3.connect()` call and a fresh `SCHEMA` executescript (all `CREATE TABLE IF NOT EXISTS`, so idempotent and cheap — microseconds on a local file) happen once per request. Given the "one artist, one machine" scale, this cost is immaterial and buys correctness for free. Enable `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;` once inside `Store.__init__` (extend it — currently only sets `PRAGMA foreign_keys = ON` via the schema script) so that a GET-while-a-POST-is-writing never raises `sqlite3.OperationalError: database is locked`.

### Pattern 2: `app.frontend()` for the built SPA, with a documented fallback

**What:** `app.frontend("/", directory="frontend/dist")` mounted after all API routers. Missing static assets 404; unmapped client-side routes fall back to `index.html`; API routes are matched first and unconditionally, so they can never be shadowed regardless of mount order (per the feature's own design intent).

**When to use:** Production serving (`comiccolor serve`). In development, run `vite dev` separately with its dev-server proxying `/api/*` to `uvicorn --reload` on a different port — `app.frontend()`'s `check_dir="auto"` convenience option is specifically for making `fastapi dev` ergonomic, but the two-process dev setup (Vite HMR + uvicorn reload) is still the standard pattern and should be kept regardless.

**Trade-offs:** This is a brand-new API (landed in the days immediately before this research — see State of the Art). If it proves unstable, the documented fallback is the older `StaticFiles(html=True)` + a manual catch-all route that returns `index.html` for any path not matching `/api/*` or a real static file — this was STACK.md's original recommendation and remains correct, just more code.

### Pattern 3: Palette extraction as quantize-then-merge, never chip/contour detection

**What:** For both PAL-01 (swatch) and PAL-02 (character sheet, after the D-14 pre-pass), run `Image.quantize(colors=K_MAX, method=Quantize.MEDIANCUT, dither=Dither.NONE)` at a generous fixed ceiling (e.g. `K_MAX=24`), pull `(count, rgb)` pairs via `.convert("RGB").getcolors(maxcolors=256)`, convert to CIELAB with `skimage.color.rgb2lab`, and greedily merge clusters whose `deltaE_cie76` falls under a threshold (starting point: same order of magnitude as Phase 5's eventual snapping threshold — this is a hypothesis, not a validated constant, see Assumptions Log), dropping clusters below a minimum pixel-share floor as extraction noise. The number of clusters remaining *is* the adaptive N.

**Verified example (this session, exact recovery on a synthetic 4-chip grid):**
```python
from PIL import Image
import numpy as np

arr = np.zeros((40, 40, 3), dtype=np.uint8)
arr[0:20, 0:20] = [255, 0, 0]
arr[0:20, 20:40] = [0, 255, 0]
arr[20:40, 0:20] = [0, 0, 255]
arr[20:40, 20:40] = [255, 255, 0]
im = Image.fromarray(arr, "RGB")
q = im.quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
colors = q.convert("RGB").getcolors(maxcolors=256)
# -> [(400, (255,255,0)), (400, (255,0,0)), (400, (0,255,0)), (400, (0,0,255))]
# Exact recovery, exact counts (20x20=400px each), zero invented colours.
```

**When to use:** Both PAL-01 and PAL-02, per D-14 (one extractor, shared downstream path). For RGBA input (swatch PNGs with transparency), note `MEDIANCUT`/`MAXCOVERAGE` do not support RGBA — either flatten alpha onto a known background colour before quantizing, or build the "kept pixels" array by filtering (see Pattern 4) rather than relying on Pillow's own RGBA handling.

**Trade-offs:** Median cut is a coarser algorithm than Pylette's default KMeans and can occasionally miss a small-but-important colour region on a genuinely photographed/shaded character sheet (not a flat chip grid). D-15 already accepts this class of imperfection with PAL-03 as the recovery path. If real character-sheet testing (supervised video-call sessions) shows this is materially worse than KMeans, swap in Pylette (already verified MIT, actively maintained) — the merge/adaptive-count logic on top is identical either way, since neither library provides adaptive count natively.

### Pattern 4: Sheet-aware pre-pass as a pixel filter, not an alpha trick

**What:** For the character-sheet path (D-14), build a boolean mask of "near-black" (ink) and "near-white" (paper) pixels using simple RGB or HSV thresholds, then construct a 1-D array of only the *kept* (non-ink, non-paper) pixel values, reshape it into a synthetic `Nx1` "image," and run Pattern 3's quantize+merge on that synthetic image. This avoids RGBA/alpha-channel ambiguity entirely (Pillow's `FASTOCTREE` alpha-aware quantization path is not verified to ignore transparent pixels for palette purposes) and keeps the pre-pass a pure NumPy/Pillow operation with no new dependency.

```python
near_black = (arr < 30).all(axis=-1)
near_white = (arr > 235).all(axis=-1)
kept = arr[~(near_black | near_white)]
synthetic = Image.fromarray(kept.reshape(-1, 1, 3), "RGB")  # Nx1 pseudo-image
```

**When to use:** PAL-02 only. PAL-01's swatch path skips this pre-pass entirely (D-14 scopes it to "the character-sheet path").

**Trade-offs:** Threshold constants (`30`, `235` above) are a starting hypothesis, not validated against real character sheets from this project's artists — flag as an Assumption; the planner should treat these as tunable and testable against real uploaded sheets during the phase, not shipped as unvalidated magic numbers.

### Pattern 5: Stage registry is page-scoped, not panel-scoped, for this phase

**What:** `.planning/research/ARCHITECTURE.md`'s original design proposed a `PanelStageRun` SQLite table tracking `(panel_id, stage) → status`. **This is superseded for Phase 1 by D-07's explicit locked decision** ("Gates are per page... `page.stage` is a single value"). Build:

```python
# model/entities.py (alongside RegionStatus, ProtectedKind)
class PipelineStage(str, Enum):
    IMPORT = "import"
    PANELS = "panels"
    PROTECTED = "protected"
    ZONES = "zones"
    PROPOSE = "propose"
    SNAP = "snap"
    REVIEW = "review"
    EXPORT = "export"
```
```python
# pipeline/stages.py
@dataclass(frozen=True)
class Stage:
    name: PipelineStage
    upstream: PipelineStage | None
    runner: Callable[[Store, Page], None] | None  # None = not implemented yet

STAGES: list[Stage] = [
    Stage(PipelineStage.IMPORT, upstream=None, runner=run_import),
    Stage(PipelineStage.PANELS, upstream=PipelineStage.IMPORT, runner=None),
    Stage(PipelineStage.PROTECTED, upstream=PipelineStage.PANELS, runner=None),
    Stage(PipelineStage.ZONES, upstream=PipelineStage.PROTECTED, runner=None),
    Stage(PipelineStage.PROPOSE, upstream=PipelineStage.ZONES, runner=None),
    Stage(PipelineStage.SNAP, upstream=PipelineStage.PROPOSE, runner=None),
    Stage(PipelineStage.REVIEW, upstream=PipelineStage.SNAP, runner=None),
    Stage(PipelineStage.EXPORT, upstream=PipelineStage.REVIEW, runner=None),
]
```

Add `page.stage TEXT NOT NULL DEFAULT 'panels'` to the schema (a page's stage becomes `"panels"` the instant upload/import completes, since UI-SPEC states "a successful upload auto-advances the page to Import-complete" with no visible confirm step for Import specifically).

**Important handoff detail for the planner:** the frontend's stage-strip rendering needs **two** pieces of information per segment, not one — `page.stage == segment.stage` (position) **and** whether `segment.runner is not None` (capability) — because UI-SPEC explicitly requires that "Not yet reached, reachable in a future phase" and "Not yet reached, no runner exists this phase" render *identically* in Phase 1 (neutral, not-yet-reached), even though the underlying data distinguishes them. Expose stage metadata (name, display name, `has_runner: bool`) via a small `GET /pipeline/stages` endpoint rather than hardcoding the 8-stage list and runner-availability in the frontend, so this doesn't need re-deriving each phase as more runners land.

**Trade-offs:** This is deliberately lighter than the ARCHITECTURE.md proposal. That heavier per-panel run-tracking table becomes relevant once Phase 2+ needs per-panel re-run granularity (e.g., re-running `zones` for one edited panel without touching siblings) — at that point the planner will likely add a `PanelStageRun`-shaped table *alongside* `page.stage`, not instead of it, since D-07 only decided the page-level *display* granularity, not that finer internal tracking can never exist. Flag this for the Phase 2/3 planners, not this one.

### Pattern 6: Coordinate transform as pure TypeScript, no DOM dependency

**What:** A single module (`frontend/src/geometry/transform.ts`) exposing two pure functions and their shared `Viewport` type:

```typescript
export interface Viewport {
  zoom: number;           // screen px per label-map px
  panX: number;           // screen-space offset of the viewport origin
  panY: number;
  devicePixelRatio: number;
  panelOffset: { x: number; y: number };  // panel's bbox origin in page-pixel space
}

export function screenToLabelMap(point: { x: number; y: number }, vp: Viewport): { x: number; y: number } {
  const pageX = (point.x - vp.panX) / (vp.zoom * vp.devicePixelRatio);
  const pageY = (point.y - vp.panY) / (vp.zoom * vp.devicePixelRatio);
  return { x: Math.floor(pageX - vp.panelOffset.x), y: Math.floor(pageY - vp.panelOffset.y) };
}

export function labelMapToScreen(point: { x: number; y: number }, vp: Viewport): { x: number; y: number } {
  const pageX = point.x + vp.panelOffset.x;
  const pageY = point.y + vp.panelOffset.y;
  return {
    x: pageX * vp.zoom * vp.devicePixelRatio + vp.panX,
    y: pageY * vp.zoom * vp.devicePixelRatio + vp.panY,
  };
}
```

**When to use:** This is the single, shared implementation Pitfall 7 (`.planning/research/PITFALLS.md`) requires — every future click-to-select, hover-highlight, and freehand-stroke interaction in Phase 2/3 routes through it. `Math.floor` (not `Math.round`) on the label-map side is deliberate: it must match whatever indexing convention the server-side NumPy array uses (0-indexed, floor-based pixel binning) exactly, or a click one sub-pixel from a boundary will disagree between client hit-test and server-side truth.

**Trade-offs:** Built speculatively (no canvas consumer exists yet in Phase 1) but low-risk because it is pure math with an obvious, narrow contract — test it now with unit tests at both zoom extremes (Pitfall 7's explicit requirement: "test at extreme zoom-in and extreme zoom-out, not just mid-zoom"), and let Phase 2 extend the `Viewport` shape if real usage reveals a missing field, rather than trying to anticipate every future need now.

### Pattern 7: Invariant check as an assertion wrapper over the existing `check_coverage`

**What:** `masks.py` already implements exhaustiveness checking (`check_coverage`) and exclusivity is structural (one int32 array, cannot represent overlap — already tested in `test_exclusivity_is_structural`). Phase 1's job is to add a thin, loudly-failing wrapper other phases and dev-mode assertions can call without re-deriving the report-parsing logic:

```python
# model/masks.py — additive
class LabelMapInvariantError(Exception):
    """Raised when a label map violates §3 exhaustiveness. Exclusivity is
    structural and cannot be violated by construction — see module docstring."""

def assert_invariant(
    label_map: np.ndarray, line_mask: np.ndarray, protected: np.ndarray | None = None
) -> None:
    report = check_coverage(label_map, line_mask, protected)
    if not report["exhaustive"]:
        raise LabelMapInvariantError(
            f"{report['uncovered_pixels']} fillable pixels have no region "
            f"(coverage={report['coverage']:.4f})"
        )
```

**When to use:** Not exercised against real pipeline data this phase (no label maps exist yet — only `import` runs, and import doesn't segment anything). Build and unit-test it now with synthetic label maps (matching `test_masks.py`'s existing style) so Phase 3's zone editor (the highest invariant-risk surface, per PITFALLS.md Pitfall 8) can call it after every merge/split/undo transition without writing this logic itself.

**Trade-offs:** None significant — this is additive, small, and directly extends code already proven correct by existing tests.

### Anti-Patterns to Avoid

- **Sharing one global `sqlite3.Connection`/`Store` across FastAPI's threadpool with `check_same_thread=False`.** Community and FastAPI-team guidance both flag this as a race-condition risk, not a shortcut. Use per-request connections (Pattern 1).
- **Building the `PanelStageRun` table this phase.** ARCHITECTURE.md proposed it, but D-07 locked page-level granularity for Phase 1. Building the panel-level table now is premature scope the phase's own requirements don't need yet (see Pattern 5).
- **Persisting character-sheet proposal colours to the database before accept.** D-05/D-15/UI-SPEC all treat pre-accept state as ephemeral by design (nothing is "real" until confirmed, mirroring D-06's stage-gate philosophy generalized to palette proposals). Persisting them would need extra schema (a proposal table) and extra cleanup logic for rejected proposals, for no requirement that asks for it.
- **Chip/contour detection (`cv2.findContours`/`connectedComponentsWithStats`) for palette extraction.** This was STACK.md's original recommendation and is explicitly overridden by D-12/D-13. Do not resurrect it.
- **A component framework (Svelte, React, etc.) for the Phase 1 shell.** STACK.md left this open as a possibility "if the shell grows past a handful of views"; the approved UI-SPEC.md closed that door explicitly ("none — hand-rolled component set"). Follow UI-SPEC, not STACK.md, where they now disagree.
- **Installing Konva this phase.** No canvas editor exists until Phase 2. Adding the dependency now buys nothing and adds noise to the dependency legitimacy audit trail for a phase that doesn't use it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dominant-colour extraction from an image | A custom k-means/median-cut implementation | `Image.quantize()` (Pillow, already pinned) | Median cut is a solved, well-tested problem; Pillow's C implementation is fast and exact on flat input (verified this session) |
| CIELAB colour distance for the adaptive-count merge | Hand-rolled RGB→Lab conversion + Euclidean distance | `skimage.color.rgb2lab` + `deltaE_cie76`/`deltaE_ciede2000` | Colour-space conversion has enough subtlety (illuminant, gamma) to be worth a tested library; also directly previews Phase 5's snapping-distance code, so learning it now pays twice |
| SPA static-file serving with client-side-routing fallback | A manual catch-all route with extension-sniffing logic to distinguish "missing JS asset" from "client route" | `app.frontend()` (FastAPI 0.141+) | FastAPI's own new implementation already solves exactly this distinction correctly (missing asset → 404, unmapped route → `index.html`) — verified via official release notes |
| Multipart file upload parsing | Hand-rolled `multipart/form-data` parsing | `python-multipart` (FastAPI's own documented dependency for `UploadFile`) | This is exactly what FastAPI's upload support is built on; do not reimplement |
| FastAPI route integration testing | Raw `requests` against a running `uvicorn` process | `fastapi.testclient.TestClient` (built on `httpx.Client`) | In-process testing, no real sockets, matches this project's existing pytest-first testing culture |

**Key insight:** Every "don't hand-roll" item in this phase is a case where the honest gap is not "no library exists" but "no library does the *adaptive* version of what exists" (palette count, stage-aware SPA fallback logic). The correct response, consistent with CLAUDE.md's "integrate before building" bias, is to use the library for the solved 90% and write a small, testable seam for the specific 10% that's genuinely this project's own problem (adaptive-K merge threshold, sheet pre-pass thresholds) — not to reject the library because it doesn't do 100% of the job out of the box.

## Runtime State Inventory

> Included because D-01/D-02 constitute a rename+scope-move of the `Series`/`Volume` entities. Conclusion: **not applicable in the migration-hazard sense**, because this is a pre-release codebase with no deployed instances.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no artist has ever created a `project.db` under the current `series`/`volume` schema; this project has not shipped. `tests/test_store.py`'s fixtures construct fresh in-`tmp_path` databases per test run, nothing persists between runs. | Code edit only — update `entities.py`, `store.py` SCHEMA, and `tests/test_store.py` fixtures directly (rename `Series`→`Project`, move `palette_entry`/`entity`/`palette_revision` to project scope). No data migration script needed. |
| Live service config | None — no external service (n8n, Datadog, etc.) references "series" or "volume" by name. | None. |
| OS-registered state | None — no scheduled tasks, services, or process managers reference this project's entity names. | None. |
| Secrets/env vars | None — this phase introduces no secrets (no auth, no API keys; Cobra's HF token handling is Phase 4's concern). | None. |
| Build artifacts | None yet — `pyproject.toml` has no web/frontend extras declared yet; this phase is what first adds them. No stale egg-info or compiled artifacts reference the old naming. | Add `[project.optional-dependencies].web` extras (`fastapi`, `uvicorn[standard]`, `python-multipart`) and declare `scikit-image` as a core dependency (already transitively used, undeclared) while touching `pyproject.toml` this phase. |

## Common Pitfalls

### Pitfall 1: WAL side files breaking D-04's "copy the folder" portability promise

**What goes wrong:** With `PRAGMA journal_mode=WAL`, SQLite keeps recently-committed data in a `project.db-wal` file (and a `-shm` shared-memory index file) that is not yet folded into `project.db` itself. If the artist copies, zips, or hands over the project folder while the app is running (or without an explicit checkpoint step), the copy can be missing committed data, or — per SQLite's own documentation — copying `project.db` alone without its `-wal` file can produce a stale or corrupt-looking database on the other end.

**Why it happens:** WAL mode is the correct choice for the per-request-connection concurrency pattern (Pattern 1) — but it trades a single-file database for a 2-3-file working set, and D-04's core promise ("copy, move, back up, or hand over the folder and it works") was designed against the mental model of one file.

**How to avoid:**
- Run `PRAGMA wal_checkpoint(TRUNCATE);` on the active `Store` connection whenever the artist explicitly closes/switches projects (an event this phase should have somewhere — e.g., a "close project" action or app-exit handler), folding all WAL content back into `project.db` and truncating the side files to zero.
- Document (in-app or in a README) that copying the project folder should happen with the app closed, or after using an explicit "prepare for backup" action if one is added.
- Consider `journal_mode=DELETE` (SQLite's traditional rollback-journal mode) instead of WAL if the portability guarantee is judged more important than concurrent-read-during-write performance — for a single-artist local app making one request at a time in practice, the WAL performance benefit is marginal and DELETE mode keeps the "it's just one file" promise intact. **This is a genuine open tradeoff for the planner to decide, not a settled recommendation** — see Open Questions.

**Warning signs:** A copied/zipped project folder that opens with fewer pages/entries than the original had, or SQLite reporting a locked/corrupt database on the copy.

**Phase to address:** This phase — the schema/persistence work is being built now, and the checkpoint-on-close (or the DELETE-mode alternative) is cheap to add at the same time as `Store.__init__`'s PRAGMA setup.

### Pitfall 2: `Store.__init__` re-running `SCHEMA` on every request is fine, but connecting to the *wrong* project.db is not

**What goes wrong:** With per-request `Store` construction (Pattern 1), the FastAPI dependency must resolve *which* `project.db` to open on every single request, based on "the currently open project." If this state is tracked incorrectly (e.g., a module-level global mutated by a previous request instead of something scoped correctly to the current session/context), a request could silently write to the wrong project's database, especially if the app is ever used with more than one browser tab open to different projects (not explicitly ruled out by any requirement).

**Why it happens:** The natural, simplest implementation is "one currently-open-project path stored in `app.state`" — this works perfectly for the single-tab, single-artist demo scenario this project explicitly targets, but is a foot-gun if that assumption is later violated even accidentally (two tabs).

**How to avoid:** Explicitly decide and document whether "currently open project" is global-per-process (`app.state`, simplest, matches v1's single-tab assumption) or per-session (cookie/header-scoped). Given `PROJECT.md`'s explicit "single machine, testing happens live over video call with the artist watching their own page" framing, global-per-process is almost certainly correct and sufficient — but the planner should state this as a conscious choice, not an accident, and the frontend should make it structurally hard to open two projects in two tabs simultaneously against a global-state backend (e.g., the project picker screen could warn, or the backend could just accept the risk as out of scope for v1).

**Phase to address:** This phase, at the point `get_current_project_path`/`get_store` are designed (Pattern 1).

### Pitfall 3: Untrusted upload filenames used directly as filesystem paths (path traversal)

**What goes wrong:** If an uploaded file's client-supplied filename (e.g., `../../etc/whatever.png` or a filename containing path separators) is used directly to construct the on-disk save path under the project folder, a malicious or malformed filename could write outside the intended `pages/`/`references/` subdirectory.

**Why it happens:** `UploadFile.filename` is client-controlled and untrusted by definition, even in a single-artist local app where the "attacker" model is closer to "a corrupted/weird filename from the artist's own OS" than a hostile actor — but PITFALLS.md's own Security Mistakes table already flags "treating single-machine as a reason to skip validation" as a named risk (a malformed upload crashing the pipeline mid-demo is the realistic failure mode here, not a hostile actor).

**How to avoid:** Never use the client-supplied filename as a path component. Generate the on-disk filename server-side (e.g., a UUID or the new `Page`/reference row's own database id + the validated extension), and store the artist-visible original filename (if wanted for display) as a separate DB column, not as part of the path.

**Phase to address:** This phase, in the upload-handling routers (`web/routers/page.py`, `web/routers/palette.py`).

### Pitfall 4: Malformed/adversarial image uploads crashing Pillow/OpenCV mid-request

**What goes wrong:** An uploaded file that has an image extension but is not a valid image (corrupted, truncated, or a non-image file renamed) can raise an unhandled exception deep inside Pillow or OpenCV, taking down the request (and, in a live supervised demo, looking exactly like "the app crashed" to the artist watching over video call).

**Why it happens:** The happy-path "open the image, process it" code works in every manual test the developer runs and fails exactly the first time a real-world file (a screenshot saved with a wrong extension, a partially-downloaded reference image) is dropped in.

**How to avoid:** Validate uploads before they enter the pipeline: attempt `Image.open(...).verify()` inside a `try/except`, check the image mode/dimensions are sane before any expensive processing, and return a clear `4xx` error with the Copywriting Contract's error-message shape ("Upload failed: the file isn't a readable image — try a PNG, JPG or TIFF.") rather than letting an exception surface as a 500.

**Phase to address:** This phase — this is exactly PROJ-02/PROJ-03's upload path.

### Pitfall 5: Adaptive-count merge threshold shipped as an unvalidated magic number

**What goes wrong:** The CIELAB `deltaE` merge threshold (Pattern 3) and the near-black/near-white pre-pass thresholds (Pattern 4) are both genuine hypotheses, not verified constants — there is no library or spec value for either. If shipped without being deliberately flagged as tunable, they will quietly become load-bearing "spec" the way PITFALLS.md's Pitfall 10 already warns against for the (unrelated but structurally identical) CIELAB snapping-reject threshold in Phase 5.

**How to avoid:** Pick a defensible starting value, but write it as a named constant with a comment stating it is unvalidated, and test it against more than one synthetic case (a flat chip grid AND a synthetic "noisy photograph" — e.g., a gradient or JPEG-artifacted image) so the planner can see it behaves reasonably in both regimes before real artist data exists to tune it against.

**Phase to address:** This phase (extraction is being built now); revisit if PAL-01/PAL-02 supervised sessions show systematically wrong counts.

## Code Examples

### FastAPI dependency for per-request Store (Pattern 1, full context)

```python
# Source: pattern synthesized from FastAPI community guidance
# (github.com/fastapi/fastapi discussion #5199) + this project's existing
# Store context-manager API (model/store.py)
from collections.abc import Iterator
from pathlib import Path
from fastapi import Depends, HTTPException, Request

from comiccolor.model import Store


def get_current_project_path(request: Request) -> Path:
    path = getattr(request.app.state, "current_project_path", None)
    if path is None:
        raise HTTPException(status_code=409, detail="No project is currently open.")
    return path


def get_store(project_path: Path = Depends(get_current_project_path)) -> Iterator[Store]:
    with Store(project_path / "project.db") as store:
        yield store
```

### `app.frontend()` mount (Pattern 2)

```python
# Source: FastAPI official release notes (0.141.0/0.141.1, 2026-07-29)
# and fastapi.tiangolo.com/tutorial/static-files/
from fastapi import FastAPI
from comiccolor.web.routers import project, page, palette

app = FastAPI()
app.include_router(project.router, prefix="/api/projects")
app.include_router(page.router, prefix="/api/pages")
app.include_router(palette.router, prefix="/api/palette")

# Mounted LAST is fine — API routes are matched first, unconditionally,
# per the feature's documented design (routes can never be shadowed).
app.frontend("/", directory="frontend/dist")
```

### Synthetic test for exact chip-grid recovery (Pattern 3, verified this session)

```python
# tests/test_extract.py — style matches existing tests/test_masks.py
import numpy as np
from PIL import Image

from comiccolor.colour.extract import extract_palette  # function to build this phase


def test_flat_chip_grid_recovers_exact_colours():
    """D-12: 'if it was already an image with chips ... 100% of the time.'"""
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[0:20, 0:20] = [255, 0, 0]
    arr[0:20, 20:40] = [0, 255, 0]
    arr[20:40, 0:20] = [0, 0, 255]
    arr[20:40, 20:40] = [255, 255, 0]
    im = Image.fromarray(arr, "RGB")

    entries = extract_palette(im)

    assert {e.rgb for e in entries} == {(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)}
    assert len(entries) == 4  # adaptive count landed on the true chip count, not K_MAX
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Hand-rolled `StaticFiles(html=True)` + custom catch-all route for SPA serving | `app.frontend(path, directory=...)` | FastAPI 0.138.0–0.141.1, June–July 2026 (days before this research) | Directly serves this phase's "serve the app shell" question; STACK.md (written 2026-08-02) predates this and assumed the hand-rolled pattern. Use the new API; keep the old pattern documented as a fallback only. |
| TypeScript 5.x/6.x tsc compiler (JS-implemented) | TypeScript 7.0, Go-native compiler ("port, not rewrite" — identical type-checking semantics) | GA 2026-07-08 | No code-level migration needed for a greenfield project; ~10x faster builds. Just pin 7.x directly rather than assuming 5.x per training-data-era research docs. |
| Pylette ~2.3.x (cited in CONTEXT.md D-13, based on training-data-era knowledge) | Pylette 6.0.0 | Multiple major versions since; exact changelog not independently verified this session (search results were inconsistent on dates) | Not adopted this phase regardless (Pillow chosen), but if the planner reconsiders Pylette, verify its current API against 6.0.0, not the 2.3.x shape D-13 describes — the API may have changed materially across 4 major versions. |

**Deprecated/outdated:** `pytoshop`, `colormath`, chip/contour-detection for palette extraction (all already flagged obsolete/overridden by prior research and CONTEXT.md — not re-litigated here, not relevant to Phase 1's actual scope beyond confirming they stay out of this phase's dependency list).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | CIELAB `deltaE` merge threshold and near-black/near-white pre-pass thresholds (Patterns 3–4) are workable starting values | Palette Construction / Pitfall 5 | Adaptive extraction returns visibly wrong counts on real character sheets; mitigated by PAL-03's manual add/delete recovery path (already a locked design decision, not a gap) |
| A2 | Global-per-process "currently open project" state (`app.state`) is sufficient, i.e., no two-tabs-two-projects scenario needs supporting in v1 | Pitfall 2 | Silent cross-project writes if the app is ever used with multiple tabs open to different projects; low likelihood given the explicit single-artist-single-session testing model, but not independently verified against a requirement that rules it out |
| A3 | `app.frontend()` (days-old FastAPI feature) is stable enough to build on for a project with no other users to absorb early-adopter risk | Standard Stack / Pattern 2 | If buggy, falls back cleanly to the well-established `StaticFiles(html=True)` + catch-all pattern — low risk, explicit fallback documented |
| A4 | WAL mode (vs. DELETE/rollback-journal mode) is the right choice given D-04's folder-portability requirement | Pitfall 1 | If wrong, either data-loss-on-copy (if checkpoint discipline is skipped) or a missed, marginal performance benefit (if DELETE mode is chosen instead) — genuinely undecided, flagged as an Open Question below |
| A5 | Median-cut (Pillow `quantize`) quality is acceptable vs. KMeans (Pylette) on real, non-flat character sheets | Standard Stack / Pattern 3 | If real supervised sessions show visibly worse proposals, swap in Pylette — the merge logic on top is unaffected either way, so this is a low-cost swap if wrong |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **WAL vs. DELETE journal mode for `project.db`, given D-04's folder-portability promise.**
   - What we know: WAL is the better fit for the per-request-connection concurrency pattern (Pattern 1) and is what most modern SQLite-backed web apps use by default. DELETE mode keeps the "it's one file" mental model D-04 was written against, at a real but likely-negligible performance cost given true single-artist, largely-serial request patterns.
   - What's unclear: Whether the planner considers "artist copies the folder while the app happens to be running" a real enough scenario (versus "artist closes the app first, as any sane person would before copying a project folder") to justify the extra checkpoint-discipline WAL requires.
   - Recommendation: Default to WAL + an explicit checkpoint-on-project-close action (Pitfall 1), since it's the more standard choice and the checkpoint discipline is cheap to add; but flag this explicitly for the planner/user to confirm rather than silently deciding it.

2. **Where exactly do not-yet-accepted character-sheet reference images live between upload and accept?**
   - What we know: D-05 requires zero-prompt upload with binding deferred to accept time; the extracted *proposals* are correctly ephemeral (Pattern in this doc), but the *uploaded file itself* plausibly needs to survive a refresh (so the artist doesn't have to re-upload if they navigate away mid-review), even though the proposals it generated do not.
   - What's unclear: Whether this phase needs a lightweight `reference_image` tracking table (id, project_id, path, entity_id nullable) for auditability, or whether "save to `<project>/references/pending/<uuid>.<ext>` and only create a DB row at accept time" (file-system-as-source-of-truth for the unbound state) is sufficient. Both are internally consistent with every locked decision; neither is mandated by CONTEXT.md.
   - Recommendation: Start with the lighter file-system-only approach (no new table) since it's simpler and nothing in the requirements demands listing "pending, unreviewed sheets" anywhere in the UI (UI-SPEC's contract shows proposals immediately after upload, not as a separate persisted queue) — but flag this as a discretion call the planner should state explicitly, not one this research is locking.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Everything | Yes (3.14 in dev env) | 3.14 (pyproject requires >=3.11) | — |
| pip | Package installation | Yes | current | — |
| Node.js / npm | Frontend build (Vite/TS/Vitest) | Yes | node v24.13.1, npm 11.8.0 | — |
| Network access (PyPI/npm) | Verifying/installing this phase's new dependencies | Yes — confirmed live this session | — | — |
| SQLite (via Python stdlib `sqlite3`) | Persistence | Yes (stdlib, no install needed) | bundled with Python 3.14 | — |
| GPU / CUDA | Not required this phase | N/A | — | Phase 4 concern only |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none — everything this phase needs is available in the current dev environment.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest >=8.0 (existing, `pyproject.toml` `[project.optional-dependencies].dev`) |
| Backend config file | `pyproject.toml` `[tool.pytest.ini_options]` (existing — `testpaths = ["tests"]`) |
| Frontend framework | Vitest 4.1.10 (new this phase) |
| Frontend config file | `frontend/vite.config.ts` (or `vitest.config.ts`) — none exists yet, Wave 0 |
| Quick run command (backend) | `pytest tests/test_store.py tests/test_masks.py tests/test_pipeline.py tests/test_extract.py -x` |
| Quick run command (frontend) | `npm --prefix frontend run test` (Vitest) |
| Full suite command (backend) | `pytest` |
| Full suite command (frontend) | `npm --prefix frontend run test -- --run` |
| Integration test client | `fastapi.testclient.TestClient` (httpx-backed) against the FastAPI app, no real uvicorn process needed |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROJ-01 | Create project, reopen, pages/palette/edits intact | integration | `pytest tests/test_web/test_project_routes.py -x` | ❌ Wave 0 |
| PROJ-02 | Upload pages, add more over time, list preserved | integration | `pytest tests/test_web/test_page_routes.py -x` | ❌ Wave 0 |
| PROJ-03 | Upload character sheet as reference | integration | `pytest tests/test_web/test_palette_routes.py::test_sheet_upload -x` | ❌ Wave 0 |
| PROJ-04 | See each page's stage; open any page | unit + integration | `pytest tests/test_pipeline.py -x` + `tests/test_web/test_page_routes.py::test_stage_field` | ❌ Wave 0 |
| PROJ-05 | Refresh/crash immediately after an edit loses no work | integration (kill-mid-session style) + **manual-UAT** | `pytest tests/test_web/test_project_routes.py::test_reopen_after_close -x`; manual: refresh browser mid-session, confirm state survives | ❌ Wave 0 (automatable persistence check); manual step is genuinely needed for "crash" specifically, not just "refresh" |
| PAL-01 | Swatch upload creates named entries from chips | unit | `pytest tests/test_extract.py -x` | ❌ Wave 0 |
| PAL-02 | Sheet proposals, accept/reject individually | unit (extraction) + integration (accept/reject flow) | `pytest tests/test_extract.py tests/test_web/test_palette_routes.py -x` | ❌ Wave 0 |
| PAL-03 | Create/rename/recolour/delete by hand | unit (existing `Store` methods, already covered by `test_store.py`) + integration | `pytest tests/test_store.py tests/test_web/test_palette_routes.py -x` | ✅ (Store layer) / ❌ (routes, Wave 0) |
| PAL-04 | Recolour propagates, no re-run | unit — **already covered** | `pytest tests/test_store.py::test_palette_edit_is_a_single_row_update tests/test_store.py::test_panels_affected_by_is_the_repaint_set` | ✅ Already exists and passes today |

**Manual-only / UAT items (not automatable within this phase):**
- Visual verification against UI-SPEC.md's token/copy/interaction contracts (colour values, spacing, the exact stage-strip visual states) — this is what `gsd-ui-checker`-style review and human eyes are for, not pytest/Vitest.
- "Crash" specifically (not just refresh) — a true process kill mid-write is hard to script reliably; the integration test can simulate "close and reopen the Store without an explicit clean shutdown," which covers the persistence-discipline claim, but a literal supervised-session crash test is a manual/UAT step per PROJ-05's own success-criteria language ("closes the app, reopens it later").

### Sampling Rate

- **Per task commit:** backend quick run + frontend quick run (both above).
- **Per wave merge:** full backend suite (`pytest`) + full frontend suite + one manual pass against UI-SPEC's Checker Sign-Off table for any UI-touching wave.
- **Phase gate:** Full suite green (`pytest` + Vitest) before `/gsd-verify-work`; the PROJ-05 manual crash-scenario check should be run at least once at phase gate, not per-task.

### Wave 0 Gaps

- [ ] `tests/test_pipeline.py` — covers PROJ-04 (STAGES shape, `page.stage` transitions)
- [ ] `tests/test_extract.py` — covers PAL-01/PAL-02 (quantize+merge, pre-pass, adaptive count)
- [ ] `tests/test_web/__init__.py` + `test_project_routes.py`, `test_page_routes.py`, `test_palette_routes.py` — cover PROJ-01/02/03/05, PAL-02/03
- [ ] `frontend/vitest.config.ts` + `frontend/src/geometry/transform.ts` + `frontend/tests/transform.test.ts` — the coordinate-transform module and its tests, framework install: `npm install --save-dev vitest@^4.1` inside `frontend/`
- [ ] Frontend `package.json` test script (`"test": "vitest"`) — none exists yet, greenfield frontend

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Explicitly out of scope — single machine, no accounts (`PROJECT.md` constraints) |
| V3 Session Management | No | No multi-user sessions; "currently open project" is process-global state (see Pitfall 2), not a user session concept |
| V4 Access Control | No | Single local artist, no roles |
| V5 Input Validation | Yes | Pydantic request models (FastAPI's default) for all JSON bodies; explicit image validation (`Image.open().verify()`) for uploads before processing (Pitfall 4); parameterized SQL throughout (already the existing `Store` pattern — continue it, never string-format SQL) |
| V6 Cryptography | No | No secrets/passwords/tokens handled in this phase |
| V12 File & Resource Handling | Yes | Server-generated filenames for all uploads, never client-supplied (Pitfall 3); bound the folder-picker to paths the artist explicitly selects, never accept an arbitrary path string from the frontend without validating it resolves inside an expected root |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via uploaded filename | Tampering | Never use `UploadFile.filename` as a path component; generate server-side ids/UUIDs (Pitfall 3) |
| Malformed image causing unhandled exception / DoS mid-request | Denial of Service | Validate with `Image.open().verify()` in a `try/except` before processing; return structured 4xx errors, never let an unhandled exception surface as a bare 500 (Pitfall 4) |
| SQL injection | Tampering | Continue the existing parameterized-query pattern throughout `Store` — already followed consistently in the codebase; do not introduce string-formatted SQL anywhere new this phase |
| Arbitrary folder-path disclosure via the "open project" flow | Information Disclosure | The folder picker should be a native OS dialog (client-side) handing back a path the artist explicitly chose, not a free-text path field the backend blindly trusts and opens |

## Sources

### Primary (HIGH confidence)
- `pip index versions fastapi/uvicorn/python-multipart/httpx/scikit-image/Pylette/colorthief/colorgram.py` — live PyPI registry queries, this session
- `npm view vite/typescript/vitest/konva version|time.created|repository.url|license` — live npm registry queries, this session
- FastAPI official release notes (`fastapi.tiangolo.com/release-notes/`) — confirmed `app.frontend()` landed 0.141.0/0.141.1, 2026-07-29, via WebFetch this session
- FastAPI official docs (`fastapi.tiangolo.com/tutorial/static-files/`, `.../reference/testclient/`) — confirmed `StaticFiles` import shape and `TestClient`'s `httpx.Client` basis, via WebFetch this session
- Microsoft DevBlogs — "Announcing TypeScript 7.0" — confirmed GA date (2026-07-08) and "port, not rewrite" semantics claim, via WebSearch this session
- Direct execution: `Image.quantize()` + `.getcolors()` exact-recovery test on a synthetic 4-chip image, this session (see Code Examples)
- `slopcheck install fastapi uvicorn python-multipart httpx scikit-image` — direct tool run this session, all `[OK]`
- Existing codebase, read directly: `model/entities.py`, `model/store.py`, `model/masks.py`, `tests/test_store.py`, `tests/test_masks.py`, `pyproject.toml`, `.planning/codebase/TESTING.md`

### Secondary (MEDIUM confidence)
- WebSearch synthesis on FastAPI sync-route threadpool + SQLite `check_same_thread` community guidance (GitHub `fastapi/fastapi` discussion #5199, Medium/DEV.to practitioner posts) — cross-checked, consistent across multiple independent sources
- WebSearch synthesis on SQLite WAL-mode copy/portability hazards (SQLite's own forum + `sqlite.org/wal.html`) — official SQLite documentation is the primary source within this secondary synthesis
- `umesh-malik.com` blog post on `app.frontend()` usage details (mount signature, fallback behaviour) — corroborated by the official release notes but the blog itself is a secondary/unofficial source
- GitHub repo page fetches (WebFetch) for `qTipTip/Pylette` and `fengsp/color-thief-py` — maintenance/licence signals (commit counts, open issues), not primary registry data

### Tertiary (LOW confidence, flagged for validation)
- CIELAB merge-threshold and ink/paper pre-pass threshold starting values (Patterns 3–4) — genuine hypotheses, no source beyond this session's own reasoning; explicitly logged in Assumptions
- `.planning/research/STACK.md`'s Vite "6.x" and Pylette "2.3.x" version estimates — superseded by this session's live verification (8.2.1 / 6.0.0), included here only to document the drift, not as ongoing guidance

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version number and licence claim in the Core/Supporting tables was verified live against PyPI/npm this session, not carried over from training data or prior research docs.
- Architecture: MEDIUM-HIGH — the per-request-Store and `app.frontend()` patterns are corroborated by official docs/community consensus; the exact schema shape for unbound reference images (Open Question 2) and the WAL-vs-DELETE call (Open Question 1) are genuine, explicitly-flagged discretion points for the planner, not settled facts.
- Pitfalls: MEDIUM — the WAL-portability and per-thread-connection pitfalls are corroborated by official SQLite/community sources; the adaptive-threshold pitfall is this project's own reasoning, consistent with the same shape of pitfall (Pitfall 10) already validated in `.planning/research/PITFALLS.md` for the unrelated CIELAB-snapping case in Phase 5.

**Research date:** 2026-08-10
**Valid until:** ~30 days for the Python/backend findings (stable ecosystem); ~14 days for the npm/frontend version numbers and the `app.frontend()` claim specifically, since it is days old as of this research and could see rapid follow-up patches — re-verify its behaviour empirically during implementation rather than trusting this document indefinitely.
