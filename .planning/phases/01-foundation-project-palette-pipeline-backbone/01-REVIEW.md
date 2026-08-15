---
phase: 01-foundation-project-palette-pipeline-backbone
reviewed: 2026-08-15T21:13:12Z
depth: standard
files_reviewed: 61
files_reviewed_list:
  - src/comiccolor/cli.py
  - src/comiccolor/colour/__init__.py
  - src/comiccolor/colour/extract.py
  - src/comiccolor/model/__init__.py
  - src/comiccolor/model/entities.py
  - src/comiccolor/model/masks.py
  - src/comiccolor/model/store.py
  - src/comiccolor/pipeline/__init__.py
  - src/comiccolor/pipeline/runner.py
  - src/comiccolor/pipeline/stages.py
  - src/comiccolor/web/__init__.py
  - src/comiccolor/web/app.py
  - src/comiccolor/web/appconfig.py
  - src/comiccolor/web/deps.py
  - src/comiccolor/web/routers/__init__.py
  - src/comiccolor/web/routers/page.py
  - src/comiccolor/web/routers/palette.py
  - src/comiccolor/web/routers/pipeline.py
  - src/comiccolor/web/routers/project.py
  - src/comiccolor/web/routers/reference.py
  - src/comiccolor/web/routers/volume.py
  - src/comiccolor/web/schemas.py
  - src/comiccolor/web/uploads.py
  - frontend/src/api/client.ts
  - frontend/src/api/types.ts
  - frontend/src/components/proposalCard.ts
  - frontend/src/components/stageStrip.ts
  - frontend/src/components/swatchCard.ts
  - frontend/src/components/toast.ts
  - frontend/src/components/uploadDrop.ts
  - frontend/src/geometry/transform.ts
  - frontend/src/main.ts
  - frontend/src/shell/router.ts
  - frontend/src/shell/sidebar.ts
  - frontend/src/shell/toolbar.ts
  - frontend/src/views/pageDetail.ts
  - frontend/src/views/pageGrid.ts
  - frontend/src/views/palette.ts
  - frontend/src/views/projectPicker.ts
  - frontend/src/styles/base.css
  - frontend/src/styles/pages.css
  - frontend/src/styles/palette.css
  - frontend/src/styles/shell.css
  - frontend/src/styles/tokens.css
  - tests/test_extract.py
  - tests/test_masks.py
  - tests/test_pipeline.py
  - tests/test_store.py
  - tests/test_web/conftest.py
  - tests/test_web/test_page_routes.py
  - tests/test_web/test_palette_routes.py
  - tests/test_web/test_project_routes.py
  - frontend/tests/client.test.ts
  - frontend/tests/palette.test.ts
  - frontend/tests/projectPicker.test.ts
  - frontend/tests/proposalCard.test.ts
  - frontend/tests/router.test.ts
  - frontend/tests/stageStrip.test.ts
  - frontend/tests/transform.test.ts
  - frontend/tests/uploadDrop.test.ts
  - pyproject.toml
findings:
  critical: 4
  warning: 20
  info: 8
  total: 32
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-08-15T21:13:12Z
**Depth:** standard
**Files Reviewed:** 61
**Status:** issues_found

## Summary

Phase 1 delivers the FastAPI backend, SQLite persistence, pipeline registry, and a
vanilla-TS SPA shell. The documentation-per-module discipline is unusually strong, and
CLAUDE.md's non-negotiable invariants hold: `region` has no RGB column, `Region` has no
RGB field, `PaletteEntry` is the only colour home, label maps stay exclusive/exhaustive,
and nothing learned entered the segmentation layer. **No invariant violations found.**

That is the good news. The bad news is that several of the module docstrings assert
safety properties the code does not actually have, and the test suite — which passes,
96 green — is structured in a way that cannot observe any of them.

Four Critical findings, three of which I reproduced against the running app:

1. **The `get_store` seam is broken under concurrency.** The prompt asked me to check
   every handler for `async def`; there are none, all handlers are correctly sync. But
   that is not sufficient. FastAPI runs the dependency's `__enter__`, the endpoint, and
   the dependency's `__exit__` as **three separate** `run_in_threadpool` calls, and
   anyio does not guarantee the same worker thread across them. `sqlite3.connect` is
   called with the default `check_same_thread=True`. I ran 8 concurrent
   `GET /api/palette` requests against the real app: **the very first round raised
   `sqlite3.ProgrammingError`.** The frontend issues exactly this concurrency
   (`Promise.all` in `sidebar.refresh`, `pageGrid.boot`, `pageDetail.boot`, plus the
   sidebar and the mounted view booting simultaneously). `TestClient` is sequential, so
   the entire web test suite is blind to it.

