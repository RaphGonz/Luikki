# Phase 1: Foundation — Project, Palette & Pipeline Backbone - Context

**Gathered:** 2026-08-02
**Status:** Ready for planning

<domain>
## Phase Boundary

A persistent project an artist creates, reopens, and adds pages and reference
images to over time; a palette built automatically from an uploaded image and
editable by hand; and the shared infrastructure every later editor stands on —
the pipeline stage registry, the screen↔label-map coordinate transform, and the
label-map exclusivity/exhaustiveness invariant check.

Covers PROJ-01..05 and PAL-01..04.

**Not this phase:** panel polygon editing (Phase 2), protected masks (Phase 2),
zone editing (Phase 3), Cobra (Phase 4), snapping (Phase 5), review view
(Phase 6), PSD export (Phase 7).

</domain>

<decisions>
## Implementation Decisions

### Project model

- **D-01:** "Project" is the existing `Series` entity, renamed. The hierarchy
  becomes **Project → Volume → Page → Panel → Region**.

- **D-02:** **Palette and entities move up to project scope.** `palette_entry`
  and `entity` re-point from `volume_id` to `project_id`, and
  `volume.palette_revision` moves to the project row. This is what makes the
  palette accumulate across everything in the project, and it is the reason
  D-01 chose Series over Volume as the project. This is a schema migration of
  `model/entities.py` + `model/store.py` + `tests/test_store.py`, not a rename.

- **D-03:** **Volume survives and is artist-visible.** The artist creates
  volumes inside a project and files pages into them. Note for the planner: no
  v1 requirement asks for volume grouping — this is a deliberate,
  user-confirmed addition made after the cost was stated, on the grounds that
  it matches how a real series is organised and gives page reading order a
  natural home. Keep its UI minimal: create, rename, delete, and assign pages.

- **D-04:** **Folder per project, database inside it.** A project is a
  directory the artist names, containing `project.db` plus asset subdirectories
  (pages, reference images, label maps). "Open project" is a folder pick.
  Projects are portable — copy, move, back up, or hand over the folder and it
  works, which matters directly for the supervised video-call testing model.
  A small recent-projects list (outside any project, in app config) keeps the
  artist from file-picking every time; it is a convenience index only and must
  never be authoritative over the folder.

