# Phase 1: Foundation — Project, Palette & Pipeline Backbone - Pattern Map

**Mapped:** 2026-08-10
**Files analyzed:** 24
**Analogs found:** 13 real in-repo / 11 greenfield (no analog — RESEARCH.md is authoritative for these)

**Honesty note:** This phase is split. The Python model/store/pipeline/colour layer has strong,
direct analogs in the existing codebase — use them literally, don't paraphrase them. The FastAPI
`web/` layer and the entire `frontend/` TypeScript app have **no analog anywhere in this repo**
(first web code, first TS code this project has ever had). For those files this document points
at `01-RESEARCH.md` § Code Examples / § Architecture Patterns Pattern 1-7 and `01-UI-SPEC.md`'s
token/interaction contracts instead of forcing a fake analogy.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/comiccolor/model/entities.py` (modified: `Series`→`Project`, scope moves, `PipelineStage` enum, `page.stage`) | model | CRUD | itself (existing file, same file modified) | exact — edit in place |
| `src/comiccolor/model/store.py` (modified: schema migration, `Project`/`Volume`/`Page` CRUD re-pointed) | model/service | CRUD | itself (existing file, same file modified) | exact — edit in place |
| `src/comiccolor/model/masks.py` (modified: add `LabelMapInvariantError` + `assert_invariant`) | utility | transform | itself — extends `check_coverage` | exact — additive to existing file |
| `tests/test_store.py` (modified: Project rename, scope-move assertions) | test | CRUD | itself (existing file, same file modified) | exact |
| `tests/test_masks.py` (modified: add invariant-wrapper tests) | test | transform | itself (existing file, same file modified) | exact |
| `src/comiccolor/pipeline/stages.py` (new) | config/registry | event-driven (declarative registry, no runtime dispatch loop) | `src/comiccolor/segmentation/segmenter.py` (`Segmenter` Protocol) | role-match — Protocol/registry shape, not CRUD |
| `src/comiccolor/pipeline/runner.py` (new) | service | request-response (thin, single `run_import`) | `src/comiccolor/segmentation/segmenter.py` (`TrappedBallSegmenter.segment`) — a swappable-implementation caller | role-match |
| `src/comiccolor/colour/extract.py` (new) | service | transform (image in, `PaletteEntry` list out) | `src/comiccolor/extract/manga_line.py` + `src/comiccolor/extract/passthrough.py` (Protocol implementation pair) | role-match — same "adapter wraps a CV/ML routine, returns a typed result dataclass" shape |
| `src/comiccolor/extract/base.py` (unmodified — read as the Protocol pattern) | interface | — | n/a (this IS the analog for `colour/extract.py`'s shape) | — |
| `src/comiccolor/cli.py` (modified: add `serve` subcommand) | controller/entry-point | request-response | itself (existing file, same file modified) | exact |
| `pyproject.toml` (modified: add `fastapi`, `uvicorn`, `python-multipart`, `scikit-image`, `httpx` dev; add `web` extras) | config | — | itself (existing file, same file modified) | exact |
| `tests/test_pipeline.py` (new) | test | CRUD/event-driven | `tests/test_store.py` (fixture + assertion style) | role-match |
| `tests/test_extract.py` (new) | test | transform | `tests/test_masks.py` (pure-function, synthetic-array style) | role-match |
| `src/comiccolor/web/app.py` (new) | controller (app factory) | request-response | **none in repo** | no analog — RESEARCH.md Pattern 2, § Code Examples |
| `src/comiccolor/web/deps.py` (new) | middleware (DI) | request-response | **none in repo** | no analog — RESEARCH.md Pattern 1, § Code Examples |
| `src/comiccolor/web/schemas.py` (new) | model (Pydantic DTOs) | request-response | **none in repo** (closest conceptual kin is `model/entities.py`'s dataclasses, but Pydantic validation semantics differ materially) | weak/no analog — RESEARCH.md § Security Domain V5 |
| `src/comiccolor/web/routers/project.py` (new) | controller | CRUD (request-response over `Store`) | **none in repo**; conceptually wraps `store.add_series`/`add_volume`/`pages_for_volume` | no analog — RESEARCH.md Pattern 1 + § Architecture Patterns diagram |
| `src/comiccolor/web/routers/page.py` (new) | controller | file-I/O + CRUD (multipart upload) | **none in repo** | no analog — RESEARCH.md Pitfall 3/4, § Security Domain |
| `src/comiccolor/web/routers/palette.py` (new) | controller | CRUD + file-I/O (extraction + accept/reject) | **none in repo**; wraps `store.add_palette_entry`/`update_palette_rgb`/`panels_affected_by` | no analog for the HTTP layer — `store.py`'s existing methods ARE the service-layer analog underneath it |
| `tests/test_web/__init__.py`, `test_project_routes.py`, `test_page_routes.py`, `test_palette_routes.py` (new) | test | request-response (integration) | `tests/test_store.py` (fixture style: `tmp_path`, pytest fixtures) for DB setup; no existing FastAPI `TestClient` analog | partial — fixture conventions transfer, HTTP test shape does not |
| `frontend/src/shell/*` (new: sidebar, project picker, volume/page grid) | component | request-response (fetch) | **none in repo** | no analog — greenfield TS; follow UI-SPEC.md §8 Screen inventory |
| `frontend/src/palette/*` (new: palette grid, proposal cards) | component | request-response (fetch) | **none in repo** | no analog — UI-SPEC.md Phase-Specific Interaction Contracts §4/§5 |
| `frontend/src/geometry/transform.ts` (new) | utility | transform (pure math) | **none in repo** | no analog — RESEARCH.md Pattern 6 (full code given) |
| `frontend/tests/transform.test.ts` (new) | test | transform | **none in repo** | no analog — Vitest, no existing frontend test culture to match |
| `frontend/vite.config.ts` / `vitest.config.ts`, `package.json` (new) | config | — | **none in repo** | no analog — RESEARCH.md § Validation Architecture |

## Pattern Assignments

### `src/comiccolor/model/entities.py` (model, CRUD) — MODIFY IN PLACE

**Analog:** itself — the file already contains every convention the new pieces must match.

**Dataclass + docstring pattern to copy** (lines 43-57, `Series`/`Volume` — becomes `Project`/`Volume`):
```python
@dataclass
class Series:
    name: str
    id: int | None = None


@dataclass
class Volume:
    series_id: int
    name: str
    id: int | None = None
    # Bumped on every palette mutation. Lets the incremental propagation in
    # Tier 2 (§6) find stale panels without re-running the volume.
    palette_revision: int = 0
```
D-01/D-02 rename `Series`→`Project` and move `palette_revision` off `Volume` onto `Project`;
`Volume` keeps `project_id` (was `series_id`) and drops `palette_revision`. Preserve the exact
"why" comment style — it is load-bearing per CLAUDE.md docstring conventions (explain why, cite §).

**Enum pattern to copy** (lines 25-31, `RegionStatus`) — this is the direct analog for the new
`PipelineStage` enum (RESEARCH.md Pattern 5):
```python
class RegionStatus(str, Enum):
    """Provenance of a region's palette assignment, per §3."""

    AUTO = "auto"  # assigned by snapping, unreviewed
    CONFIRMED = "confirmed"  # artist looked at it and accepted
    FLAGGED = "flagged"  # snap distance over threshold, or high seed variance
    MANUAL = "manual"  # artist assigned it directly
```
Follow this shape exactly for `PipelineStage(str, Enum)` (`IMPORT`, `PANELS`, `PROTECTED`, `ZONES`,
`PROPOSE`, `SNAP`, `REVIEW`, `EXPORT`) — string enum, one-line inline comments per member where
non-obvious, docstring citing §.

**`Page` dataclass** (lines 59-67) — add `stage: PipelineStage = PipelineStage.PANELS` here per
D-07/Pattern 5 (page becomes `"panels"` the instant import completes — see RESEARCH.md Pattern 5
schema note). Follow the existing field-then-comment convention (`# Path to the ink layer...`).

**Module docstring convention** (lines 1-17) — the top-of-file docstring names the invariants
enforced structurally. When editing, extend it to state the new project-scope invariant (palette
lives on `Project`, never `Volume`) in the same "why, not what" voice CLAUDE.md requires.

---

### `src/comiccolor/model/store.py` (model/service, CRUD) — MODIFY IN PLACE

**Analog:** itself.

**SCHEMA constant pattern** (lines 28-117) — `CREATE TABLE IF NOT EXISTS`, `ON DELETE CASCADE`
throughout, `UNIQUE` constraints as the schema-level invariant enforcement mechanism. Rename
`series`→`project`, move `palette_entry.volume_id`→`palette_entry.project_id`, move
`entity.volume_id`→`entity.project_id`, move `volume.palette_revision`→`project.palette_revision`,
add `page.stage TEXT NOT NULL DEFAULT 'panels'` (RESEARCH.md Pattern 5). Keep the `idx_*` index
block convention (lines 112-116) and add corresponding indexes for any new FK columns.

**CRUD method pattern to copy verbatim in shape** (lines 142-165, `add_series`/`add_volume`/`add_page`):
```python
def add_series(self, series: Series) -> Series:
    cur = self.conn.execute("INSERT INTO series (name) VALUES (?)", (series.name,))
    self.conn.commit()
    series.id = cur.lastrowid
    return series
```
Every new CRUD method (`add_project`, updated `add_volume`, `pages_for_volume` stage-aware queries)
must follow this exact shape: parameterized SQL only (never string-format — RESEARCH.md § Security
Domain V5 flags this explicitly), `.commit()` synchronously before returning, mutate-and-return the
passed dataclass with the new `id`.

**Revision-counter propagation pattern** (lines 236-258, `update_palette_rgb`) — **already fully
built, PAL-04's server side needs zero new code**, only re-pointing `volume_id`→`project_id` in the
`UPDATE volume SET palette_revision...` subquery to `UPDATE project SET palette_revision...`:
```python
def update_palette_rgb(self, entry_id: int, rgb: tuple[int, int, int]) -> int:
    """Edit a colour. Returns the entry's new revision.

    This is the single-row update §3 is built around. No region rows are
    touched; nothing is re-run. Callers repaint only the panels named by
    ``panels_affected_by``.
    """
    ...
```
```python
def panels_affected_by(self, palette_entry_id: int) -> list[int]:
    """Panel ids referencing this entry — the incremental repaint set (§6)."""
    ...
```
This is the pattern the `web/routers/palette.py` recolour endpoint calls directly — do not
reimplement any of this logic in the web layer, just marshal HTTP → these two methods → HTTP.

**Row-adapter pattern** (lines 331-388, `_page`, `_panel`, `_palette_entry`) — one private
`_<entity>(row: sqlite3.Row) -> Entity` function per table, used by every `*_for_*` query method.
New `_project` adapter follows this exact shape.

**Class docstring** (line 121) — `"""Thin data-access layer. Not thread-safe; one Store per thread."""`
This is the literal constraint RESEARCH.md Pattern 1 (`web/deps.py`) exists to respect — cite it
when wiring per-request `Store` construction.

---

### `src/comiccolor/model/masks.py` (utility, transform) — ADDITIVE ONLY

**Analog:** itself — `check_coverage` (lines 107-137) is the exact function the new invariant
wrapper extends, not replaces.

**Pattern to copy** — RESEARCH.md's own Pattern 7 gives the literal code (already matches this
file's docstring/type-hint/exception conventions):
```python
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
Follow `check_coverage`'s own docstring shape (lines 107-120: explains what invariant is verified,
cites §3, documents the boolean-mask convention of its arguments) for `assert_invariant`'s docstring.

---

### `src/comiccolor/pipeline/stages.py` (config/registry, event-driven) — NEW FILE

**Analog:** `src/comiccolor/segmentation/segmenter.py` — `@runtime_checkable` Protocol pattern
(lines 51-59).

**Protocol pattern to copy**:
```python
@runtime_checkable
class Segmenter(Protocol):
    @property
    def name(self) -> str: ...

    def segment(
        self, line_mask: np.ndarray, protected: np.ndarray | None = None
    ) -> np.ndarray:
        """``line_mask`` True on ink. Returns an int32 label map, 0 = unassigned."""
        ...
```
D-10's "declarative registry with a thin runner" is not quite this Protocol shape (a `Stage` is a
frozen dataclass entry in a list, not an interface multiple classes implement) — RESEARCH.md
Pattern 5 already gives the concrete `Stage`/`STAGES` code to use directly:
```python
@dataclass(frozen=True)
class Stage:
    name: PipelineStage
    upstream: PipelineStage | None
    runner: Callable[[Store, Page], None] | None  # None = not implemented yet

STAGES: list[Stage] = [
    Stage(PipelineStage.IMPORT, upstream=None, runner=run_import),
    Stage(PipelineStage.PANELS, upstream=PipelineStage.IMPORT, runner=None),
    ...
]
```
What transfers from `segmenter.py` is the *docstring convention* (module docstring states the seam's
contract up front, "X in, Y out, both implementations produce the same thing") and the "class docstring
explains what varies vs. what's guaranteed" discipline — apply that to the `Stage`/`STAGES` module
docstring even though the concrete shape is a dataclass list, not a Protocol.

---

### `src/comiccolor/pipeline/runner.py` (service, request-response) — NEW FILE

**Analog:** `TrappedBallSegmenter.segment` (segmenter.py lines 63-76) — a small function that calls
into `Store`/model objects and returns/mutates a typed result, no dispatch logic beyond its own job.

**Pattern:** `run_import(store: Store, page: Page) -> None` sets `page.stage = PipelineStage.PANELS`
and persists it via a new `Store.set_page_stage` method (follow `store.set_label_map_path`, lines
200-202, for the "single-column UPDATE, commit, no return value" shape):
```python
def set_label_map_path(self, panel_id: int, path: str) -> None:
    self.conn.execute("UPDATE panel SET label_map_path = ? WHERE id = ?", (path, panel_id))
    self.conn.commit()
```

---

### `src/comiccolor/colour/extract.py` (service, transform) — NEW FILE

**Analog:** `src/comiccolor/extract/manga_line.py` + `src/comiccolor/extract/passthrough.py` +
`src/comiccolor/extract/base.py` — the existing Protocol-implementation-pair pattern for "image in,
typed result dataclass out."

**Result-dataclass pattern to copy** (`extract/base.py` lines 24-32):
```python
@dataclass
class ExtractionResult:
    """A greyscale line image plus whatever the extractor wants on the record."""

    lines: np.ndarray
    meta: dict[str, object] = field(default_factory=dict)
```
`colour/extract.py` should define an analogous small dataclass (e.g. proposed colours + counts +
provenance) rather than returning bare tuples/dicts, matching this project's "dataclass for
structured multi-field returns" convention.

**Class-per-responsibility docstring pattern to copy** (`manga_line.py` lines 43-51 — explains
*why* a design choice was made, not just what the class does):
```python
class MangaLineExtractor:
    """CPU-capable wrapper around the ``res_skip`` network.

    ``tile`` bounds peak memory and lets full-resolution studio pages (300dpi
    is routinely 3500x5000) run without a GPU. ...
    """
```
Apply this voice to `extract_palette()`'s docstring: state why quantize+CIELAB-merge was chosen
over chip detection (D-12/D-13) and flag the merge threshold as a tunable constant (RESEARCH.md
Pitfall 5) directly in the docstring, the same way `manga_line.py` flags "Franco-Belgian hatching
is out of its training distribution" as a named caveat rather than burying it in a comment.

**Concrete algorithm** — use RESEARCH.md § Code Examples' verified snippet directly (Pattern 3/4):
```python
q = im.quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
colors = q.convert("RGB").getcolors(maxcolors=256)
```
plus the sheet pre-pass filter (Pattern 4):
```python
near_black = (arr < 30).all(axis=-1)
near_white = (arr > 235).all(axis=-1)
kept = arr[~(near_black | near_white)]
synthetic = Image.fromarray(kept.reshape(-1, 1, 3), "RGB")
```
No in-repo analog exists for the CIELAB merge step (`skimage.color.rgb2lab` + `deltaE_cie76`) —
this is genuinely new to the codebase; write it as a small private helper (`_merge_similar`) inside
this module, following the "private functions prefixed with underscore" convention already used in
`segmenter.py` (`_ball`, `_install_quiet_logger`) and `manga_line.py` (`_feather`, `_ramp`).

---

### `src/comiccolor/cli.py` (controller, request-response) — MODIFY IN PLACE

**Analog:** itself.

**Subparser pattern to copy** (lines 32-45, the `p3` subparser):
```python
p3 = sub.add_parser("p3", help="run the P3 region-count spike")
p3.add_argument("pages", nargs="+", help="image files or directories")
p3.add_argument("-o", "--out", default="reports/p3", help="output directory")
```
New `serve` subcommand follows this shape: `sub.add_parser("serve", help=...)`, args for `--port`/
`--project` if needed, dispatch block follows the existing `if args.command == "p3":` /
`if args.command == "ab":` pattern (lines 59-91) — add `if args.command == "serve":` importing
`uvicorn` and the app factory lazily (matching the existing lazy-import-inside-the-branch style
used for `.spike.p3`/`.spike.ab`).

**Error-handling pattern to copy** (line 24): `raise SystemExit("no images found")` — CLI errors
are `SystemExit` with a plain message string, never a raw traceback. Apply the same style to any
CLI-level validation added for `serve` (e.g., project path doesn't exist).

---

### `tests/test_pipeline.py` (test, CRUD/event-driven) — NEW FILE

**Analog:** `tests/test_store.py` — fixture and assertion style (lines 1-41, 43-48).

**Fixture pattern to copy**:
```python
@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s
```
**Assertion-of-impossibility pattern to copy** (line 43-47, docstring + assertion style):
```python
def test_region_table_has_no_rgb_column(store):
    """§9: do not bake RGB into regions. Enforced by the schema."""
    columns = {row[1] for row in store.conn.execute("PRAGMA table_info(region)")}
    assert not columns & {"r", "g", "b", "rgb", "colour", "color"}
```
Apply this to `test_pipeline.py`'s STAGES-shape tests: assert the declared chain order, assert only
`import`'s `runner` is non-`None`, assert `page.stage` transitions follow `Stage.upstream` — state
each test's docstring as "what design guarantee this proves," matching the module docstring
convention: `"""The §3 invariants, as tests. ... assertions are about what is impossible..."""`.

---

### `tests/test_extract.py` (test, transform) — NEW FILE

**Analog:** `tests/test_masks.py` (synthetic-numpy-array style) — read via RESEARCH.md's own
worked example, which already matches this project's test conventions:
```python
def test_flat_chip_grid_recovers_exact_colours():
    """D-12: 'if it was already an image with chips ... 100% of the time.'"""
    arr = np.zeros((40, 40, 3), dtype=np.uint8)
    arr[0:20, 0:20] = [255, 0, 0]
    ...
    entries = extract_palette(im)
    assert {e.rgb for e in entries} == {(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)}
```
Docstring convention: quote the CONTEXT.md decision ID the test proves (`D-12`), matching
`test_store.py`'s `"""§9: do not bake RGB into regions..."""` habit of citing the governing spec/
decision directly in the test docstring.

---

## No Analog Found (greenfield — follow RESEARCH.md / UI-SPEC.md, not a forced in-repo analogy)

| File | Role | Data Flow | Reason | Where to look instead |
|---|---|---|---|---|
| `src/comiccolor/web/app.py` | controller (app factory) | request-response | First FastAPI code in this repo | RESEARCH.md § Code Examples "`app.frontend()` mount (Pattern 2)" — use verbatim |
| `src/comiccolor/web/deps.py` | middleware (DI) | request-response | First FastAPI dependency-injection code | RESEARCH.md § Code Examples "FastAPI dependency for per-request Store (Pattern 1, full context)" — use verbatim; reconciles `Store`'s "not thread-safe" docstring with FastAPI's threadpool |
| `src/comiccolor/web/schemas.py` | model (Pydantic DTOs) | request-response | No Pydantic anywhere in repo today | RESEARCH.md § Security Domain V5 (Pydantic request models for all JSON bodies); shape request/response DTOs 1:1 against `model/entities.py` dataclasses but keep them separate files/classes — do not reuse the dataclasses as Pydantic models |
| `src/comiccolor/web/routers/project.py`, `page.py`, `palette.py` | controller | CRUD / file-I/O | No HTTP routing code in repo today | RESEARCH.md § Architecture Patterns diagram (which router owns which `Store` calls) + Pitfall 3 (server-generated filenames, never client `UploadFile.filename`) + Pitfall 4 (`Image.open().verify()` before processing, structured 4xx not bare 500) |
| `tests/test_web/*` | test | request-response (integration) | No `fastapi.testclient.TestClient` usage in repo today | RESEARCH.md § Validation Architecture ("Integration test client: `fastapi.testclient.TestClient`, no real uvicorn process needed"); reuse `tests/test_store.py`'s `tmp_path`/fixture conventions for the underlying DB setup only |
| `frontend/src/shell/*`, `frontend/src/palette/*` | component | request-response (fetch) | Zero TypeScript/frontend files exist anywhere in this repo (confirmed by UI-SPEC.md's own greenfield note) | UI-SPEC.md §8 "Screen inventory and shell layout," Color/Typography/Spacing token tables, and Phase-Specific Interaction Contracts §1-7 (these are the binding component contracts, not a code analog) |
| `frontend/src/geometry/transform.ts` | utility | transform | No TS in repo | RESEARCH.md Pattern 6 — full working implementation given, copy directly (`screenToLabelMap`/`labelMapToScreen`/`Viewport` interface) |
| `frontend/tests/transform.test.ts` | test | transform | No Vitest/frontend-test culture in repo | RESEARCH.md § Validation Architecture — Vitest 4.1.10, test at both zoom extremes per Pitfall 7 |
| `frontend/vite.config.ts`, `frontend/package.json` | config | — | No frontend build tooling in repo | RESEARCH.md § Standard Stack install block: `npm create vite@latest frontend -- --template vanilla-ts` |

## Shared Patterns

### Parameterized SQL only, never string-formatted
**Source:** `src/comiccolor/model/store.py`, every method (e.g. lines 142-146, 236-258)
**Apply to:** `model/store.py`'s new/modified methods, and indirectly `web/routers/*.py` (which
must never build raw SQL themselves — always go through `Store`).
```python
cur = self.conn.execute("INSERT INTO series (name) VALUES (?)", (series.name,))
```

### `X | None` union syntax, complete type hints, relative imports
**Source:** every existing module (`entities.py`, `store.py`, `masks.py`, `segmenter.py`)
**Apply to:** all new Python files (`pipeline/`, `colour/`, `web/`) per CLAUDE.md Conventions.
```python
def get_store(project_path: Path = Depends(get_current_project_path)) -> Iterator[Store]:
```

### Docstrings explain *why*, cite § sections
**Source:** every module and class docstring across `model/`, `segmentation/`, `extract/`
(e.g. `masks.py` lines 1-11, `entities.py` lines 1-17, `store.py` lines 1-7)
**Apply to:** all new files, especially `pipeline/stages.py` (cite D-06/D-07/D-10/D-11) and
`colour/extract.py` (cite D-12/D-13/D-14/D-15, flag unvalidated thresholds per RESEARCH.md Pitfall 5).

### Context-manager + `close()` resource pattern
**Source:** `Store.__enter__`/`__exit__`/`close()` (store.py lines 131-138)
```python
def __enter__(self) -> Store:
    return self

def __exit__(self, *exc: object) -> None:
    self.close()
```
**Apply to:** `web/deps.py`'s `get_store` dependency, which wraps this exact context manager per
request (RESEARCH.md Pattern 1) — do not reimplement connection lifecycle, reuse `Store`'s.

### No-RGB-on-Region / colour-lives-in-one-place invariant
**Source:** `model/entities.py` module docstring (lines 3-10), enforced structurally not by review
**Apply to:** any new table this phase adds must hold the same standard — CONTEXT.md code_context
is explicit: "Any new table added this phase must hold to the same standard: make bad states
unrepresentable rather than checked." No RGB columns anywhere except `palette_entry`.

### Server-generated filenames for uploads (new this phase, no existing analog but a named rule)
**Source:** RESEARCH.md Pitfall 3, § Security Domain V12
**Apply to:** `web/routers/page.py`, `web/routers/palette.py` — never use `UploadFile.filename` as
a path component; generate a UUID or DB-id-based filename server-side.

### Structured 4xx over Pillow/OpenCV exceptions (new this phase)
**Source:** RESEARCH.md Pitfall 4
**Apply to:** all upload-handling routers — wrap `Image.open(...).verify()` in `try/except`, return
the Copywriting Contract's error shape ("Upload failed: the file isn't a readable image — try a
PNG, JPG or TIFF."), never let an exception surface as a bare 500.

## Metadata

**Analog search scope:** `src/comiccolor/model/`, `src/comiccolor/segmentation/`,
`src/comiccolor/extract/`, `src/comiccolor/cli.py`, `tests/`, `pyproject.toml`
**Files scanned:** `entities.py`, `store.py`, `masks.py`, `segmenter.py`, `extract/base.py`,
`extract/passthrough.py`, `extract/manga_line.py`, `cli.py`, `pyproject.toml`, `test_store.py`
(read directly this session); `test_masks.py`, `test_trappedball.py`, `test_panels.py`,
`test_hatching.py` (located, not re-read — same fixture/assertion conventions already captured
from `test_store.py` and RESEARCH.md's own worked examples)
**Pattern extraction date:** 2026-08-10