2. **`POST /api/projects` builds a directory path from an unvalidated client string.**
   `body.name` goes straight into `parent / name`. I created a project at
   `../secret/pwned` (escaping `parent_dir`) and at an absolute path (ignoring
   `parent_dir` entirely). Both returned 201 and wrote `project.db` outside the intended
   workspace. `_resolve_project_path` guards `POST /open` carefully; the create path has
   no equivalent guard at all.

3. **`POST /api/pages/` never validates `volume_id`.** `volume.py` has
   `_get_owned_volume`; `page.py` has no equivalent. Uploading to a nonexistent volume
   returns a bare 500 (FK violation) *after* the image bytes are already written to
   `pages/`, leaving an orphaned file. The module docstring claims a bad file "becomes a
   `RejectedUpload` entry, never an unhandled exception and never a bare 500."

4. **Partial sheet accept destroys the sheet.** `accept_sheet` moves the pending file
   out of `pending/` unconditionally, so accepting 1 of 2 proposals makes the second one
   permanently unacceptable — the server 404s while `palette.ts` still renders it as a
   live, clickable card.

The frontend has a second systemic problem: `boot()`/`refresh()` in four modules have no
`try`/`catch`, so a 409 (no project open) produces an unhandled rejection and a blank
screen; and every `catch` that does exist is gated on `err instanceof ApiError`, so a
network failure (`fetch` throws `TypeError`) is silently swallowed with no UI at all.
Frontend vitest runs in `environment: "node"` and only imports pure helpers — every
render function, every view, and the entire `api` fetch object are untested.

---

## Critical Issues

### CR-01: Per-request `Store` is used across threadpool threads — `sqlite3.ProgrammingError` under any concurrency

**File:** `src/comiccolor/web/deps.py:49-51`, `src/comiccolor/model/store.py:138`
**Issue:** `get_store` is a sync generator dependency. FastAPI resolves it via
`contextmanager_in_threadpool`, which issues `run_in_threadpool(cm.__enter__)`, then the
endpoint via a *separate* `run_in_threadpool(dependant.call)`, then
`anyio.to_thread.run_sync(cm.__exit__, ...)`. anyio hands out whichever worker is idle;
under concurrent requests that is not the same thread. `Store.__init__` calls
`sqlite3.connect(self.path)` with the default `check_same_thread=True`, so the connection
raises the moment the endpoint runs on a different worker than the one that built it.

Reproduced against the real app (`httpx.ASGITransport`, 8 concurrent
`GET /api/palette`), failing on round 0:

```
ProgrammingError: SQLite objects created in a thread can only be used in that same
thread. The object was created in thread id 25180 and this is thread id ...
```

The frontend guarantees this concurrency — `sidebar.ts:154`
(`Promise.all([api.projects.current(), api.volumes.list()])`) fires two store-backed
requests at once on every page load, and the sidebar boots in parallel with whichever
view the router mounts. `deps.py`'s docstring explicitly rejects
"a single long-lived connection ... with SQLite's thread check disabled" as the unsafe
alternative, but the safe-looking alternative it chose is not safe either without
disabling the per-object check.

**Fix:** Each `Store` is still confined to exactly one request (no sharing), so
disabling the *object-level* thread assertion is correct here; the connection is never
touched by two threads at the same time.

```python
# src/comiccolor/model/store.py
def __init__(self, path: str | Path) -> None:
    self.path = Path(path)
    self.path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI resolves a sync generator dependency,
    # the endpoint, and the dependency teardown as three separate
    # run_in_threadpool calls, and anyio makes no same-worker guarantee. The
    # connection is still owned by exactly one request at a time, so the
    # object-level thread assertion is the only thing that must be relaxed.
    self.conn = sqlite3.connect(self.path, check_same_thread=False)
```

And add a regression test that TestClient cannot fake — concurrent requests through
`httpx.AsyncClient(transport=ASGITransport(app=app))` with `asyncio.gather`.

---

### CR-02: Path traversal — client-supplied project `name` is used as a filesystem path component

**File:** `src/comiccolor/web/routers/project.py:99-115`, `src/comiccolor/web/appconfig.py:41-55`, `src/comiccolor/web/schemas.py:40-42`
**Issue:** `create_project` passes `body.name` verbatim to
`appconfig.create_project_folder(parent, body.name)`, which does `parent / name`.
`ProjectCreateRequest.name` is only constrained by `NonEmptyStr` (length 1..200) — no
character set, no separator rejection. `pathlib`'s `/` operator also lets an *absolute*
name discard `parent` entirely.

