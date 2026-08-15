---
phase: 01-foundation-project-palette-pipeline-backbone
plan: 06
subsystem: api
tags: [fastapi, pydantic, sqlite, uploads, app-factory]

# Dependency graph
requires:
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Project-scoped Store surface, PipelineStage enum (plan 01-03)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "Pipeline stage registry (Stage/STAGES) for pipeline.py to serialise later (plan 01-04)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "extract_palette/EmptyImageError for palette.py/reference.py to call later (plan 01-05)"
  - phase: 01-foundation-project-palette-pipeline-backbone
    provides: "tests/test_web scaffold, conftest fixtures, 19 skip-marked route stubs (plan 01-01)"
provides:
  - "src/comiccolor/web/schemas.py — every Pydantic DTO the phase's routers use, 22 models"
  - "src/comiccolor/web/deps.py — get_current_project_path/get_store/get_project, set_current_project/clear_current_project"
  - "src/comiccolor/web/uploads.py — decode_image/save_upload/display_name, the single upload choke point"
  - "src/comiccolor/web/appconfig.py — project-folder layout constants, recents index"
  - "src/comiccolor/web/app.py — create_app(), six routers registered, conditional SPA mount"
  - "src/comiccolor/web/routers/{project,volume,page,pipeline,palette,reference}.py — empty stub routers"
  - "comiccolor serve CLI subcommand"
