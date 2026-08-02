# Codebase Concerns

**Analysis Date:** 2026-08-02

## Repository State

**Uninitialized git history:**
- Files: `.gitignore`, `flatting-pipeline-spec.md`, `pyproject.toml`, `reports/`, `src/`, `tests/`
- Status: All files are untracked; no commits exist yet
- Impact: No version history, no baseline for diffs, no deployment safety. First commit must be deliberate.
- Fix approach: Run `git add` on all project files and create an initial commit with a clear message before any CI/CD is enabled.

**No CI/CD pipeline:**
- Files: None found (looking for `.github/workflows/`, `.gitlab-ci.yml`, `.circleci/config.yml`, `Makefile`, `tox.ini`, etc.)
- Impact: Code quality checks, tests, and linting are not enforced on every push. Human reviewers must manually verify before merge.
- Fix approach: Add GitHub Actions workflow for tests and linting; consider pre-commit hooks for local validation.

## Dependencies & Licensing

**PyTorch not declared as a dependency:**
- Files: `src/comiccolor/extract/manga_line.py` (line 74-75 imports torch), `pyproject.toml`
- Issue: `torch` is imported at runtime in `MangaLineExtractor._load()` but is not listed in `pyproject.toml` dependencies
- Impact: Installation will not pull torch; users must install it separately or face silent import failures
- Fix approach: Add `torch>=2.0` to `pyproject.toml` dependencies (or as optional `[torch]` extra if torch is optional for non-ML builds)

**Model weights not versioned:**
- Files: `.gitignore` (line 24: `*.pth`), `src/comiccolor/extract/manga_line.py` (line 37)
- Issue: `erika.pth` (172 MB, per spec line 21) is git-ignored. Users must manually download from GitHub releases or find the file elsewhere
- Impact: Reproducibility is fragile; wrong weight versions may silently load if found in the path
- Fix approach: Either (a) pin a specific erika.pth version in setup docs with SHA256 verification, or (b) add a setup/fetch script that downloads and validates weights on first use

**Third-party licensing is clean:**
- Files: `third_party/LineFiller/LICENSE` (MIT), `third_party/MangaLineExtraction/LICENSE` (MIT)
- Status: Both vendored libraries are MIT-licensed, which is permissive and commercially usable
- Note: The spec (line 46-83) resolves the AGPL question; OpenRAIL++-M applies only via diffusers runtime pull, not distribution

## Code Quality Issues

**Dynamic sys.path manipulation (two instances):**
- Files: `src/comiccolor/extract/manga_line.py` (line 82-83), `src/comiccolor/segmentation/segmenter.py` (line 123-124)
- Issue: Both modules append vendor directories to `sys.path` at import time. This is fragile and can cause conflicts if other code modifies sys.path.
- Impact: Potential import conflicts, hard-to-debug module resolution, loss of encapsulation
- Fix approach: Use `importlib.util.spec_from_file_location()` to load vendor modules directly without polluting sys.path

**LineFiller logger pre-emption (workaround rather than solution):**
- Files: `src/comiccolor/segmentation/segmenter.py` (lines 23-48: `_install_quiet_logger()`)
- Issue: The function pre-creates a fake `log.logger` module to prevent LineFiller from opening `./log/app.log` on import, because vendored LineFiller has a side effect that creates this file relative to the working directory
- Impact: Fragile — if LineFiller's import changes, this workaround breaks silently. The fake logger is a band-aid on a vendor import with side effects
- Fix approach: Either (a) patch LineFiller's logger before vendoring, or (b) ensure the working directory is safe for file creation, or (c) move away from LineFiller if the side effect becomes unmaintainable

**Insufficient test coverage:**
- Files: `tests/` (497 lines total; breakdown: `test_store.py` 129, `test_trappedball.py` 99, `test_panels.py` 74, `test_masks.py` 94, `test_hatching.py` 101)
- Gaps:
  - CLI (`src/comiccolor/cli.py`) has no tests
  - `src/comiccolor/extract/manga_line.py` has no tests (the largest feature-bearing module at 208 lines)
  - `src/comiccolor/extract/passthrough.py` has no tests
  - Spike modules (`spike/p3.py`, `spike/ab.py`) have no tests; these contain complex report generation logic
  - No integration tests for end-to-end workflows
  - No error-handling tests (e.g., missing weights file, corrupted image input)