Reproduced, both returning 201:

```
{"name": "../secret/pwned", "parent_dir": "<tmp>/workspace"}
  -> created <tmp>/secret/pwned/{project.db,pages,references,label_maps}
{"name": "C:\\...\\abs_escape"}
  -> created C:\...\abs_escape  (parent_dir ignored entirely)
```

`parent_dir` is likewise passed through `expanduser().resolve()` with no containment
check. The module docstring claims "Every path a client supplies ... goes through
`_resolve_project_path` before this process opens a database at it" — the create route
does not, and it is the one route that *writes*. This directly contradicts the
`display_name`/`save_upload` discipline `uploads.py` establishes for the exact same class
of input.

**Fix:** Constrain the name to a single safe path segment at the schema boundary, and
re-assert containment in `create_project_folder`.

```python
# schemas.py
ProjectName = Annotated[
    str,
    Field(min_length=1, max_length=100, pattern=r"^[^\\/:*?\"<>|\x00-\x1f.][^\\/:*?\"<>|\x00-\x1f]*$"),
]

class ProjectCreateRequest(BaseModel):
    name: ProjectName
    parent_dir: str | None = None
```

```python
# appconfig.py
def create_project_folder(parent: Path, name: str) -> Path:
    parent = parent.resolve()
    project_dir = (parent / name).resolve()
    if project_dir.parent != parent:
        raise ValueError(f"project name must be a single folder name, got {name!r}")
    ...
```

Add a route test asserting `{"name": "../escape"}` is a 4xx and that nothing was created
outside `parent_dir`.

---

### CR-03: `POST /api/pages/` accepts any `volume_id` — bare 500 plus an orphaned file on disk

**File:** `src/comiccolor/web/routers/page.py:72-127`
**Issue:** `volume_id` arrives as a raw query parameter and is never checked for
existence or for belonging to the currently open project. `volume.py:47` has
`_get_owned_volume` for precisely this; `page.py` has no equivalent and never calls it.
`save_upload` writes the image bytes **before** `store.add_page`, so when the foreign-key
constraint fires the file is already on disk and the request dies as an unhandled
`sqlite3.IntegrityError`.

Reproduced:

```
POST /api/pages/?volume_id=9999  ->  500 Internal Server Error
orphan files in pages/: 1
```

This also breaks the batch contract: a mid-batch failure aborts the loop, so earlier
accepted pages in the same request are persisted but never reported to the client, while
later files are never processed. The module docstring's promise — "a bad file in a batch
is reported in `rejected` without losing the good ones" — does not hold for this failure
mode.

**Fix:** Validate ownership once, before the loop, and keep the 500 path closed.

```python
from .volume import _get_owned_volume, VOLUME_NOT_FOUND_DETAIL
from ..deps import get_project

@router.post("/", status_code=201)
def upload_pages(
    volume_id: int,
    files: list[UploadFile],
    project_root: Path = Depends(get_current_project_path),
    store: Store = Depends(get_store),
    project: Project = Depends(get_project),
) -> PageUploadResponse:
    _get_owned_volume(volume_id, project, store)   # 404 before a byte is written
    ...
```

Consider also deleting `saved.path` if `store.add_page` raises, so a failed insert leaves
no orphan.

---

### CR-04: Partial sheet accept consumes the sheet — remaining proposals become permanently unacceptable

**File:** `src/comiccolor/web/routers/reference.py:228-249`, `frontend/src/views/palette.ts:510-524`
**Issue:** `accept_sheet` moves the pending file out of `pending/` into `references/`
unconditionally, regardless of how many of the sheet's proposals were listed in
`body.items`. The accept route can only re-derive proposals from the *pending* file
(`_pending_path`), so any second accept for the same sheet 404s. Meanwhile
`palette.ts:521` removes only the accepted indices from `proposals` and re-renders the
rest as live, selectable cards with a working Accept button.

Reproduced:

```
proposals: 2
first accept  (index 0) -> 201
second accept (index 1) -> 404 "That character sheet is no longer available — upload it again."
```

Accepting an empty `items` list has the same effect: the sheet is consumed, an `Entity`
is created with zero entries, and the artist's uploaded sheet is gone from `pending/`
with nothing to show for it (also reproduced — 201, `pending/` empty).

**Fix:** Pick one and make the client match it.