affects: ["01-07", "01-08", "01-09", "01-10"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-request Store via FastAPI dependency injection (get_store): with Store(path) as store: yield store — never a shared connection"
    - "Server-generated uuid4().hex upload filenames; client filename only ever becomes display_name(), never a path component"
    - "app.state.current_project_path written only inside deps.py (set_current_project/clear_current_project)"
    - "Empty APIRouter() stubs registered up front so app.py/schemas.py never appear in a later plan's files_modified"

key-files:
  created:
    - src/comiccolor/web/__init__.py
    - src/comiccolor/web/schemas.py
    - src/comiccolor/web/appconfig.py
    - src/comiccolor/web/deps.py
    - src/comiccolor/web/uploads.py
    - src/comiccolor/web/app.py
    - src/comiccolor/web/routers/__init__.py
    - src/comiccolor/web/routers/project.py
    - src/comiccolor/web/routers/volume.py
    - src/comiccolor/web/routers/page.py
    - src/comiccolor/web/routers/pipeline.py
    - src/comiccolor/web/routers/palette.py
    - src/comiccolor/web/routers/reference.py
  modified:
    - src/comiccolor/cli.py
    - tests/test_web/conftest.py
    - tests/test_web/test_project_routes.py

key-decisions:
  - "The single test_requests_without_an_open_project_return_409 registers a throwaway probe route directly on the app instance (never on a shared router module) so it can prove the get_store/get_project dependency chain before any real router body exists, while still honouring the plan's instruction that all six routers stay literally 'router = APIRouter() plus a docstring' in this plan."
  - "conftest.py's client fixture now opens a real Store with a Project row before calling set_current_project, matching how a real request resolves its project (a folder with no project row and no folder at all both mean 'no project' to get_project)."

requirements-completed: [PROJ-01, PROJ-02, PROJ-03, PROJ-05]

# Metrics
duration: ~55min
completed: 2026-08-15
---

# Phase 1 Plan 6: FastAPI Contracts and App Shell Summary

**Stood up the whole `src/comiccolor/web/` layer's contracts and shell — 22 Pydantic DTOs, the per-request `Store` dependency, the single upload-validation choke point, the project-folder layout, the app factory with six routers (five stubs), and `comiccolor serve` — all built directly against RESEARCH.md's Pattern 1/Pattern 2 rather than an in-repo analog, since this is the first web code the project has ever had.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 3
- **Files modified:** 16 (13 created, 3 modified)

## Accomplishments

- `schemas.py` declares all 22 Pydantic DTOs the phase's four route plans (01-07..01-10) need in one place, with `RGBTuple` (three `0..255`-bounded channels) and `NonEmptyStr` (length-bounded) as shared constrained field types, and `PipelineStage` imported from `comiccolor.model` rather than restated as a string union.
- `appconfig.py` lays out D-04's folder-per-project structure (`pages/`, `references/pending/`, `label_maps/`) and a recents index that silently drops any entry whose folder has vanished — never authoritative over the folder itself.
- `deps.py` gives every request a fresh `Store` on its own connection (`get_store`), resolves the open project from `app.state.current_project_path` (`get_current_project_path`, `get_project`), and is the *only* module that ever writes that process-global attribute (`set_current_project`/`clear_current_project`) — RESEARCH.md Pitfall 2's guard, grep-verified.
- `uploads.py` is the single place untrusted bytes become a file: `decode_image` never lets a Pillow exception surface past a structured 400 carrying the UI-SPEC error sentence verbatim; `save_upload` always writes to a `uuid4().hex`-named file, never the client's own filename; `display_name` strips both POSIX and Windows path components for the artist-visible name only.
- `app.py`'s `create_app()` registers all six routers (`project`, `volume`, `page`, `pipeline`, `palette`, `reference` — all currently empty stubs except the plumbing), `GET /api/health`, an `EmptyImageError` -> 400 handler, and mounts the built SPA via `app.frontend()` (confirmed available on the installed fastapi 0.141.1 per 01-01-SUMMARY) only when `frontend/dist/index.html` exists, with a `StaticFiles(html=True)` fallback kept for a hypothetical downgrade.
- `comiccolor serve --host/--port/--project/--reload` starts the app in one process on loopback by default (`grep -c "0.0.0.0"` returns 0); an invalid `--project` path raises `SystemExit`, matching the file's existing CLI error convention.
- `tests/test_web/conftest.py`'s `client` fixture now opens a real `Store` with a `Project` row and calls `set_current_project` before yielding, matching how a real request resolves its project. `test_requests_without_an_open_project_return_409` is unskipped and implemented — the one test this plan un-skips ahead of every other stub — proving the dependency chain and the 409 guard in one assertion.
- Full suite: `pytest -q` — 71 passed, 18 skipped, 2 xfailed (up from 70 passed/19 skipped at the start of this plan — exactly the one newly-passing test).

## Task Commits

Each task was committed atomically:

1. **Task 1: Declare the whole phase's HTTP contract in one schemas module** - `bd47c5c` (feat)
2. **Task 2: Per-request Store dependency, project-folder layout, recents index, upload choke point** - `66c3834` (feat)
3. **Task 3: App factory, router registration, conditional SPA mount, comiccolor serve** - `c07b60f` (feat)

**Plan metadata:** pending (this commit, docs: complete plan)

## Files Created/Modified

- `src/comiccolor/web/__init__.py` - package docstring only
- `src/comiccolor/web/schemas.py` - all 22 phase-1 DTOs (see full list below)
- `src/comiccolor/web/appconfig.py` - `PROJECT_DB_NAME`/`PAGES_DIR`/`REFERENCES_DIR`/`PENDING_DIR`/`LABEL_MAPS_DIR`/`CONFIG_DIR`/`RECENTS_PATH`/`DEFAULT_WORKSPACE`/`MAX_RECENTS`, `RecentProject`, `create_project_folder`, `is_project_folder`, `read_recents`, `record_recent`, `forget_recent`
- `src/comiccolor/web/deps.py` - `NO_PROJECT_DETAIL`, `get_current_project_path`, `get_store`, `get_project`, `set_current_project`, `clear_current_project`
- `src/comiccolor/web/uploads.py` - `UPLOAD_ERROR_DETAIL`, `MAX_UPLOAD_BYTES`, `MAX_DIMENSION`, `ALLOWED_FORMATS`, `decode_image`, `SavedUpload`, `save_upload`, `display_name`
- `src/comiccolor/web/app.py` - `create_app()`
- `src/comiccolor/web/routers/__init__.py` + `project.py`/`volume.py`/`page.py`/`pipeline.py`/`palette.py`/`reference.py` - each `router = APIRouter()` plus a docstring naming its requirement(s) and owning plan
- `src/comiccolor/cli.py` - added the `serve` subparser and its dispatch branch
- `tests/test_web/conftest.py` - `client` fixture now creates a real `Store`/`Project` and calls `set_current_project`
- `tests/test_web/test_project_routes.py` - unskipped and implemented `test_requests_without_an_open_project_return_409`

## Full DTO List (schemas.py)

**Shared constrained types:** `RGBChannel = Annotated[int, Field(ge=0, le=255)]`, `RGBTuple = tuple[RGBChannel, RGBChannel, RGBChannel]`, `NonEmptyStr = Annotated[str, Field(min_length=1, max_length=200)]`.

- `ProjectCreateRequest {name: NonEmptyStr, parent_dir: str | None = None}`
- `ProjectOpenRequest {path: str}`
- `ProjectResponse {id: int, name: str, path: str, palette_revision: int}`
- `RecentProjectResponse {name: str, path: str, opened_at: str}`
- `BrowseResponse {path: str}`
- `VolumeCreateRequest {name: NonEmptyStr}`
- `VolumeRenameRequest {name: NonEmptyStr}`
- `VolumeResponse {id: int, project_id: int, name: str, page_count: int}`
- `PageResponse {id: int, volume_id: int, index: int, original_name: str, width: int, height: int, stage: PipelineStage, image_url: str}`
- `RejectedUpload {filename: str, detail: str}`
- `PageUploadResponse {accepted: list[PageResponse], rejected: list[RejectedUpload]}`
- `StageResponse {name: PipelineStage, display_name: str, upstream: PipelineStage | None, produces: str, has_runner: bool}`
- `PaletteEntryCreateRequest {rgb: RGBTuple, label: NonEmptyStr}`
- `PaletteEntryUpdateRequest {label: NonEmptyStr | None = None, rgb: RGBTuple | None = None}`
- `PaletteEntryResponse {id: int, rgb: RGBTuple, label: str, entity_id: int | None, revision: int}`
- `PaletteUpdateResponse {entry: PaletteEntryResponse, pages_affected: int}`
- `SwatchExtractResponse {entries: list[PaletteEntryResponse]}`
- `ProposalResponse {index: int, rgb: RGBTuple, pixel_share: float}`
- `SheetProposalResponse {sheet_id: str, image_url: str, proposals: list[ProposalResponse]}`
- `SheetAcceptItem {index: int, part: NonEmptyStr}`
- `SheetAcceptRequest {character_name: NonEmptyStr, items: list[SheetAcceptItem]}`
- `SheetAcceptResponse {entity_id: int, entries: list[PaletteEntryResponse]}`

## deps.py signatures (for 01-07..01-10 to import directly)

```python
NO_PROJECT_DETAIL = "No project is currently open."

def get_current_project_path(request: Request) -> Path: ...        # 409 if unset
def get_store(project_path: Path = Depends(get_current_project_path)) -> Iterator[Store]: ...
def get_project(store: Store = Depends(get_store)) -> Project: ...  # 409 if no project row
def set_current_project(app: FastAPI, path: Path) -> None: ...
def clear_current_project(app: FastAPI) -> None: ...
```

## uploads.py signatures (for 01-08/01-09/01-10 to import directly)

```python
UPLOAD_ERROR_DETAIL = "Upload failed: the file isn't a readable image — try a PNG, JPG or TIFF."
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_DIMENSION = 20000
ALLOWED_FORMATS = {"PNG": ".png", "JPEG": ".jpg", "TIFF": ".tif", "BMP": ".bmp", "WEBP": ".webp"}

def decode_image(data: bytes) -> Image.Image: ...  # raises HTTPException(400, UPLOAD_ERROR_DETAIL)

@dataclass(frozen=True)
class SavedUpload:
    path: Path
    relative_path: str
    width: int
    height: int
    format: str

def save_upload(data: bytes, dest_dir: Path, project_root: Path) -> SavedUpload: ...
def display_name(filename: str | None) -> str: ...  # display-only, never a path component
```

## appconfig.py constant values

```
PROJECT_DB_NAME = "project.db"
PAGES_DIR       = "pages"
REFERENCES_DIR  = "references"
PENDING_DIR     = "references/pending"
LABEL_MAPS_DIR  = "label_maps"
CONFIG_DIR      = Path.home() / ".comiccolor"
RECENTS_PATH    = CONFIG_DIR / "recent.json"
DEFAULT_WORKSPACE = Path.home() / "ComicColor"
MAX_RECENTS     = 10
```

`create_project_folder(parent, name) -> Path` raises `FileExistsError` if `project.db` already exists at the target. `is_project_folder(path) -> bool` requires both a directory and a `project.db` file inside it — a freshly created folder is not yet a project by this definition. `read_recents()` tolerates a missing/corrupt file (returns `[]`) and filters out any entry whose folder no longer passes `is_project_folder`. `record_recent`/`forget_recent` write atomically (temp file + `os.replace`).

## SPA mount: app.frontend() used, not the fallback

01-01-SUMMARY confirmed `fastapi==0.141.1` with `hasattr(FastAPI(), "frontend")` `True`. `create_app()` checks `hasattr(app, "frontend")` at runtime and calls `app.frontend("/", directory=dist_dir)` when true; the `StaticFiles(html=True)` branch exists only as a defensive fallback for a hypothetical dependency downgrade and was not exercised this session (no `frontend/dist/` exists yet in this phase).

## Decisions Made

- The one un-skipped test (`test_requests_without_an_open_project_return_409`) registers a throwaway probe route directly on the `app` instance inside the test itself — not on any shared router module — so it can prove the `get_store`/`get_project` dependency chain and the 409 guard before any router body exists, while every router module stays literally `router = APIRouter()` plus a docstring as the plan's action text specifies. This resolves an internal tension in the plan: the acceptance criteria's own escape-hatch clause ("if an APIRouter with no routes contributes no path...") anticipates that no router will have a real path yet, while the test itself is asked to assert against `/api/palette` specifically. The probe approach satisfies both: it exercises the exact `/api/palette` path named in the plan, without adding real functionality to `palette.py` ahead of plan 01-09.
- `conftest.py`'s `client` fixture was changed to open a real `Store` with a `Project` row (via `Store.add_project`) before calling `set_current_project`, rather than just pointing `app.state.current_project_path` at an empty folder as Wave 0 had it. This matches how a real request actually resolves its project (`get_project` reads `store.the_project()`), and is what the plan's Task 3 action text specifies.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reworded two acceptance-criteria-tripping literal strings out of docstrings**
- **Found during:** Task 2 acceptance-criteria verification
- **Issue:** `deps.py`'s module docstring explained the rejected alternative design using the literal substring `check_same_thread=False`, and `uploads.py`'s docstrings explained the mitigation using the literal substring `UploadFile.filename` (twice) and `.verify()` (once, in addition to the one real code occurrence) — each explaining *why* a pattern is avoided by naming it, which tripped the plan's own grep-based acceptance criteria (`grep -c "check_same_thread"` must return `0`; `grep -c "UploadFile.filename\|file.filename"` must return `0`; `grep -c "\.verify()"` must return exactly `1`), the same class of self-referential documentation conflict 01-04-SUMMARY records for `stages.py`/`PanelStageRun`.
- **Fix:** Reworded each docstring to describe the same design decision without the literal tripping substring (e.g. "a single long-lived connection shared across the threadpool with SQLite's thread check disabled" instead of naming the flag; "the client's own filename never reaches path construction" instead of naming the attribute).
- **Files modified:** `src/comiccolor/web/deps.py`, `src/comiccolor/web/uploads.py`
- **Verification:** All six of Task 2's grep-based acceptance criteria re-run and confirmed passing after the reword; `pytest -q` stayed green throughout.
- **Committed in:** `66c3834` (Task 2 commit — caught and fixed before the commit was made)

---

**Total deviations:** 1 auto-fixed (1 blocking — acceptance-criteria conflict resolved by rewording, no behavior change)
**Impact on plan:** No scope creep. Every mitigation described is still fully documented; only the literal substring used to name the avoided pattern changed.

## Issues Encountered

- No `.venv` existed inside this worktree (worktrees are separate checkouts; the shared `.venv` at the main checkout's `pyproject.toml` install doesn't follow into a worktree's own `src/`). Created a fresh `.venv` in the worktree and ran `pip install -e ".[web,dev]"` before any verification command could run — this is expected worktree setup, not a plan deviation, and is called out here only because it consumed real time before Task 1's work began.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `schemas.py`, `deps.py`, `uploads.py`, `appconfig.py` and `app.py` are complete and stable — plans 01-07 through 01-10 build directly against the signatures recorded above and should never need to touch `app.py` or `schemas.py`.
- All six routers exist as empty, importable stubs with `router = APIRouter()` — 01-07 (`project.py`), 01-08 (`volume.py`/`page.py`/`pipeline.py`), 01-09 (`palette.py`), 01-10 (`reference.py`) each own exactly one module and can run in parallel without file contention.
- `comiccolor serve` is a real, working entry point (`--host`/`--port`/`--project`/`--reload`), loopback-only by default.
- No blockers for any Wave-4+ plan in this phase.

---
*Phase: 01-foundation-project-palette-pipeline-backbone*
*Completed: 2026-08-15*

## Self-Check: PASSED

All 13 created files and this SUMMARY.md verified present on disk. All three
task commits (`bd47c5c`, `66c3834`, `c07b60f`) verified present in `git log`.