- Impact: Regressions in extract or spike logic go unnoticed; CLI changes risk breaking user workflows
- Fix approach: Add tests for extractors (mock torch if needed), CLI argument parsing, and spike report generation. Target >80% coverage for src/ excluding spike modules (which are experimental).

**No error handling in spike report modules:**
- Files: `src/comiccolor/spike/p3.py`, `src/comiccolor/spike/ab.py`
- Issue: These modules load images, extract lines, and segment without try/except. If an image is corrupted or a step fails mid-run, the entire run fails and results are not persisted
- Impact: Running p3 or ab on 10+ pages will lose all progress if one page fails
- Current workaround: `ab.py` (line 75-86) does persist results incrementally and can resume; `p3.py` does not
- Fix approach: Add per-page error handling to both modules; log failures and continue; add resume capability to p3.py

## Architectural Concerns

**Deferred panel boundary crossing detection:**
- Files: `flatting-pipeline-spec.md` (line 164-169)
- Issue: The spec acknowledges that artists draw open panels, characters crossing borders, and large SFX overlaying multiple panels. Panel segmentation does not solve this, and bubble/SFX detection is "deferred to project start."
- Impact: Users will need to manually mask open areas or live with colourization errors where art crosses panel lines
- Fix approach: Research and integrate an open-source comic bubble/text detector before shipping Tier 2 (the interactive UI stage)

**Trapped-ball gap closure has a fundamental trade-off:**
- Files: `src/comiccolor/segmentation/closure.py` (lines 39 in comment), `flatting-pipeline-spec.md` (line 91-93)
- Issue: The trapped-ball algorithm and gap closure parameters are in direct tension with hatching absorption. The spec notes: "gap closure and hatching are in direct tension, and no radius satisfies both. Hatching has to be removed upstream (§7 Tier 3), not segmented around."
- Impact: Users cannot tune a single radius parameter to handle both fine line art and dense hatching; they must choose via the `radii` parameter in `SegmentationParams`
- Current mitigation: `adaptive_radii()` (line 69-85 in trappedball.py) estimates passable width from the artwork itself, which is better than a fixed schedule but not perfect
- Fix approach: Hatching removal is in scope for Tier 3 (not Tier 1); document the trade-off and recommend the `MangaLineExtractor` for hatching-heavy input

**Line gap closure relies on endpoint detection via skeletonization:**
- Files: `src/comiccolor/segmentation/closure.py` (line 68-76)
- Issue: The `find_endpoints()` function uses `skimage.morphology.skeletonize()` to find stroke ends and bridge them. Skeletonization is sensitive to thinning artifacts and noise
- Impact: On low-resolution or noisy line art, bridging may fail to find real endpoints or create false bridges
- Fix approach: Add optional pre-processing (morphological closing) via `ClosureParams.close_radius` (line 44); document that closure is most reliable on clean line art

## Missing Infrastructure

**No input validation for image data:**
- Files: `src/comiccolor/segmentation/preprocess.py`, `src/comiccolor/cli.py`
- Issue: Modules load images but do not validate dimensions, color space, or bit depth before processing
- Impact: Malformed images may crash downstream code with cryptic numpy/OpenCV errors instead of user-friendly messages
- Fix approach: Add `validate_image()` helper in preprocess.py; check for min/max dimensions and require uint8 greyscale or RGB input

**No logging or observability:**
- Files: Entire codebase
- Issue: There is no structured logging, error reporting, or user-facing feedback mechanisms. Spike runs are silent except for stdout prints
- Impact: Users cannot see progress on long runs; errors are lost without stderr redirection
- Fix approach: Add Python `logging` module with info/warning/error levels; consider telemetry hooks for hosted tier in future