- Server-side (preferred): only move the file when `body.items` is non-empty **and** the
  accept was the artist's final action, or leave the file in `pending/` and have
  `discard_sheet` be the only thing that consumes it. Copy rather than `replace` into
  `references/`, and add the reference path only once per entity.
- Client-side: after a successful accept, clear `sheetId`, `proposals` and the proposal
  grid so the consumed sheet cannot be acted on again:

```ts
// palette.ts, after a successful accept
sheetId = null;
proposals = [];
proposalState.clear();
sheetImage.hidden = true;
discardSheetButton.hidden = true;
renderProposalGrid();
updateAcceptForm();
```

Also reject an empty `items` list with a 400 rather than silently consuming the sheet.

---

## Warnings

### WR-01: `deps.py` does not document the sync-handler thread-affinity contract it depends on

**File:** `src/comiccolor/web/deps.py:1-27, 49-51`
**Issue:** The module docstring mentions "FastAPI running sync routes on a threadpool"
but never states the actual rule a contributor must follow: **every route depending on
`get_store` must be a plain `def`, never `async def`.** That rule is written down exactly
once in the entire codebase, buried in `palette.py:174-180`'s `upload_swatch` docstring —
a place nobody adding a route to `page.py` or `volume.py` will read. All 20 handlers are
currently correct; the first `async def` added silently breaks them.
**Fix:** Add the rule to `deps.py`'s docstring beside `get_store`, and add a test that
walks `app.routes` asserting no route endpoint depending on `get_store` is a coroutine
function (`inspect.iscoroutinefunction`).

### WR-02: `read_recents` is not tolerant of a corrupt file, despite claiming to be

**File:** `src/comiccolor/web/appconfig.py:68-87`
**Issue:** The `except` clause catches only `OSError` and `json.JSONDecodeError`.
`RecentProject(**item)` raises an uncaught `TypeError` on any dict carrying an extra key
(`_looks_like_recent` checks only that the three required keys are a *subset*), and
iterating `raw` raises `TypeError` if the JSON top level is not a list. Both surface as a
500 on `GET /api/projects/recent`, which is the first request the project picker makes —
the artist's entry screen breaks with no in-app recovery.

Reproduced:

```
recent.json = [{"name":..,"path":..,"opened_at":..,"extra":1}]  -> 500
recent.json = 5                                                  -> 500
```

**Fix:**

```python
try:
    raw = json.loads(RECENTS_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    return []
if not isinstance(raw, list):
    return []
entries = [
    RecentProject(name=i["name"], path=i["path"], opened_at=i["opened_at"])
    for i in raw
    if _looks_like_recent(i)
]
```

Building from named keys (not `**item`) makes the function forward-compatible with any
future field as well.

### WR-03: `GET /api/pages/{id}/image` returns a bare 500 when the file is missing on disk

**File:** `src/comiccolor/web/routers/page.py:147-161`
**Issue:** The containment assertion is correct, but nothing checks that `resolved`
actually exists. Starlette's `FileResponse` raises at send time for a missing file.
An artist who moved, renamed or deleted a page image outside the app (which D-04's
"copy the folder" model actively encourages) gets a 500. Reproduced: 500 after unlinking
the page file.
**Fix:**

```python
if not resolved.is_file():
    raise HTTPException(status_code=404, detail=PAGE_NOT_FOUND_DETAIL)
return FileResponse(resolved)
```

### WR-04: Upload size limit is enforced after the whole payload is already in memory

**File:** `src/comiccolor/web/uploads.py:49-76`, `src/comiccolor/web/routers/page.py:94`, `palette.py:182`, `reference.py:154`
**Issue:** Every caller does `file.file.read()` — an unbounded read of the whole spooled
upload into a `bytes` — and only *then* does `decode_image` compare `len(data)` against
`MAX_UPLOAD_BYTES`. The limit therefore never prevents the allocation it exists to
prevent. Separately, `decode_image` calls `image.load()` (full decode) *before* checking
`MAX_DIMENSION`, so a decompression-bomb-shaped file is fully rasterised before the
dimension guard runs; only Pillow's own `MAX_IMAGE_PIXELS` stands between that and
hundreds of MB of resident pixels. Note `MAX_DIMENSION = 20000` (400 Mpx) is above
Pillow's default bomb threshold, so the constant is largely unreachable as written.
**Fix:** Stream-read with a cap at the router, and check `probe.size` (available after
`Image.open`, before `load()`) rather than `image.size`:

