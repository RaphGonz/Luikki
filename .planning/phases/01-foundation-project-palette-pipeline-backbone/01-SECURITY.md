---
phase: 01
slug: foundation-project-palette-pipeline-backbone
status: verified
threats_open: 0
asvs_level: 1
created: 2026-08-16
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
>
> Deployment reality: single machine, local web app, one artist, supervised session (CLAUDE.md / PROJECT.md). No authentication by design — ASVS V2 (authentication) and V4 (access control) are explicitly out of scope per 01-RESEARCH.md § Security Domain. IDOR-shaped findings against this model are recorded as accepted risk, not gaps.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|----------------|
| PyPI / npm registry → developer machine | Newly declared packages execute install-time and import-time code | Package bytes, install scripts |
| `caller` → `Store` SQL | Every value reaching the DB from a router, CLI or test crosses into SQL construction | SQL parameter values |
| `Store` → project folder on disk | `Store.__init__` creates parent directories and a DB file at a caller-supplied path | Filesystem path |
| browser → FastAPI `/api/*` | Every JSON body, query parameter, multipart part crosses here untrusted | JSON, multipart, query params |
| multipart bytes → filesystem | Uploaded page/swatch/sheet bytes become files inside the project folder | Image bytes, filenames |
| request → `project.db` selection | Which DB a request writes to is resolved from process state, not the request | Process-global path |
| browser path/query params → filesystem | `sheet_id`, page ids select which file is read/moved/deleted | Path segments, row ids |
| router → `run_stage` | A stage name from an HTTP request reaches the pipeline registry lookup | Enum-constrained stage name |
| server response → DOM | Project names, paths, labels, character names, `ApiError.detail` rendered into the page | Text content |
| `location.hash` → view dispatch | Artist-editable hash selects which view mounts and with which ids | Route string |
| host OS dialog → server | `tkinter.filedialog` returns a path chosen on the host | Filesystem path |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-SC | Tampering | pip/npm installs (01-01, 01-02, 01-05, 01-11) | mitigate | All 8 packages (fastapi, uvicorn, python-multipart, httpx, scikit-image, vite, typescript, vitest) `Approved` in 01-RESEARCH.md § Package Legitimacy Audit, no `[SLOP]`/`[SUS]`/`[ASSUMED]`. Floors pinned at audited versions: `pyproject.toml:11,15-16`; `frontend/package.json` `devDependencies` — exactly 3 packages, no `dependencies` key, versions match audit. 01-11 added zero new npm packages (confirmed: package.json unchanged from 01-02 baseline). | closed |
| T-01-SQLI | Tampering | `model/store.py` (01-03) | mitigate | `grep -nE "execute\(\s*f[\"']\|\.format\(" src/comiccolor/model/store.py` → 0 matches. All statements parameterized. | closed |
| T-01-STATE | Tampering | schema (01-03) | mitigate | `store.py:40` `CHECK (id = 1)`; `UNIQUE (volume_id, idx)` (`:61`), `UNIQUE (project_id, name)` (`:49,81`); no RGB column on `region` (`store.py:95-106`); `region.palette_entry_id ... ON DELETE SET NULL` (`store.py:99`). | closed |
| T-01-DUR | Denial of Service | WAL/commit discipline (01-03, 01-07) | mitigate | Synchronous `self.conn.commit()` after every mutation (21 call sites in `store.py`); `PRAGMA busy_timeout=5000` (`store.py:171`); `checkpoint()` runs `PRAGMA wal_checkpoint(TRUNCATE)` (`store.py:196`), called from `POST /api/projects/close` (`routers/project.py:193`) and on project open/create (`:142`). | closed |
| T-01-STAGE (pipeline) | Elevation of Privilege | `pipeline/runner.py:run_stage` (01-04) | mitigate | Dispatch is registry-lookup only; unknown/unimplemented stage raises `KeyError`/`StageNotImplementedError` (`runner.py:56`); no `getattr`/dynamic import/string-to-callable resolution found (grep confirmed). | closed |
| T-01-GATE | Tampering | stage advancement (01-04) | mitigate | `run_stage` never walks the chain or advances a page on its own (`runner.py:43-56`, no chain-walk logic present). | closed |
| T-01-INV | Tampering | `masks.py:assert_invariant` (01-04) | mitigate | Raises `LabelMapInvariantError` on violation (`masks.py:161,188,193`) rather than returning an ignorable report. | closed |
| T-01-IMG | Denial of Service | image decode boundary (01-05, 01-06, 01-08, 01-09, 01-10) | mitigate | `uploads.py:decode_image` runs `Image.open().verify()` in `try/except` (`:99-103`), checks format/dimensions on the *probe* before `load()` (`:105,122-129`, WR-04 fix confirmed — order matters, dimension check precedes full raster). `EmptyImageError` (`colour/extract.py:71,109,114,122`) is a `ValueError` subclass. All three upload entry points (`page.py:130`, `palette.py:189`, `reference.py:203`) route through `uploads.read_capped`/`decode_image`. | closed |
| T-01-MEM | Denial of Service | `colour/extract.py` kept-pixel array (01-05) | mitigate | `K_MAX = 24` fixed constant (`extract.py:39`), used in `quantize(colors=K_MAX, ...)` (`:145`) — no input-controlled loop bound; array size bounded by upload-validator dimension cap upstream. | closed |
| T-01-PATH | Tampering | upload filename → disk path (01-06, 01-08, 01-09, 01-10) | mitigate | `save_upload` names files `f"{uuid4().hex}{ALLOWED_FORMATS[image.format]}"` (`uploads.py:156-157`); client filename only reaches `display_name()` (`uploads.py:168`, called at `page.py:126`); no `open(` on client-controlled paths in `uploads.py`/`page.py`/`reference.py`/`palette.py` (grep confirmed). | closed |
| T-01-DB | Tampering | `web/deps.py:get_store` (01-06) | mitigate | Path resolved only from `app.state.current_project_path` (`deps.py:65`); only `set_current_project`/`clear_current_project` write it (`:89-96`, docstring-asserted sole writers); 409 with no project open (`:67,85`). | closed |
| T-01-NET | Information Disclosure | `comiccolor serve` bind (01-06) | mitigate | `cli.py:61` `--host` default `"127.0.0.1"`; no `0.0.0.0` literal anywhere in `cli.py`/`web/app.py` (grep confirmed). | closed |
| T-01-INPUT | Tampering | JSON request bodies (01-06, 01-10, 01-13) | mitigate | `schemas.py:32` `RGBChannel = Field(ge=0, le=255)`; `:34` `NonEmptyStr = Field(min_length=1, max_length=200)`; `character_name`/`part` both `NonEmptyStr` (`schemas.py:217,221`); FastAPI 422s before handler runs. Client-side mirror: `acceptPayload` (`proposalCard.ts:123-144`) validates non-empty name/part and emits only `{character_name, items:{index,part}}` — never RGB. | closed |
| T-01-OPEN | Information Disclosure | `POST /api/projects/open` (01-07) | mitigate | `_resolve_project_path` (`project.py:72-86`): `Path.resolve()` resolves symlinks/`..`, requires `appconfig.is_project_folder` (existing dir + `project.db`), never creates/mkdirs, 400 on failure. | closed |
| T-01-CREATE | Tampering | `POST /api/projects` (01-07) | mitigate | `create_project_folder` composes `(parent/name).resolve()` and asserts `project_dir.parent == parent` (`appconfig.py:78-80`, CR-02 fix); existing `project.db` → `FileExistsError`→409 (`:85-86`); non-empty foreign dir also rejected (`:87`, WR-19 fix). `schemas.py:44-49` `ProjectName` pattern rejects path separators/traversal chars at the boundary. | closed |
| T-01-BROWSE | Denial of Service | `POST /api/projects/browse` (01-07) | mitigate | `import tkinter` inside the handler (`project.py:240`), wrapped in broad `except Exception` → 503 (`:248-250`). | closed |
| T-01-SERVE | Information Disclosure | `GET /api/pages/{id}/image` (01-08) | mitigate | `resolved = (project_root / page.source_path).resolve()`; `is_relative_to(project_root.resolve())` containment assert (`page.py:197-198`); `is_file()` check before `FileResponse` (`:204`, WR-03 fix). Client supplies only an integer id. | closed |
| T-01-SHEETID | Tampering | `sheet_id` path parameter (01-10) | mitigate | `SHEET_ID_RE = r"^[0-9a-f]{32}$"` (`reference.py:59`), `_validate_sheet_id` runs before any path construction (`:78-89`), 404 on mismatch; `_locate` additionally resolves and asserts containment (`:92-108`). | closed |
| T-01-EPHEM | Tampering | proposal indices (01-10, 01-13) | mitigate | Proposals re-derived server-side from the stored pending file each accept (`reference.py:296-298`); out-of-range/duplicate index → 400 via `_validate_items` (`:143-156`); client (`acceptPayload`) sends only `{index, part}`, never RGB. | closed |
| T-01-RGB | Tampering | `PATCH /api/palette/{entry_id}` (01-09) | mitigate | RGB Pydantic-constrained `0..255` (`schemas.py:32`), label length-bounded; no raw SQL in `palette.py` (grep confirmed); write goes only to `palette_entry` via `store.update_palette_rgb`. | closed |
| T-01-XSS | Tampering | rendering artist/server text into DOM (01-11, 01-12, 01-13) | mitigate | `innerHTML` absent from the entire `frontend/src` tree — only appears once, in a comment explaining the rule (`sidebar.ts:14`). `textContent`/`createTextNode` used across `views/`, `components/`, `shell/` (confirmed present in all 11 relevant files). | closed |
| T-01-HASH | Tampering | `parseRoute` (01-11) | mitigate | `router.ts:25-46` — total function; unknown/malformed/non-numeric hash falls back to `{kind:"picker"}`; explicit `Number.isInteger(id) && id >= 0` guard. | closed |
| T-01-ORIGIN | Information Disclosure | `apiUrl` (01-11) | mitigate | `client.ts:36-40` builds only relative `/api/...` URLs; no `http(s)://` literal in `frontend/src/api/*.ts` (grep confirmed). | closed |
| T-01-NOSAVE | Denial of Service | data loss on refresh (01-11) | mitigate | No Save button/write-buffer found (grep confirmed); every mutation commits on the triggering action; on failure the DOM is untouched, e.g. `renameEntry`'s catch explicitly does not revert the input (`palette.ts:147-158`). | closed |
| T-01-STORAGE | Information Disclosure | browser storage (01-11) | mitigate | Zero `localStorage`/`sessionStorage` references anywhere in `frontend/src` (grep confirmed). | closed |
| T-01-SRC | Tampering | thumbnail `<img src>` (01-12) | mitigate | `src`/`img.src` set from server-built `page.image_url` in `pageGrid.ts:69`, `pageDetail.ts:82`, `palette.ts:389` — never a client-composed path segment. | closed |
| T-01-UPLOAD | Denial of Service | drag-and-drop large/numerous files (01-12) | mitigate | `input.accept = "image/*"` set in `uploadDrop.ts:68` and `palette.ts:90,311`; server-side `MAX_UPLOAD_BYTES`/format/dimension checks are the real control (verified under T-01-IMG). | closed |
| T-01-PARTIAL | Denial of Service | mixed-batch upload data loss (01-12) | mitigate | `partitionUploadResult` (`uploadDrop.ts:31-41`) keeps `result.accepted` and `failures` separate; accepted pages are never dropped by a co-occurring failure. | closed |
| T-01-STAGEUI | Information Disclosure | stage strip rendering (01-12) | mitigate | `segmentStates` (`stageStrip.ts:39-51`) derives state only from `stage.name`/`currentStage` — never reads `has_runner`; the only reference to `has_runner` in the whole frontend is its type declaration (`api/types.ts:86`), never consumed. | closed |
| T-01-FLOOD | Denial of Service | colour picker drag (01-13) | mitigate | `swatchCard.ts:67-71` — `input` event only updates local `colour.style.background`; `change`/`blur` events call `commitRecolour`, guarded by `lastCommittedHex` so an unchanged value is a no-op — one write per commit, not per frame. | closed |
| T-01-DESTRUCT | Tampering | delete vs. reject controls (01-13) | mitigate | Delete → `openDeleteConfirmation` with named heading (`palette.ts:247-278`, `Delete "{label}"?`, explicit cancel/confirm). Proposal reject (`proposalCard.ts` checkbox `change`) has no dialog — asymmetry matches the design intent (real/persisted data vs. never-persisted proposal). | closed |
| T-01-01 | Tampering | test scaffolding (01-01) | accept | Runs only in developer's own pytest run; no network/filesystem-write-outside-`tmp_path`/subprocess behaviour. | closed (accepted) |
| T-01-02 | Information Disclosure | `tokens.css`, `transform.ts` (01-02) | accept | Static design tokens and pure arithmetic — nothing to disclose. | closed (accepted) |
| T-01-03 | Tampering | `vite.config.ts` dev proxy (01-02) | accept | Loopback-only, dev-only; production serves SPA from the same FastAPI process. | closed (accepted) |
| T-01-CONST | Tampering | `MERGE_DELTA_E`, `INK_MAX`, `PAPER_MIN` (01-05) | accept | Unvalidated hypotheses (RESEARCH.md Assumptions Log A1); wrong value degrades quality, not safety; manual add/delete is the recovery path (D-15). | closed (accepted) |
| T-01-TABS | Tampering | process-global current project (01-06) | accept | Two tabs on two projects could cross-write. Accepted for v1: single machine, one artist, supervised session (PROJECT.md, RESEARCH.md A2). | closed (accepted) |
| T-01-LOCALPATH | Information Disclosure | typed-path fallback (01-07) | accept | Caller already owns the filesystem on a single-machine app; realistic failure is a typo, turned into a 400 by `_resolve_project_path`. | closed (accepted) |
| T-01-IDOR (volume/page) | Elevation of Privilege | volume/page ids (01-08) | accept | One artist, one open project; ASVS V4 out of scope. Wrong id → 404 neutral copy (correctness, not access control). | closed (accepted) |
| T-01-IDOR (palette entry) | Elevation of Privilege | entry ids (01-09) | accept | Same rationale as above, scoped to `palette_entry`. | closed (accepted) |
| T-01-DISK (pages) | Denial of Service | orphaned page bytes on delete (01-08) | accept | Orphaned bytes recoverable; no v1 reclamation requirement; bounded per-upload by `MAX_UPLOAD_BYTES`. | closed (accepted) |
| T-01-DISK (pending sheets) | Denial of Service | abandoned pending sheets (01-10) | accept | Filesystem-only pending state by design (Open Question 2); per-file bounded by `MAX_UPLOAD_BYTES`; `DELETE /sheets/{id}` gives an explicit discard. | closed (accepted) |
| T-01-GOBACK | Tampering | absent Go-Back flow (01-12) | accept | No destructive stage-reset path exists in Phase 1 — nothing to guard yet; contract recorded for Phase 2. | closed (accepted) |
| T-01-PATH-DB | Tampering | `Store.__init__` trusts caller path (01-03) | transfer | Transfer target: web-boundary validation. Verified present as `T-01-OPEN` (`project.py:72-86`, actually shipped in plan 01-07, not 01-06 as the plan's own cross-reference states — documentation slip, not a code gap; the control itself is closed). | closed |
| T-01-SQLI (01-04 caller) | Tampering | `runner.py` calling `Store` | transfer | No SQL constructed in `runner.py` (grep confirmed); parameterization owned by `store.py`, verified above. | closed |
| T-01-SQLI (01-07 caller) | Tampering | `routers/project.py` calling `Store` | transfer | No SQL literals in `routers/project.py` (grep confirmed). | closed |
| T-01-SQLI (01-08 caller) | Tampering | `routers/page.py`/`volume.py` calling `Store` | transfer | No SQL literals in `routers/page.py` (grep confirmed). | closed |
| T-01-SQLI (01-09 caller) | Tampering | `routers/palette.py` calling `Store` | transfer | No SQL literals in `routers/palette.py` (grep confirmed). | closed |
| T-01-SQLI (01-10 caller) | Tampering | `routers/reference.py` calling `Store` | transfer | No SQL literals in `routers/reference.py` (grep confirmed). | closed |
| T-01-IMG (01-13 client) | Denial of Service | swatch/sheet drop zones | transfer | Decoding/size/format/dimension bounds enforced server-side (`uploads.py`, verified under mitigate `T-01-IMG` above); client only sets `accept="image/*"`. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party / another boundary)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-01-01 | Test scaffolding crosses no trust boundary. | Plan 01-01 author | 2026-08-15 |
| AR-02 | T-01-02 | Static tokens / pure arithmetic, nothing to disclose. | Plan 01-02 author | 2026-08-15 |
| AR-03 | T-01-03 | Loopback-only, dev-only Vite proxy; prod serves from one process. | Plan 01-02 author | 2026-08-15 |
| AR-04 | T-01-CONST | Unvalidated colour-merge thresholds degrade quality, not safety; manual correction path exists (D-15). | Plan 01-05 author | 2026-08-15 |
| AR-05 | T-01-TABS | Process-global current-project path; single-machine, single-artist, supervised session per PROJECT.md. | Plan 01-06 author | 2026-08-15 |
| AR-06 | T-01-LOCALPATH | Typed-path fallback on a single-machine app the artist already controls; `_resolve_project_path` still turns a typo into a 400. | Plan 01-07 author | 2026-08-15 |
| AR-07 | T-01-IDOR (volume/page) | One artist, one open project; ASVS V4 access control explicitly out of scope. | Plan 01-08 author | 2026-08-15 |
| AR-08 | T-01-IDOR (palette entry) | Same rationale, `palette_entry` ids. | Plan 01-09 author | 2026-08-15 |
| AR-09 | T-01-DISK (pages) | Orphaned page bytes on delete; recoverable, no v1 reclamation requirement, bounded per-upload. | Plan 01-08 author | 2026-08-15 |
| AR-10 | T-01-DISK (pending sheets) | Abandoned `references/pending/` files; filesystem-only design (Open Question 2), bounded, explicit discard exists. | Plan 01-10 author | 2026-08-15 |
| AR-11 | T-01-GOBACK | No destructive stage-reset flow ships in Phase 1; nothing to guard yet. | Plan 01-12 author | 2026-08-15 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-08-16 | 49 | 49 | 0 | gsd-security-auditor |

