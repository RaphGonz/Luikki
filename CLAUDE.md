
## Project

**Luikki**

A layered flatting application for comic and manga production. An artist
uploads their line art pages; the app cuts them deterministically into panels,
balloons, zones and depth planes, and returns an editable, layered PSD — one
layer per plane, fake flat colours the professional replaces — that drops
straight into Photoshop or Clip Studio. It proposes no colour (ROADMAP G).
Every stage boundary is inspectable and correctable by the artist — that is
the product, not a feature of it.

For v1 the users are professional colourists, observed rather than served: the
app runs on one machine (Raph's), and testing happens live over video call with
the artist watching their own page go through the pipeline.

**Core Value:** An artist gets flats they can actually use, and every place the machine got it
wrong is one click to fix.

### Constraints

- **Deployment**: Single machine, local web app — Testing is supervised over
  video call; nobody else runs it. Later hosting is a separate, deliberately
  deferred concern.

- **Hardware**: Any machine. The models (line extraction, balloons, depth)
  run on onnxruntime, on a GPU when there is one, else on the CPU.
- **Tech stack**: Python 3.11+, numpy/opencv/scipy/pillow, SQLite, pytest —
  Established by the existing codebase; the web layer is the only open choice.

- **Model licences**: Depth Anything V2 *Small* only (Apache-2.0); Base and
  Large are CC-BY-NC-4.0 and must never be fetched. The bubble detector is
  Apache-2.0. Cobra and its OpenRAIL++-M pull are gone (ROADMAP G1).

- **Licence**: Source-available under PolyForm Shield 1.0.0 (`LICENSE`): any use, commercial included, except supplying a product that competes with Luikki — Vendored dependencies
  (LineFiller, MangaLineExtraction) are MIT, which is compatible.

- **Export**: PSD only — `.clip` is an undocumented SQLite container; CSP
  imports PSD with groups intact, so one path serves both applications.

- **Data model**: Regions store `palette_entry_id`, never RGB — The entries are
  eight fake flats (`export/flat_colours.py`). Non-negotiable.

- **Evaluation**: Real ink layers, never extracted lines — Extracted lines are
  closed, gap-free and uniformly weighted. Real ink is none of those, and an
  evaluation set of extracted lines measures nothing.

## Technology Stack

## Languages

- Python 3.11+ (currently 3.13.14 in development environment) - All source code and CLI tools

## Runtime

- Python 3.11+ (specified in `pyproject.toml`, currently 3.13.14 in `.venv`)
- Platform: Cross-platform (Linux, Windows, macOS via Python portability)
- pip / setuptools
- Lockfile: Not present (dependency pinning via `pyproject.toml` only)

## Frameworks

- FastAPI + uvicorn (`[web]` extra) - The local app in `src/luikki/web/`. One route per button, plus one per correction and one per preview PNG. Handlers are plain `def`, not `async def`: segmentation and depth are seconds of CPU or GPU work, and FastAPI runs sync handlers in a threadpool instead of stalling the event loop.
- pydantic - Request bodies for the corrections (`Shape`, `Stroke`, `Merge`, `Cut`, `Planes`, `Export` in `web/app.py`)
- Frontend: no framework and no build step - `web/static/` is one HTML, one CSS and one JS file, plus `locales/<lang>.json` (every word of the interface) and `favicon.svg`, served as they are. Hand-rolled 2D canvas, one screen↔image transform (`view` in `app.js`), zero runtime dependencies. Layout, colour tokens and the rules for lines on the artwork come from `UI.md`.
- argparse (Python standard library) - Command-line interface in `src/luikki/cli.py`
- pytest 8.0+ - Configured in `pyproject.toml`, run via `pytest tests/`
- setuptools 68+ - Project build and package management

## Key Dependencies

- numpy >=2.0 - Array processing, image operations (used throughout segmentation and masking)
- opencv-python-headless >=4.10 - Image loading, manipulation, morphological operations (in `segmentation/`, `extract/`, `spike/`)
- scipy >=1.14 - Scientific computing, specifically `scipy.ndimage` for morphological operations (in `src/luikki/segmentation/closure.py`)
- pillow >=11.0 - Image format support and I/O fallback
- scikit-image >=0.26 - `skeletonize()` in `segmentation/closure.py`
- psd-tools >=1.18 - The layered export in `export/psd.py`
- onnxruntime >=1.20 - The RT-DETR balloon detector. Deliberately not `ultralytics`, which is AGPL-3.0 whatever licence its weights carry.
- fastapi / uvicorn / python-multipart (`[web]`) - The local app and its uploads
- httpx (`[dev]`) - Required by `fastapi.testclient`, which `tests/test_web.py` presses every button through
- torch (PyTorch) - NOT a runtime dependency. The client runs MangaLineExtraction from `models/manga_line.onnx` on onnxruntime; torch (plus onnx, onnxscript: the `[models]` extra) is only needed to re-export that file from `third_party/MangaLineExtraction/erika.pth` (`models.export_manga_line`); `luikki models` downloads the published export from the `models-1` release, sha256-pinned.
- pytest >=8.0 - Unit testing framework

## Vendored Third-Party

- Source: `third_party/LineFiller/` (github.com/hepesu/LineFiller)
- Purpose: Reference implementation of trapped-ball region segmentation (§1.4)
- Integration: Dynamically loaded in `src/luikki/segmentation/segmenter.py` via `LineFillerSegmenter` class
- Contains: `linefiller.trappedball_fill` functions for multi-radius flood fill and merge operations
- Source: `third_party/MangaLineExtraction/`
- Purpose: Structural line extraction model (§7 Tier 3 adaptation)
- Model weights: `erika.pth` (PyTorch state dict, ~50MB, vendored)
- Architecture: `res_skip` network (imported from `model_torch.py` in vendor directory)
- Integration: `src/luikki/extract/manga_line.py` `MangaLineExtractor` runs the ONNX export of these weights on onnxruntime; the vendored torch code is only read by the export and the parity test
- Note: Trained on manga line art; tolerance for Franco-Belgian hatching is experimental

## Configuration

- No `.env` file. Environment variables, all read at call time: `LUIKKI_SUPABASE_URL` and `LUIKKI_SUPABASE_KEY` to point the sign-in (`account.py`) at another Supabase project; `LUIKKI_PAYMENT_URL` and `LUIKKI_PORTAL_URL` to open other Stripe pages than `PAYMENT_URL` (a Payment Link) and `PORTAL_URL` (the Customer Portal's login link) in `billing.py`, test mode's for instance; `LUIKKI_UPDATE_URL` to read another `latest.json` than the latest GitHub release's (`web/update.py`); `LUIKKI_MODELS` for another model folder.
- Otherwise configuration is CLI arguments only (see `src/luikki/cli.py`)
- `pyproject.toml` - Standard Python project configuration, defines dependencies, entry point, test paths
- CLI: `luikki = "luikki.cli:main"` - Command-line entry point in `src/luikki/cli.py`
- Subcommands:
  - `serve` - the local app, for a browser. `--port`, `--workdir`
  - `app` - the same app in its own window (`desktop.py`: uvicorn on a free port of 127.0.0.1 in a thread, pywebview on it; the `[desktop]` extra). `--debug` opens the inspector
  - `flatten` - one page headlessly, then the PSD. `--layers` (`plane` | `colour`), `--no-planes`, `--extract-lines`, `--leak-gap` (§1.3's gap allowance, 0-1), `--steps` (one image per stage boundary)
  - `p3` / `ab` - the segmentation experiments; reports land in `reports/`
  - `models` - fill `models/` once: download the bubble detector (sha256-pinned), export `manga_line.onnx`

## State on disk

- `<workdir>` without `--workdir`: `%LOCALAPPDATA%\Luikki` / `~/Library/Application Support/Luikki` (`default_workdir` in `web/project.py`). A project left in the old `%TEMP%\luikki` is copied across once.
- The signed-in session is not on disk: its refresh token, email and the device uuid sit in the system password store under the service `Luikki` (`keyring`). Tests swap in a memory vault (`tests/conftest.py`).
- `<workdir>/project.json` and `<workdir>/pages/NNNN/` - every page, saved on each edit (`web/project.py`): `page.json` (zones' planes, line extraction on or off), the source image, one `panelN.npy` zone map and one `depthN.npy` set of depth groups per panel, the extractor's lines. Files, not SQLite. One page is open at a time; the app reopens the last one.

## Database

- SQLite (local file-based, no server required)
- Schema defined in `src/luikki/model/store.py` (PRAGMA foreign_keys enabled)
- Instantiated via `Store(path)` constructor in `src/luikki/model/store.py`
- No connection pooling or multi-thread safety (per docstring: "Not thread-safe; one Store per thread")

## Model & Weights

- Depth Anything V2 Small (`models/depth_small.onnx`, Apache-2.0, sha256-pinned in `models.py`) - relative depth per panel for the planes (`segmentation/planes.py`).

## Platform Requirements

- Python 3.11+
- pip and setuptools
- MangaLineExtraction: CPU or GPU through onnxruntime providers (`best_providers` in `extract/manga_line.py`: CUDA with `onnxruntime-gpu`, DirectML with `onnxruntime-directml`, else CPU). It degrades to CPU rather than refusing.
- Model files live in `models/` (`luikki/models.py`; `LUIKKI_MODELS` overrides, a frozen app reads its bundle). Nothing downloads at launch: `luikki models` fetches the bubble detector, the line extractor and the depth model, once per checkout.
- The installed app: `packaging/luikki.spec` (PyInstaller onedir, built from `.venv-build`, which never has torch) → `dist/Luikki`. `packaging/smoke.py <page>` checks a build end to end; the windowed exe logs to `%LOCALAPPDATA%\Luikki\Logs\luikki.log`. `packaging/luikki.iss` (Inno Setup 6, per-user, no admin) → `dist/installer/Luikki-<version>-setup.exe`; `packaging/TESTEURS.md` is what testers read. `.github/workflows/release.yml`: a tag `v*` builds Windows and the Mac (`Luikki.app`, DMG), smoke-tests each bundle on `packaging/synthetic_page.py`, and publishes the release with `latest.json`, which installed apps read to offer the update. The version lives in `luikki/__init__.py` only; the tag must match it.
- For GUI/visualization: OpenCV with headless mode (cv2 works without display server)
- Python 3.11+ runtime
- No torch at runtime: the whole local pipeline runs on numpy, OpenCV and onnxruntime
- No external service for the pipeline: only the account and the licence (Supabase; Stripe's Payment Link, whose webhook is a Supabase Edge Function in `supabase/functions/stripe-webhook`) are online. No Modal, no server of our own
- Storage: Local filesystem for SQLite database and image outputs

## Deployment Path

- On-premise: Fully supported (self-contained, no licence restrictions for code execution)
- Cloud/SaaS hosting: Future tier compatible

## Conventions

## Naming Patterns

- Lowercase with underscores: `cli.py`, `manga_line.py`, `trapped_ball.py`
- Module/package names reflect functionality: `segmentation/`, `extract/`, `model/`
- Test files use `test_` prefix: `test_masks.py`, `test_trappedball.py`
- Snake_case for all function and method names: `load_line_art()`, `measure_passage_width()`, `region_stats()`
- Private functions (module-internal) prefixed with single underscore: `_ball()`, `_box_page()`, `_install_quiet_logger()`
- Descriptive names that indicate purpose: `check_coverage()`, `relabel_sequential()`, `expand_under_lines()`
- Snake_case for local variables and parameters: `line_mask`, `fillable`, `label_map`, `grey`
- Clear, specific names over abbreviations: `height, width` not `h, w`
- Type-indicating for optional values: `radii: tuple[int, ...] | None`
- Enum classes for domain concepts: `RegionStatus`, `ProtectedKind` in `src/luikki/model/entities.py`
- Dataclasses for data structures: `Series`, `Volume`, `Page`, `Panel`, `Entity`, `PaletteEntry`, `Region`, `ProtectedMask` in `src/luikki/model/entities.py`
- Protocol classes for interface contracts: `Segmenter` protocol in `src/luikki/segmentation/segmenter.py`
- UPPER_CASE for module-level constants: `DEFAULT_RADII`, `UNASSIGNED`, `IMAGE_SUFFIXES`, `_STRIDE`

## Code Style

- Black-style implicit (no explicit config found)
- Line length appears to follow conventional limits (~88 chars implied)
- Consistent indentation (4 spaces)
- No explicit linting config files detected (`.eslintrc`, `.flake8`, etc.)
- Code appears to follow PEP 8 conventions through discipline

## Import Organization

- Relative imports used throughout: `from .masks import UNASSIGNED`, `from ..model.entities import Entity`
- No absolute path aliases (no `@` aliases in config)

## Type Hints

- Complete type annotations on all function signatures
- Use of modern Python 3.10+ union syntax (`X | None` instead of `Optional[X]`)
- Type hints on dataclass fields

## Error Handling

- Raise specific exceptions: `FileNotFoundError`, `ValueError`, `SystemExit`
- Use `SystemExit` with message strings for CLI errors (`src/luikki/cli.py` line 22, 24, 67)
- Conditional checks before operations with descriptive error messages

## Logging

- `logging` module used minimally
- Only found in `src/luikki/segmentation/segmenter.py` lines 34-40 to suppress vendored library output
- Used for integration concerns (controlling third-party library verbosity)
- No application-level logging observed (design expects explicit returns/exceptions)

## Docstrings

- Comprehensive explanations of design, invariants, and references to specification
- Use § symbol to reference design sections (e.g., "§3 data model", "§1.4 Trapped-ball region segmentation")
- Explain WHY, not WHAT
- Concise one-liner describing behavior
- Additional paragraphs for parameters and return values
- Use backticks for code references: `` `line_mask` ``, `` `palette_entry_id` ``
- Explain design decisions and non-obvious logic
- Usually appear above the block they explain
- Often reference specification sections or external constraints

## Function Design

- Functions are compact, typically under 50 lines
- Segmented into clear steps with inline comments
- Longer functions appear only in specialized modules (e.g., `load_line_art()` at 56 lines for image format handling)
- Use dataclasses for multiple related parameters: `SegmentationParams` in `src/luikki/segmentation/trappedball.py`
- Default to None for optional/advanced parameters, then normalize: `params = params or SegmentationParams()`
- Accept Path objects or strings (`str | Path`), normalize to `Path()` immediately
- Explicit, single return value (no tuple unpacking patterns)
- Numpy arrays used directly for image data
- Dataclass instances returned for domain objects
- Dictionaries used for structured results: `dict[int, tuple[int, tuple[int, int, int, int]]]`

## Module Design

- No `__all__` lists found; all public functions/classes are module-level and not prefixed with `_`
- Imports expected to be explicit: `from .module import SpecificClass`
- `src/luikki/model/__init__.py` re-exports public classes (lines 1-41)
- Pattern: import classes from submodules, add to `__all__`, then export

## Class Design

- Used for data containers with structural invariants
- Type hints on every field
- Docstrings explain field meanings and constraints
- `field(default_factory=list)` for mutable defaults
- Used to define interfaces without implementation
- Decorated with `@runtime_checkable`
- Minimal, focused on contract

## The shape of the app
Six buttons, in one order, and nothing runs by itself: upload → panels →
bubbles → zones → planes (optional) → export. Re-running a step deletes what
depended on it, and a step that would delete the artist's own corrections asks
first.

Every stage is a proposal the artist can refuse, and each correction belongs
to its own stage:

- panels and balloons (steps 2 and 3) - drag a corner, click an edge to add
  one, click empty page to draw a new shape, right-click to delete. The
  browser sends the whole polygon, never an edit.
- zones (step 4) - press over a zone to select it, sweep to take several,
  right-click to merge; or cut one with a stroke across it. There is no
  unmerge, only Ctrl+Z on the last few edits. Merge and cut stay open at
  step 5. Under « Advanced »: how open a border may be before the leak audit
  (§1.3, `segmentation/leaks.py`) reads it as a passage rather than a hole in
  a line (book-scoped), and line extraction, off by default and per page —
  MangaLineExtraction erases small dense detail it takes for hatching.
- planes (step 5, may be skipped) - depth is read per panel and votes: each
  zone takes the plane most of its pixels are on, so boundaries stay the
  ink's. A zone cut or merged later votes again on the depth kept for its
  panel. The same gestures as step 4 pick zones; the inspector or the right
  click puts them on 1st plane, 2nd plane, background, or « characters » —
  which only the artist decides. Ctrl+Z takes a plane change back.
- export (step 6) - one layer per plane (Background, Middle ground,
  Foreground, Characters, Balloons on top), or a group per plane with a layer
  per colour. Inside a layer, eight fake flats, and two touching zones are
  never alike, so the magic wand takes one zone.

The interface is `UI.md`: a step rail on the left drives the canvas, and the
inspector on the right shows what the canvas selected. Raph's choices sit on
top of it and are not bugs: the name and logo in the signature orange
(`--attention`), a dark violet surround (OKLCh L 0.28), zoom and pan kept, and
layer visibility that follows the open step. Every colour is a token in the
`:root` block of `app.css`.

No word the artist reads lives in `index.html` or `app.js`. Every string is a
literal key in `static/locales/en.json`, and `tests/test_locales.py` fails on
a missing, unused or assembled key. A language is a file; `?lang=en-XA` is a
pseudo-locale that shows any text left in the code.

The long steps report real progress through `GET /api/progress`
(`web/progress.py`), read without the session lock the step holds. The server
sends codes (`phase`, `index`, `count`) and the browser supplies the words.
Check the UI with `luikki serve`. The account sits in the header; it only
holds the licence (one, 10 €/an).

`ARCHITECTURE.md` is the fast way into the code: where things are and how the
data moves. See `SPEC.md` for what is being built and why.