```python
probe = Image.open(BytesIO(data))
probe.verify()
if probe.format not in ALLOWED_FORMATS:
    raise HTTPException(400, UPLOAD_ERROR_DETAIL)
if not (1 <= probe.width <= MAX_DIMENSION and 1 <= probe.height <= MAX_DIMENSION):
    raise HTTPException(400, UPLOAD_ERROR_DETAIL)
image = Image.open(BytesIO(data)); image.load()
```

### WR-05: `accept_sheet` is non-atomic — a DB failure after the file move loses the sheet

**File:** `src/comiccolor/web/routers/reference.py:242-261`
**Issue:** `pending.replace(dest)` runs before `set_entity_reference_images` and before
any `add_palette_entry`. If any of those raise (disk full, constraint, interrupted
request), the file has already left `pending/` and the accept can never be retried —
`_pending_path` 404s from then on. The route is documented as doing everything "in one
request" but has no transactional boundary.
**Fix:** Write the palette entries and entity reference first, then move the file last;
or copy to `references/` and unlink from `pending/` only after every write commits.

### WR-06: A rejected character sheet leaves an unreachable orphan file in `pending/`

**File:** `src/comiccolor/web/routers/reference.py:154-160`
**Issue:** `save_upload` writes the bytes to `pending/` *before* `extract_palette` runs.
When the sheet is all-ink/all-paper, `EmptyImageError` propagates to the app-level 400
handler and the response carries no `sheet_id` — so the client can never call
`DELETE /sheets/{id}` for it. The file is unreachable and permanent. Reproduced: 400
returned, `pending/` count went 0 → 1.
**Fix:** Extract before saving, and only persist the file once extraction succeeds:

```python
image = uploads.decode_image(data)
proposals = extract_palette(image, sheet_mode=True)   # may raise EmptyImageError
saved = uploads.save_upload(data, project_root / PENDING_DIR, project_root)
```

### WR-07: `update_palette_entry` can pass `None` into `_entry_response`

**File:** `src/comiccolor/web/routers/palette.py:120-124`
**Issue:** `updated = store.palette_entry_by_id(entry_id)` is typed
`PaletteEntry | None` and is used unguarded. If the row disappeared between the
existence check on line 111 and the re-read (concurrent DELETE), this is an
`AttributeError` → 500 rather than the 404 the route already has copy for. Also, a
`PATCH` with an empty body `{}` returns 200 having done nothing (reproduced) — arguably
fine, but undocumented.
**Fix:**

```python
updated = store.palette_entry_by_id(entry_id)
if updated is None:
    raise HTTPException(status_code=404, detail=ENTRY_NOT_FOUND_DETAIL)
```

### WR-08: `delete_palette_entry` does not bump `project.palette_revision`

**File:** `src/comiccolor/model/store.py:396-401`
**Issue:** `add_palette_entry` bumps it, `update_palette_rgb` bumps it,
`update_palette_label` deliberately does not (documented — the colour did not change).
Delete changes colour state materially (`region.palette_entry_id` becomes NULL via
`ON DELETE SET NULL`) but silently leaves `palette_revision` unchanged.
`entities.py:141` documents the field as "Bumped on every palette mutation. ... A
renderer caches against this." A renderer keyed on `palette_revision` will serve stale
pixels after a delete — the exact §6 incremental-propagation case the field exists for.
**Fix:**

```python
def delete_palette_entry(self, entry_id: int) -> None:
    self._execute(
        "UPDATE project SET palette_revision = palette_revision + 1 WHERE id ="
        " (SELECT project_id FROM palette_entry WHERE id = ?)",
        (entry_id,),
    )
    self._execute("DELETE FROM palette_entry WHERE id = ?", (entry_id,))
    self.conn.commit()
```

### WR-09: No Origin/CSRF protection on the multipart write endpoints

**File:** `src/comiccolor/web/app.py:36-58`
**Issue:** The app registers no CORS or origin-checking middleware and has no
authentication by design. JSON endpoints are incidentally protected (an
`application/json` body forces a CORS preflight a hostile origin cannot satisfy), but
`multipart/form-data` is a CORS-*simple* content type. Any web page the artist visits
while `comiccolor serve` is running can silently `POST` a cross-origin form to
`http://127.0.0.1:8000/api/pages/?volume_id=1`, `/api/palette/swatch` or
`/api/references/sheets` and write files plus database rows into the open project. The
same applies to `POST /api/projects/browse`, which pops a native tkinter dialog on the
artist's desktop.
`client.ts:8-12` documents a T-01-ORIGIN concern for the *outbound* direction only.
**Fix:** Add a small middleware rejecting any state-changing request whose `Origin`
header is present and not in `{http://127.0.0.1:<port>, http://localhost:<port>, the vite
dev origin}`. Cheap, and it closes the whole class.