**Notes for future audit runs:**
- No `## Threat Flags` sections exist in any of the 13 SUMMARY.md files for this phase — no new attack surface was self-reported by any executor. No unregistered flags to log.
- 01-REVIEW.md's CR-01..CR-04 and WR-04/WR-09/WR-15/WR-16 fixes were independently re-verified in the implementation (not taken on the reviewer's or verifier's word): `check_same_thread=False` (`store.py:163`), `ProjectName` pattern + containment assert (`schemas.py:44-49`, `appconfig.py:78-80`), `get_owned_volume` pre-check before write (`page.py:120`), copy-not-move non-consuming sheet accept (`reference.py:296-321`), streamed capped reads at all three upload sites (`uploads.py:51-76`, wired in `page.py`/`palette.py`/`reference.py`), and an Origin-check middleware (`app.py:41-86`) closing the CSRF-shaped gap on multipart endpoints — this last one is hardening beyond the original STRIDE register (no declared T-01 ID covers inbound origin checking) but is recorded here since it materially reduces the attack surface WR-09 identified.
- WR-10 through WR-14 (frontend robustness: unhandled promise rejections, silent non-`ApiError` catches, dead sidebar `is-current` styling, stale `swatchCard` rename snapshot, no DOM-level test coverage) remain intentionally deferred per 01-REVIEW.md/01-VERIFICATION.md. None has a declared threat-model mitigation and none produces a genuine security consequence beyond UX degradation — not re-raised as blockers here, consistent with phase instructions.
- One documentation-only inaccuracy found during verification: 01-03-PLAN.md's `T-01-PATH-DB` mitigation text cites "plan 01-06" as where `T-01-PATH-OPEN` is mitigated; the actual control (`T-01-OPEN`) ships in plan 01-07 (`routers/project.py:72-86`). The control itself is present and verified closed — this is a cross-reference slip in the plan text, not a code gap.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-08-16
