
## Project

**ComicColor**

A layered colour-flatting application for comic and manga production. An artist
uploads their line art pages, character sheets and palette; the app segments
panels and colour zones deterministically, proposes colours with a generative
model, and returns an editable, layered PSD that drops straight into Photoshop
or Clip Studio. Every stage boundary is inspectable and correctable by the
artist — that is the product, not a feature of it.

For v1 the users are professional colourists, observed rather than served: the
app runs on one machine (Raph's), and testing happens live over video call with
the artist watching their own page go through the pipeline.

**Core Value:** An artist gets flats they can actually use, and every place the machine got it
wrong is one click to fix.

### Constraints

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

## Technology Stack

## Languages

- Python 3.11+ (currently 3.13.14 in development environment) - All source code and CLI tools

## Runtime

- Python 3.11+ (specified in `pyproject.toml`, currently 3.13.14 in `.venv`)
- Platform: Cross-platform (Linux, Windows, macOS via Python portability)
- pip / setuptools
- Lockfile: Not present (dependency pinning via `pyproject.toml` only)

## Frameworks

- None (library-based architecture, not web/application framework)
- argparse (Python standard library) - Command-line interface in `src/comiccolor/cli.py`
- pytest 8.0+ - Configured in `pyproject.toml`, run via `pytest tests/`
- setuptools 68+ - Project build and package management

## Key Dependencies

- numpy >=2.0 - Array processing, image operations (used throughout segmentation and masking)
- opencv-python-headless >=4.10 - Image loading, manipulation, morphological operations (in `segmentation/`, `extract/`, `spike/`)
- scipy >=1.14 - Scientific computing, specifically `scipy.ndimage` for morphological operations (in `src/comiccolor/segmentation/closure.py`)
- pillow >=11.0 - Image format support and I/O fallback
- torch (PyTorch) - Required by `MangaLineExtraction` line extraction (in `src/comiccolor/extract/manga_line.py`, line 74), but NOT listed in project dependencies. Must be installed separately. Vendored model weights: `third_party/MangaLineExtraction/erika.pth`
- skimage (scikit-image) - Visible in virtual environment (`scipy-1.18.0`), imported in `src/comiccolor/segmentation/closure.py` for `skeletonize()`. Likely indirect dependency via scipy or must be added.
- pytest >=8.0 - Unit testing framework

## Vendored Third-Party

- Source: `third_party/LineFiller/` (github.com/hepesu/LineFiller)
- Purpose: Reference implementation of trapped-ball region segmentation (§1.4)
- Integration: Dynamically loaded in `src/comiccolor/segmentation/segmenter.py` via `LineFillerSegmenter` class
- Contains: `linefiller.trappedball_fill` functions for multi-radius flood fill and merge operations
- Source: `third_party/MangaLineExtraction/`
- Purpose: Structural line extraction model (§7 Tier 3 adaptation)
- Model weights: `erika.pth` (PyTorch state dict, ~50MB, vendored)
- Architecture: `res_skip` network (imported from `model_torch.py` in vendor directory)
- Integration: Wrapped in `src/comiccolor/extract/manga_line.py` as `MangaLineExtractor` class
- Note: Trained on manga line art; tolerance for Franco-Belgian hatching is experimental

## Configuration

- No `.env` file or environment variable configuration documented
- Configuration via CLI arguments only (see `src/comiccolor/cli.py`)
- `pyproject.toml` - Standard Python project configuration, defines dependencies, entry point, test paths
- CLI: `comiccolor = "comiccolor.cli:main"` - Command-line entry point in `src/comiccolor/cli.py`
- Subcommands:

## Database

- SQLite (local file-based, no server required)
- Schema defined in `src/comiccolor/model/store.py` (PRAGMA foreign_keys enabled)
- Instantiated via `Store(path)` constructor in `src/comiccolor/model/store.py`
- No connection pooling or multi-thread safety (per docstring: "Not thread-safe; one Store per thread")

## Model & Weights

- Cobra (SIGGRAPH 2025, github.com/zhuang2002/Cobra)

## Platform Requirements

- Python 3.11+
- pip and setuptools
- For torch (MangaLineExtraction): CPU or GPU support (defaulted to CPU in `src/comiccolor/extract/manga_line.py`)
- For GUI/visualization: OpenCV with headless mode (cv2 works without display server)
- Python 3.11+ runtime
- torch optional (only if line extraction is used; can skip for colour-only pipelines)
- No external services or APIs required (entirely self-contained except for future Cobra integration)
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
- Enum classes for domain concepts: `RegionStatus`, `ProtectedKind` in `src/comiccolor/model/entities.py`
- Dataclasses for data structures: `Series`, `Volume`, `Page`, `Panel`, `Entity`, `PaletteEntry`, `Region`, `ProtectedMask` in `src/comiccolor/model/entities.py`
- Protocol classes for interface contracts: `Segmenter` protocol in `src/comiccolor/segmentation/segmenter.py`
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
- Use `SystemExit` with message strings for CLI errors (`src/comiccolor/cli.py` line 22, 24, 67)
- Conditional checks before operations with descriptive error messages

## Logging

- `logging` module used minimally
- Only found in `src/comiccolor/segmentation/segmenter.py` lines 34-40 to suppress vendored library output
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
- Use dataclasses for multiple related parameters: `SegmentationParams` in `src/comiccolor/segmentation/trappedball.py`
- Default to None for optional/advanced parameters, then normalize: `params = params or SegmentationParams()`
- Accept Path objects or strings (`str | Path`), normalize to `Path()` immediately
- Explicit, single return value (no tuple unpacking patterns)
- Numpy arrays used directly for image data
- Dataclass instances returned for domain objects
- Dictionaries used for structured results: `dict[int, tuple[int, tuple[int, int, int, int]]]`

## Module Design

- No `__all__` lists found; all public functions/classes are module-level and not prefixed with `_`
- Imports expected to be explicit: `from .module import SpecificClass`
- `src/comiccolor/model/__init__.py` re-exports public classes (lines 1-41)
- Pattern: import classes from submodules, add to `__all__`, then export

## Class Design

- Used for data containers with structural invariants
- Type hints on every field
- Docstrings explain field meanings and constraints
- `field(default_factory=list)` for mutable defaults
- Used to define interfaces without implementation
- Decorated with `@runtime_checkable`
- Minimal, focused on contract

See `SPEC.md` for what is being built and why.

<!-- tokenade-scaffold -->
## Explore code with the `tokenade` CLI (cheaper than reading whole files)
Use these only when you don't yet know where code lives — if you know the path, open it directly:
`tokenade map` (repo structure) · `skeleton <file…>` (signatures) · `query <symbol…>` (locate a symbol) · `impact <file…>` (dependents) · `semantic "<query>"` (search by meaning). They take MANY targets per call (`tokenade skeleton a.rs b.rs c.rs`) — batch in ONE turn.

## Reading documents & media
tokenade extends your `Read` tool: reading .pdf .docx .xlsx .xls .xlsb .pptx .odt .ods .odp .odg .epub .rtf .fb2 (and their flat-XML, macro-enabled and template variants) returns extracted text instead of failing on the binary; .mp4 .mkv .mov .webm .avi .mp3 .wav .m4a .flac .ogg .opus (and other common containers) returns what the file is plus a transcript when one is available; and .png .jpg .jpeg .gif .webp .bmp .tif .tiff .ico .tga .pnm .pbm .pgm .ppm .qoi .hdr are decoded for you — any image format you cannot display yourself is converted to PNG automatically. Just Read the path as usual.
For a big document, asking beats reading it whole — `tokenade read <file> --prompt "q1, q2"` returns only the passages that answer, and putting several questions in ONE comma-separated call is the CHEAPEST option in tokens spent.

## Fetching or searching several things
Do them in ONE call — `tokenade web <url1> <url2> …` / `tokenade search "<q1>" "<q2>" …` — they run concurrently, so you pay ONE round-trip instead of N and never re-send the context each extra turn would have re-sent.

## Compute over data with `tokenade exec`
`tokenade exec --lang python --script '<code>'` (also sh/node/ruby/awk/jq/perl) runs a capped subprocess with a scrubbed env — your permissions, not a jail — and returns ONLY its stdout. Use it to COMPUTE over data — filter/aggregate a large or structured output, pull facts across SEVERAL files, or apply one mechanical edit across many files (migration, find-replace) — in ONE script, not one command per item. It is NOT a file reader: to read content, use the parallel reads above, not `exec`. Keep scripts SHORT (aim ≤ ~20 lines): exec is for throwaway one-shot computation, not for code you will edit and iterate on — every script char is billed as output, and a long script usually means a simpler command (or a real file you Write once and run) does it cheaper. Long or quote-heavy script? `--script-file <path>` (or `--script -` on stdin) avoids shell quoting entirely.

## Commands
If you do not have hooks (i.e. you are not Claude Code or Gemini CLI), use `tokenade wrap '<cmd>'` to wrap all your commands. If there is an opportunity for compacting noisy output, tokenade will find it — and you will waste fewer tokens. On Windows, if your commands are PowerShell or cmd (not bash), add `--shell powershell` or `--shell cmd` so they run under the right interpreter: `tokenade wrap --shell powershell '<cmd>'`.
An absolute path (`/usr/bin/git`) is intercepted exactly like `git` when hooks are installed; where interception goes through your PATH instead, only the bare name is seen — so prefer the bare name if you are not sure which you have.

## Keep output lean
Keep prose terse and code minimal — every token you write is billed as output.
- **Prose:** answer directly — no preamble, recap, tool-call narration, summary, or emoji. Drop articles, filler (*just/really/basically/simply*) and hedging; fragments fine; short word over long.
- **Output:** don't paste long raw output — quote the shortest decisive line. No decorative tables.
- **Code:** write the least that works; reuse before adding (`query` / `skeleton` / `impact`, stdlib, platform feature — YAGNI).
- **Verbatim:** keep code, identifiers, API/CLI names and error strings exact — never abbreviate or paraphrase. Keep the user's language.
- **Correctness first:** fix root causes not symptoms, don't downgrade the algorithm, don't guess APIs/flags/versions — verify.
- **Full prose where terseness could mislead:** security/data-loss warnings, irreversible-action confirmations, multi-step sequences.
<!-- /tokenade-scaffold -->