### WR-10: Unhandled promise rejections on every view boot — blank screen, no error UI

**File:** `frontend/src/shell/sidebar.ts:153-169,199`; `frontend/src/views/pageGrid.ts:42-54`; `frontend/src/views/pageDetail.ts:67-77`
**Issue:** `refresh()` and both `boot()` functions `await` API calls with no
`try`/`catch`, and are invoked as `void boot()`. With no project open,
`api.projects.current()` returns 409 → `ApiError` thrown → unhandled rejection. This is
the *guaranteed first-load state*: `main.ts:19` renders the sidebar unconditionally
before any project exists, so a fresh start always logs an unhandled rejection and leaves
the sidebar permanently blank. Navigating directly to `#/volume/1` or `#/page/1` without
a project produces a blank content region with no message at all.
**Fix:** Wrap each `boot`/`refresh` body in `try`/`catch` and render an inline error
banner using `err.detail`, matching the error handling already present in `palette.ts`
and `projectPicker.ts`.

### WR-11: Non-`ApiError` failures are silently swallowed in every catch block

**File:** `frontend/src/views/palette.ts:128-131,153-157,173-175,202-204,231-234,287-290,525-530,539-542`; `frontend/src/views/projectPicker.ts:150-152,196-198,213-219,236-239`
**Issue:** The pattern `catch (err) { if (err instanceof ApiError) showError(err.detail); }`
appears twelve times. `fetch` rejects with a `TypeError` (not `ApiError`) when the
network is down or the server process died — the single most likely failure on a
local-first app. Every one of those catches then does *nothing*: no banner, no toast, no
console output. The artist clicks Delete, nothing happens, and the app gives no signal at
all. `loadPalette` is worse: it also sets `entries = []`, so a failed load renders as an
empty palette indistinguishable from a genuinely empty one.
**Fix:** Add an `else` branch everywhere, e.g. a shared helper:

```ts
function detailOf(err: unknown): string {
  return err instanceof ApiError
    ? err.detail
    : "Couldn't reach the app — check it's still running, then try again.";
}
```

### WR-12: The sidebar never re-renders, so `currentRoute` and every `.is-current` style are dead

**File:** `frontend/src/main.ts:19`; `frontend/src/shell/sidebar.ts:27,55-57,87-89,112-114`; `frontend/src/styles/shell.css:96-98`
**Issue:** `main.ts` calls `renderSidebar(app)` once with no second argument, so
`currentRoute` is always `undefined` and the three `is-current` branches are unreachable.
`shell.css:96-98` styles selectors that can never be applied. The sidebar also never
refreshes on navigation or on data changes elsewhere: creating a project in the picker
leaves the sidebar project name empty; uploading pages in `pageGrid` leaves the sidebar's
`page_count` stale. The module docstring advertises "The selected volume/page uses the
accent current-item indicator" as a shipped behaviour.
**Fix:** Have `startRouter` re-invoke the sidebar (or expose a `sidebar.setRoute(route)` /
`sidebar.refresh()` handle) on each `resolve()`, and call `refresh()` after
project-create and page-upload.

### WR-13: `swatchCard` holds a stale `entry` snapshot, so a rename can diverge from the server

**File:** `frontend/src/components/swatchCard.ts:84-93`; `frontend/src/views/palette.ts:147-158`
**Issue:** `commitRename` compares against the closure-captured `entry.label`.
`renameEntry` on success replaces `entries[index]` with a *new* object and never
re-renders the grid, so the card's `entry` keeps the original label forever. Rename
"Colour 1" → "Hair", then back to "Colour 1": the second commit sees
`value === entry.label`, treats it as a no-op, and reverts the input — leaving the UI
showing "Colour 1" while the server still holds "Hair". Same staleness applies to the
delete confirmation heading, which is looked up from `entries` (fresh) while the card
shows stale text.
**Fix:** Either mutate in place (`entries[index].label = result.entry.label`) plus a
`renderGrid()` after rename, or have `renderSwatchCard` return a `setEntry(next)` handle
the view calls on success.

### WR-14: Frontend tests cover only pure helpers — no DOM, no fetch layer