- **D-05:** **Reference images bind to a character at accept time, not upload
  time.** Uploading a character sheet is one drag-and-drop with no prompts. The
  app asks for the character name only when the artist accepts palette
  proposals extracted from that sheet — the moment they are looking at the
  colours and know what to call them. This is what lets entries land as
  `Kaito / hair / base` (the spec's label shape) without taxing every upload.

### Pipeline stage model

- **D-06:** **The pipeline is forward-only with a confirmation gate at each
  stage.** The artist reviews a stage's output, confirms, and that boundary
  locks. There is deliberately no "stale downstream" concept anywhere in the
  system, because the model never permits stale state to exist. This was the
  user's own reframing of the question and it overrides the invalidation-graph
  design the question originally offered.

- **D-07:** **Gates are per page.** The artist confirms a stage for a whole
  page before moving to the next. `page.stage` is a single value, which is
  exactly what PROJ-04 needs to display.

- **D-08:** **Going back is possible, but costed and explicit.** The artist can
  reset a page to an earlier stage. Before it happens the app states plainly
  what will be destroyed and re-run — in concrete terms ("discards zone edits
  on 6 panels, re-runs colour proposal"), not a generic warning — and requires
  confirmation. Going back is understood by the user as expensive in both GPU
  minutes and the artist's own corrections; the UI must make that cost visible
  rather than smooth it over.

- **D-09:** **Palette edits sit entirely outside the stage chain.** Recolouring
  a palette entry is never a stage regression at any stage, including on a
  fully reviewed page. No warning, no confirmation, no re-run. This is
  `flatting-pipeline-spec.md` §213 ("palette edits propagate incrementally,
  never re-run the volume") and PAL-04, and it is already implemented
  server-side by `store.update_palette_rgb()` + `store.panels_affected_by()`.

- **D-10:** **Declarative registry with a thin runner.** Each stage declares
  its name, its dependencies, what it produces, and a callable that runs it. A
  small runner walks the chain, but every stage stays individually triggerable
  and individually inspectable — the registry must not become an orchestrator
  that runs a page past its gates.

- **D-11:** **Phase 1 declares the full stage chain and implements only
  import.** Register import → panels → protected → zones → propose → snap →
  review → export with their dependencies and gates up front; only `import` has
  a working runner. Later phases fill in runners against a contract that
  already exists, and Phase 1 can show a real stage indicator immediately. The
  planner should expect some declared stage shapes to need amending in Phases
  3–5 and should not treat the declaration as frozen.

### Palette building

- **D-12:** **Palette is built automatically by dominant-colour extraction over
  the whole image — not by chip/contour detection.** The artist may drop a chip
  grid, a photographed set of objects, or a screenshot; the extractor returns
  the main colours either way. On an image that already contains flat chips or
  uniform colour blobs, this is exact. The artist then modifies the result.
  This explicitly supersedes the `cv2.findContours` / `connectedComponents`
  chip-detection approach proposed in `.planning/research/STACK.md` — that
  section of the stack research is **overridden** for this requirement.

- **D-13:** **Use an existing library — do not hand-roll the extractor.**
  PROJECT.md's standing "build from existing tools first" rule applies. The
  researcher must evaluate and pick, checking licence compatibility with the
  project's open-source intent, from at least:
  - `Pylette` (2.3.x, KMeans, actively developed, has a CLI and batch mode)
  - `ColorThief` / `color-thief-py` (median cut, Pillow-only, widely used but
    check maintenance status)
  - `colorgram.py` (proportion-aware extraction)
  - Pillow's own `Image.quantize()` / `convert("P", palette=ADAPTIVE)` — median
    cut with **zero new dependencies**, since Pillow >=11.0 is already pinned
  Adding no dependency at all is a legitimate winning outcome here.

- **D-14:** **One extractor serves both PAL-01 and PAL-02, with a sheet-aware
  pre-pass.** The character-sheet path drops near-black ink and near-white
  paper before extracting, so what comes back is the character's colours and
  not the page's. Everything after that — proposals, accept/reject, naming,
  entity binding — is shared between the two paths.

- **D-15:** **Extraction count is adaptive** — the extractor decides how many
  colours to return based on the image, rather than a fixed N or an
  artist-supplied N. Accepted tradeoff: on a shaded character sheet "distinct
  flat colour" is a judgement call and the artist gets no count lever. The
  recovery path is PAL-03 (create/delete entries by hand), which must therefore
  be reachable directly from the extraction result, not buried in a separate
  palette screen.

- **D-16:** **Entries are auto-named `Colour 1..N` and freely renameable.** No
  naming prompt blocks getting a working palette. PAL-03's rename covers the
  rest, and D-05's accept-time character binding is what supplies the
  meaningful `Kaito / hair / base` labels where they matter.

### Claude's Discretion

The user did not select **web shell architecture** for discussion, so this is
Claude's call. Take `.planning/research/STACK.md` as the default and do not
re-litigate it:

- **FastAPI** backend serving the app; the existing `Store` stays the data
  layer (do not introduce an ORM — it would compete with the already-built
  model).
- **Vite + TypeScript** frontend, served as static files by FastAPI in
  production so there is one process to run.
- Phase 1's screens are forms and lists (project picker, volume/page grid,
  palette manager) — no canvas editor lands until Phase 2. A lightweight
  component framework for the shell is fine and expected; **do not** put the
  Phase 2/3 canvas editors inside a reactive framework's render model when they
  arrive.
- **Do not** use NiceGUI / Streamlit / Gradio / Reflex — ruled out with reasons
  in STACK.md.
- **Coordinate transform ownership** is also Claude's call. The consumers are
  the browser-side editors in Phases 2–3, so the transform belongs in
  TypeScript with its own unit tests; if the server ever needs the same maths
  (rasterising a client-sent polyline), that is a separate small Python
  function, not a shared abstraction stretched across the language boundary.
  The planner should state which it chose and why.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Pipeline specification (source of truth for pipeline internals)
- `flatting-pipeline-spec.md` — full architecture, resolved prerequisites
  P1–P4, metrics, anti-patterns, known hard cases. PROJECT.md scopes the
  product *around* this document; it does not restate it.
- `flatting-pipeline-spec.md` §213 — "palette edits propagate incrementally,
  never re-run the volume". Basis for D-09.
- `flatting-pipeline-spec.md` §315 — every stage boundary is inspectable and
  editable. The constraint D-10's registry must not violate.
- `flatting-pipeline-spec.md` §3 — data model the schema changes in D-01/D-02
  must stay faithful to.
- `flatting-pipeline-spec.md` §1.5 — palette entries: project-scoped,
  versioned, editable.

### Project scope and requirements
- `.planning/PROJECT.md` — constraints, Key Decisions table, and the standing
  "build from existing tools first" instruction that D-13 enforces.
- `.planning/REQUIREMENTS.md` — PROJ-01..05, PAL-01..04 are this phase's
  requirements; full v1 list gives the shape later phases need.
- `.planning/ROADMAP.md` — Phase 1 goal and its five success criteria.

### Research (read before choosing anything)
- `.planning/research/STACK.md` — FastAPI/Vite/Konva recommendation, PSD write
  verification, Cobra dependency isolation, background-job design.
  **Caveat:** its swatch-extraction section (contour/connected-component chip
  detection) is superseded by D-12. The rest stands.
- `.planning/research/PITFALLS.md` — known failure modes.
- `.planning/research/ARCHITECTURE.md` — architectural patterns for the web layer.
- `.planning/research/SUMMARY.md` — synthesis across the research set.

### Existing code this phase modifies or builds on
- `src/comiccolor/model/entities.py` — `Series`, `Volume`, `Page`, `Panel`,
  `Entity`, `PaletteEntry`, `Region`, `ProtectedMask`. D-01/D-02 change this file.
- `src/comiccolor/model/store.py` — SQLite `SCHEMA` and CRUD. D-01/D-02 change
  this file. Note `update_palette_rgb()` and `panels_affected_by()` already
  implement PAL-04's mechanic.
- `src/comiccolor/model/masks.py` — label map I/O and `check_coverage()`. The
  invariant check this phase hardens builds on what is already here.
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`,
  `.planning/codebase/CONVENTIONS.md` — where new code goes and the house style
  it must match.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `store.update_palette_rgb(entry_id, rgb)` — already does the single-row
  update, bumps `palette_entry.revision` and the parent's palette revision, and
  touches no region rows. PAL-04's server side is **already built**; what's
  missing is the render/repaint path, not the data mechanic.
- `store.panels_affected_by(palette_entry_id)` — returns exactly the panel ids
  needing repaint. This is the incremental propagation set for PAL-04.
- `palette_entry.revision` and `volume.palette_revision` counters exist
  specifically so a renderer can cache against them. `palette_revision` needs
  to move to the project row per D-02.
- `model/masks.py` — `save_label_map`, `load_label_map`, `region_stats`,
  `check_coverage`, `relabel_sequential`. The invariant checker this phase
  builds should extend these, not replace them.
- `Store` is a context manager with `PRAGMA foreign_keys = ON` and
  `ON DELETE CASCADE` throughout — deleting a project already cleans up
  correctly. `region.palette_entry_id` is `ON DELETE SET NULL`, so deleting a
  palette entry that regions reference is already safe.

### Established Patterns

- Protocol classes for swappable implementations (`Segmenter`,
  `LineExtractor`) — the stage registry's runner callable should follow the
  same shape.
- Dataclasses for domain objects; enums for domain states (`RegionStatus`,
  `ProtectedKind`). The stage enum belongs alongside them in `entities.py`.
- The no-RGB-on-region invariant is enforced by the *schema*, not review. Any
  new table added this phase must hold to the same standard: make bad states
  unrepresentable rather than checked.
- Complete type annotations, `X | None` unions, relative imports, docstrings
  that explain *why* and cite spec sections with §.

### Integration Points

- `Store.__init__` takes a path and runs `SCHEMA` — D-04's folder-per-project
  layout means one `Store` per open project, constructed from the project
  folder. `Store` is documented as not thread-safe (one per thread); the web
  layer must respect that.
- `pyproject.toml` currently declares no web dependency at all. FastAPI,
  `python-multipart`, and `httpx` (dev) are additions this phase makes.
  `scikit-image` is used by `segmentation/closure.py` but is **not declared** —
  fix that here while touching the file.
- `cli.py` currently only dispatches research spikes (`p3`, `ab`). The web app
  is a new entry point, not an extension of it.

</code_context>

<specifics>
## Specific Ideas

- On going back through the pipeline (D-08), in the user's own words: *"Each
  stage is forward only, you cannot go back. At each stage, the artist is asked
  whether they confirm or not... To go back is to rewrite every step back: it
  will cost them time and money."* The escape hatch exists, but the design must
  treat backward movement as expensive and say so plainly at the moment it is
  offered.

- On palette extraction (D-12), in the user's own words: *"The user could drop
  a grid of objects, you extract the main colors from it to generate the
  palette. Then the user will simply modify. If it was already an image with
  chips or uniform color blob, the script will get the right colors 100% of the
  time. I'm pretty sure there's a lib doing this exact thing."* The expectation
  is exactness on flat-colour input and reasonable behaviour on anything else —
  and that this is an integration, not an implementation.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

**Noted for the planner rather than deferred:** artist-visible volumes (D-03)
are a small addition beyond the literal v1 requirements. The cost was stated
and the user confirmed it deliberately. It is in scope for Phase 1; keep it
minimal.

</deferred>

---

*Phase: 1-Foundation — Project, Palette & Pipeline Backbone*
*Context gathered: 2026-08-02*
