# Technology Stack

**Analysis Date:** 2026-08-02

## Languages

**Primary:**
- Python 3.11+ (currently 3.13.14 in development environment) - All source code and CLI tools

## Runtime

**Environment:**
- Python 3.11+ (specified in `pyproject.toml`, currently 3.13.14 in `.venv`)
- Platform: Cross-platform (Linux, Windows, macOS via Python portability)

**Package Manager:**
- pip / setuptools
- Lockfile: Not present (dependency pinning via `pyproject.toml` only)

## Frameworks

**Core:**
- None (library-based architecture, not web/application framework)

**CLI:**
- argparse (Python standard library) - Command-line interface in `src/comiccolor/cli.py`

**Testing:**
- pytest 8.0+ - Configured in `pyproject.toml`, run via `pytest tests/`

**Build/Dev:**
- setuptools 68+ - Project build and package management

## Key Dependencies

**Critical (declared in `pyproject.toml`):**
- numpy >=2.0 - Array processing, image operations (used throughout segmentation and masking)
- opencv-python-headless >=4.10 - Image loading, manipulation, morphological operations (in `segmentation/`, `extract/`, `spike/`)
- scipy >=1.14 - Scientific computing, specifically `scipy.ndimage` for morphological operations (in `src/comiccolor/segmentation/closure.py`)
- pillow >=11.0 - Image format support and I/O fallback

**Conditional/Optional:**
- torch (PyTorch) - Required by `MangaLineExtraction` line extraction (in `src/comiccolor/extract/manga_line.py`, line 74), but NOT listed in project dependencies. Must be installed separately. Vendored model weights: `third_party/MangaLineExtraction/erika.pth`
- skimage (scikit-image) - Visible in virtual environment (`scipy-1.18.0`), imported in `src/comiccolor/segmentation/closure.py` for `skeletonize()`. Likely indirect dependency via scipy or must be added.

**Development:**
- pytest >=8.0 - Unit testing framework

## Vendored Third-Party

**LineFiller (MIT licence):**
- Source: `third_party/LineFiller/` (github.com/hepesu/LineFiller)
- Purpose: Reference implementation of trapped-ball region segmentation (§1.4)
- Integration: Dynamically loaded in `src/comiccolor/segmentation/segmenter.py` via `LineFillerSegmenter` class
- Contains: `linefiller.trappedball_fill` functions for multi-radius flood fill and merge operations

**MangaLineExtraction (MIT licence):**
- Source: `third_party/MangaLineExtraction/`
- Purpose: Structural line extraction model (§7 Tier 3 adaptation)
- Model weights: `erika.pth` (PyTorch state dict, ~50MB, vendored)
- Architecture: `res_skip` network (imported from `model_torch.py` in vendor directory)
- Integration: Wrapped in `src/comiccolor/extract/manga_line.py` as `MangaLineExtractor` class
- Note: Trained on manga line art; tolerance for Franco-Belgian hatching is experimental

## Configuration

**Environment:**
- No `.env` file or environment variable configuration documented
- Configuration via CLI arguments only (see `src/comiccolor/cli.py`)

**Build:**
- `pyproject.toml` - Standard Python project configuration, defines dependencies, entry point, test paths

**Entry Point:**
- CLI: `comiccolor = "comiccolor.cli:main"` - Command-line entry point in `src/comiccolor/cli.py`
- Subcommands:
  - `comiccolor p3` - P3 region-count spike benchmark (with `--weights` for custom model)
  - `comiccolor ab` - A/B comparison of trapped-ball implementations

## Database

**Storage:**
- SQLite (local file-based, no server required)
- Schema defined in `src/comiccolor/model/store.py` (PRAGMA foreign_keys enabled)
- Instantiated via `Store(path)` constructor in `src/comiccolor/model/store.py`
- No connection pooling or multi-thread safety (per docstring: "Not thread-safe; one Store per thread")

## Model & Weights

**Not Yet Integrated (planned, §1.6):**
- Cobra (SIGGRAPH 2025, github.com/zhuang2002/Cobra)
  - Licence: OpenRAIL++-M (compatible with hosted serving)
  - Dependencies: diffusers, PixArt-alpha/PixArt-XL-2-1024-MS (downloaded at runtime from huggingface.co)
  - Role: Colour proposer model (semantic, probabilistic)
  - Integration approach: Wrap as black box, do not modify DiT

## Platform Requirements

**Development:**
- Python 3.11+
- pip and setuptools
- For torch (MangaLineExtraction): CPU or GPU support (defaulted to CPU in `src/comiccolor/extract/manga_line.py`)
- For GUI/visualization: OpenCV with headless mode (cv2 works without display server)

**Production:**
- Python 3.11+ runtime
- torch optional (only if line extraction is used; can skip for colour-only pipelines)
- No external services or APIs required (entirely self-contained except for future Cobra integration)
- Storage: Local filesystem for SQLite database and image outputs

## Deployment Path

Per memory and P1 resolution (2026-08-02):
- On-premise: Fully supported (self-contained, no licence restrictions for code execution)
- Cloud/SaaS hosting: Future tier compatible
  - Cobra's OpenRAIL++-M requires use-based restrictions propagation to terms of service
  - PixArt model weights downloaded at runtime from huggingface.co (requires outbound HTTPS)
  - No AGPL concerns (misattributed to PixArt raw `.pth` mirror, which this codebase never accesses)

---

*Stack analysis: 2026-08-02*