**File:** `frontend/vitest.config.ts:4-6`; `frontend/tests/*.test.ts`
**Issue:** `environment: "node"` means there is no DOM, and every test file imports only
pure functions: `apiUrl`, `ApiError.fromResponse`, `partitionUploadResult`,
`screenToLabelMap`/`labelMapToScreen`, `toastCopy`, `segmentStates`, `recentListModel`,
`acceptPayload`/`entryLabel`, `parseRoute`/`buildHash`. Zero tests touch
`renderSwatchCard`, `renderProposalCard`, `renderStageStrip`, `renderUploadDrop`,
`renderSidebar`, `renderPalette`, `renderPageGrid`, `renderPageDetail`,
`renderProjectPicker`, `startRouter`, or the `api` object itself. WR-10, WR-11, WR-12 and
WR-13 are all in that uncovered surface — the suite is green and cannot see any of them.
**Fix:** Add `environment: "jsdom"` (or a second `jsdom` project) plus render tests for
at least the swatch/proposal card commit paths and the router's mount/teardown, and
`vi.stubGlobal("fetch", ...)` tests for `api.*` error propagation.

### WR-15: `pytest tests/` fails on a clean checkout — no `pythonpath`, no root `conftest.py`

**File:** `pyproject.toml:28-29`
**Issue:** `[tool.pytest.ini_options]` sets `testpaths` but not `pythonpath`, and there
is no repo-root `conftest.py` inserting `src/`. Running `pytest tests` in this working
tree gives 9 collection errors: `ModuleNotFoundError: No module named 'comiccolor'`.
The suite passes only with `PYTHONPATH=src` or an editable install, neither of which is
documented anywhere in the reviewed files. CI or a new contributor hits a wall.
**Fix:**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

### WR-16: `comiccolor serve --reload` silently does nothing

**File:** `src/comiccolor/cli.py:113-120`
**Issue:** `uvicorn.run` requires an *import string* to enable reload; passing an `app`
instance with `reload=True` makes uvicorn log a warning and disable reload. The flag is
advertised in `--help` as "reload on source changes (development)" and does not work.
Also `Path(args.project)` is neither `expanduser()`d nor `resolve()`d, so
`--project ~/ComicColor/Kaito` fails with "not a project folder".
**Fix:** Either drop the flag, or branch on it:

```python
if args.reload:
    os.environ["COMICCOLOR_PROJECT"] = str(project_path) if args.project else ""
    uvicorn.run("comiccolor.web.app:create_app", factory=True,
                host=args.host, port=args.port, reload=True)
else:
    uvicorn.run(app, host=args.host, port=args.port)
```

and `Path(args.project).expanduser().resolve()`.

### WR-17: `upload_pages`'s return annotation contradicts its 400 path

**File:** `src/comiccolor/web/routers/page.py:78,119-125`
**Issue:** The handler is annotated `-> PageUploadResponse`, so FastAPI derives
`response_model=PageUploadResponse` and documents 201 only. The all-rejected branch
returns a raw `JSONResponse` with status 400 and a `{detail, rejected}` shape that
appears nowhere in the OpenAPI contract or in `schemas.py`. `uploadWithProgress`
(`uploadDrop.ts:207-218`) has to hand-normalise both shapes because of this.
**Fix:** Declare the shape (`class PageUploadRejection(BaseModel)`), annotate the handler
`-> PageUploadResponse | JSONResponse`, and add
`responses={400: {"model": PageUploadRejection}}` so the contract is discoverable.

### WR-18: Accepting the same proposal index twice creates duplicate palette entries

**File:** `src/comiccolor/web/routers/reference.py:232-261`
**Issue:** `body.items` is validated only for index range. Two items with the same index
and part produce two `PaletteEntry` rows with identical rgb, identical
`{character} / {part}` label and identical `entity_id`. Reproduced — 201 with two
`"K / hair"` entries. There is no uniqueness constraint on `palette_entry(project_id,
label)` to catch it either. `_entry_label`'s docstring claims the shape "produces two
distinct labels under one entity, never a collision" — it does not.
**Fix:** Reject duplicate `(index)` and duplicate `part` values in the request with a
400, and consider `UNIQUE (project_id, label)` on `palette_entry`.

### WR-19: `create_project_folder` silently reuses a non-empty existing directory

**File:** `src/comiccolor/web/appconfig.py:41-55`
**Issue:** The only guard is `(project_dir / PROJECT_DB_NAME).exists()`. A directory that
exists with arbitrary content but no `project.db` is adopted as a project folder and has
`pages/`, `references/pending/` and `label_maps/` created inside it. Combined with CR-02,
this is how the traversal reproduction landed inside `secret/`. It is also a TOCTOU: the
existence check and the `mkdir` are not atomic.
**Fix:** Require the target to not exist, or to exist and be empty:

```python
if project_dir.exists() and any(project_dir.iterdir()):
    raise FileExistsError(f"{project_dir} already exists and is not empty")
```