**No distributed/batch processing:**
- Files: Spike modules assume single-threaded processing
- Issue: `run_p3()` and `run_ab()` process pages sequentially. Multi-threaded or async processing would speed up CI runs
- Impact: Full evaluation runs can take hours; this blocks rapid iteration
- Fix approach: Defer to Tier 2+; consider thread pool or async pattern if spike evaluation becomes a bottleneck

## Security & Compliance

**Secrets handling is absent:**
- Files: CLI takes `--weights` argument; no env var override
- Issue: There is no mechanism to inject credentials, API keys, or secrets. Future hosted tier will need this
- Impact: SaaS deployment will require adding secret management (env vars, config files) and secure credential passing
- Fix approach: Plan secret handling architecture before Tier 2 (cloud backend)

**Model weight source is implicit:**
- Files: `src/comiccolor/extract/manga_line.py` (line 80: hardcoded GitHub URL)
- Issue: The error message points to a GitHub release, but there is no pinned version or checksum validation
- Impact: Users may accidentally load an old or malicious weight file if the GitHub release is tampered with
- Fix approach: Add SHA256 checksum verification; store it in a manifest file or pyproject.toml; warn if checksums do not match

## Known Limitations (Stated)

**American comics untested:**
- Files: `flatting-pipeline-spec.md` (line 104-105)
- Issue: P3 test results cover four distinct manga/European styles but not American variable-weight inking, spot blacks, or feathering
- Impact: Tier 1 ships without data on how well it handles American comics; users may see high region counts or extraction failures
- Status: This is known and acknowledged as needing "a retrained extractor" (§7)
- Fix approach: This is scope for Tier 3; document in release notes

**Teddy page ink fraction collapse is explained but not solved:**
- Files: `flatting-pipeline-spec.md` (line 110-113)
- Issue: Teddy page shows ink fraction dropping from 0.173 to 0.058 after extraction because flat black zones are converted to contours
- Status: Spec confirms this is benign (structure is preserved) but is unintuitive to users
- Fix approach: Document the ink-fraction metric in user guide; explain that extraction optimizes for structural lines, not pixel coverage

## Performance & Scaling

**No explicit memory limits:**
- Files: Code assumes images fit in memory
- Issue: Full-resolution studio pages (300 dpi, ~3500×5000 px) require ~80 MB per channel; multi-page runs or batch processing could exhaust RAM
- Current mitigation: `MangaLineExtractor` has a `tile` parameter (default 1024px) that bounds peak memory by tiling; `trapped_ball_segment()` has no such limit
- Fix approach: Add optional downscaling for trapped-ball if memory is constrained; document memory requirements in README

**Spike ab.py merge pass is slow:**
- Files: `src/comiccolor/spike/ab.py` (line 14: "A merged LineFiller pass is minutes per page")
- Issue: LineFiller with `merge_fill()` (10 iterations by default) is slow; a 4-page evaluation can take >1 hour
- Impact: Iterating on parameters or adding pages to evaluation is slow
- Fix approach: Profile and consider reducing default `merge_iterations` or adding early exit if no merges happen

## Deployment & Versioning

**No version pinning for scipy/numpy:**
- Files: `pyproject.toml` (lines 7-10: `numpy>=2.0`, `scipy>=1.14`, `pillow>=11.0`, `opencv-python-headless>=4.10`)
- Issue: Version constraints are loose (>= only). Major version changes in numpy or scipy could introduce silent breakage
- Impact: Determinism across environments is not guaranteed; users on different machines may get different results
- Fix approach: Consider pinning to specific minor versions in production; document which numpy/scipy versions have been tested

**Build tooling is minimal:**
- Files: `pyproject.toml` uses modern setuptools; no build script or pre-build hooks
- Issue: No mechanism to download model weights or validate third-party vendoring during `pip install`
- Impact: First-time setup requires manual steps (git clone LineFiller, download erika.pth)
- Fix approach: Add a setup.py with a custom build_py command to fetch weights on install, or document a post-install setup script

---

*Concerns audit: 2026-08-02*