### WR-20: `record_recent` and `forget_recent` duplicate the atomic-write block verbatim

**File:** `src/comiccolor/web/appconfig.py:108-113, 121-126`
**Issue:** Six lines (mkdir, tmp path, write_text, os.replace) are copy-pasted. Any fix
to the atomic-write logic — for example adding an `os.fsync` or handling a
cross-filesystem `replace` — must be applied twice or it silently regresses one caller.
**Fix:** Extract `def _write_recents(entries: list[RecentProject]) -> None:` and call it
from both.

---

## Info

### IN-01: Every upload is decoded twice

**File:** `src/comiccolor/web/routers/palette.py:183,186`; `src/comiccolor/web/routers/reference.py:155,157`
**Issue:** Both routes call `uploads.decode_image(data)`, then `uploads.save_upload(data,
...)`, which calls `decode_image(data)` again internally on the same bytes.
**Fix:** Add a `save_decoded(image, data, dest_dir, project_root)` variant, or have
`save_upload` accept an already-decoded `Image.Image`.

### IN-02: The swatch image is written to `references/` with no reference to it anywhere

**File:** `src/comiccolor/web/routers/palette.py:186`
**Issue:** `uploads.save_upload(...)`'s return value is discarded; no database row, no
`sheet_id`, no URL. Every swatch upload leaves a permanently orphaned file the artist
cannot see or delete from the app. Unlike a pending sheet, nothing ever cleans it up.
**Fix:** Either drop the write, or record the path (e.g. on the project) so it is
reachable.

### IN-03: `relabel_sequential` raises on an empty label map

**File:** `src/comiccolor/model/masks.py:140-146`
**Issue:** `int(label_map.max())` raises `ValueError` on a zero-size array.
`region_stats` guards this case (`if flat.size`); `relabel_sequential` does not, so the
two functions disagree about the empty input contract.
**Fix:** `if label_map.size == 0: return label_map.astype(np.int32)`.

### IN-04: Mixed quote style within one file

**File:** `frontend/src/components/swatchCard.ts:67,70,71`
**Issue:** Three `addEventListener` calls use single quotes; every other string in the
file (and the codebase) uses double quotes. Suggests a hand-patch that skipped the
formatter.
**Fix:** Normalise to double quotes.

### IN-05: `_REPO_ROOT` is wrong for an installed package

**File:** `src/comiccolor/web/app.py:33`
**Issue:** `parents[3]` is only the repo root for a source checkout. Installed into
`site-packages` it points somewhere arbitrary; the `index.html` check then fails and the
SPA silently never mounts. The `COMICCOLOR_FRONTEND_DIST` override exists but is
undiscoverable — `serve` gives no hint when the mount is skipped.
**Fix:** Log (or return in `/api/health`) whether the SPA mounted, so the failure is
visible.

### IN-06: `reference.py` imports a private helper across module boundaries

**File:** `src/comiccolor/web/routers/reference.py:47`
**Issue:** `from .palette import _entry_response` — a leading-underscore name imported by
another module, contrary to the CLAUDE.md convention that `_`-prefixed functions are
module-internal.
**Fix:** Promote it to `entry_response` in a shared `routers/_shared.py` (or `schemas.py`
as a classmethod `PaletteEntryResponse.of(entry)`).

### IN-07: `update_palette_rgb`'s return value is dead

**File:** `src/comiccolor/model/store.py:403-425`; `src/comiccolor/web/routers/palette.py:118-120`
**Issue:** The method runs an extra `SELECT` to return the new revision; the only caller
discards it and immediately re-reads the whole entry. The extra query is pure waste and
the documented return contract is unexercised.
**Fix:** Either use the returned revision or make the method return `None`.

### IN-08: Registry helpers declared but never called

**File:** `src/comiccolor/pipeline/stages.py:136-141`; `src/comiccolor/pipeline/runner.py:43-57`; `src/comiccolor/model/masks.py:88-104`
**Issue:** `next_stage`, `run_stage`, `regions_to_cover`, `save_binary_mask` /
`load_binary_mask` and `assert_invariant` have no production caller in this phase (only
tests). That is defensible for D-11's forward-declaration design, but `next_stage` in
particular is explicitly described in `runner.py`'s docstring as the thing a contributor
must *not* chase — a function that exists only to be not-called invites exactly that
misuse.
**Fix:** No change required; noted so the phase-2 reviewer knows these are intentional
placeholders, not accidental dead code.

---

_Reviewed: 2026-08-15T21:13:12Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
