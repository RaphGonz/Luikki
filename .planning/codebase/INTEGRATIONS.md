# External Integrations

**Analysis Date:** 2026-08-02

## APIs & External Services

**Currently Integrated:**
- None. Codebase is entirely self-contained.

**Planned (not yet implemented):**
- **Cobra (SIGGRAPH 2025)** - Colour proposal model
  - Service: Hugging Face Model Hub (huggingface.co)
  - What it's used for: Semantic colour suggestion per panel (§1.6)
  - Dependencies: diffusers library (not yet added to `pyproject.toml`)
  - Model: PixArt-alpha/PixArt-XL-2-1024-MS (downloaded at runtime from `hf.co`)
  - Auth: None (public model, but rate-limited without API token)
  - Note: Per P1 resolution, Cobra never redistributes PixArt; it downloads at runtime, avoiding AGPL constraints

## Data Storage

**Databases:**
- **SQLite (Local)**
  - Type: File-based relational database
  - Connection: Direct filesystem I/O (no network required)
  - Client: Python standard `sqlite3` module
  - Implementation: `src/comiccolor/model/store.py` (`Store` class)
  - Schema: Tables for Series, Volume, Page, Panel, Entity, PaletteEntry, Region, ProtectedMask (PRAGMA foreign_keys enabled)
  - Thread safety: Not thread-safe (one Store per thread per docstring)
  - Usage: Persistent storage of colour palette, region assignments, panel metadata

**File Storage:**
- Local filesystem only (images, intermediate rasters, label maps)
- No cloud storage integration
- Paths stored as strings in SQLite (e.g., `panel.label_map_path`, `protected_mask.mask_path`)

**Caching:**
- None. In-memory caching handled by Python process; no persistent cache layer

## Authentication & Identity

**Auth Provider:**
- None implemented. No user authentication required.

**Future Considerations (§6):**
- Cross-page identity propagation planned (character recognition across volume)
- Character reference images stored in `Entity` table (editable)
- Not yet automated; will require manual matching initially

## Monitoring & Observability

**Error Tracking:**
- None integrated

**Logs:**
- Console output via Python's print statements (in `src/comiccolor/cli.py` for report formatting)
- File output: Reports written to `reports/` directory (JSON + Markdown)
  - Example: `reports/p3/p3.json`, `reports/p3/p3.md` from P3 spike
  - Example: `reports/ab/ab.json`, `reports/ab/ab.md` from A/B spike
- Suppressed vendor logging:
  - LineFiller's `log.logger` is intercepted in `src/comiccolor/segmentation/segmenter.py:_install_quiet_logger()` to prevent unwanted `./log/app.log` creation

**Metrics Instrumentation (§5):**
- Post-correction minutes per page — not yet tracked
- Hints required ÷ fillable regions — not yet tracked
- Regions per panel — tracked in P3 spike (`src/comiccolor/spike/p3.py`)
- % regions auto-accepted — tracked in region status (`RegionStatus.auto` vs `.manual` vs `.flagged` in `src/comiccolor/model/entities.py`)
- Flagged-region precision — not yet tracked

## CI/CD & Deployment

**Hosting:**
- On-premise only (currently). Future cloud tier possible.
- Deployment model: Library + CLI (no web server)
- Runtime: Python 3.11+ executable, no containerization configured

**CI Pipeline:**
- None configured (no `.github/workflows/`, `.gitlab-ci.yml`, or equivalent)

**Testing Infrastructure:**
- pytest runner (configured in `pyproject.toml`, testpaths: `tests/`)
- Test files: `tests/test_*.py`
- No automated test triggers in source tree

## Environment Configuration

**Required env vars:**
- None documented or enforced

**Optional settings (via CLI):**
- `--weights`: Path to MangaLineExtraction weights (default: `third_party/MangaLineExtraction/erika.pth`)
- `--reading`: Panel reading order (rtl or ltr, default: rtl)
- `--out`: Output directory for reports (default: `reports/p3` or `reports/ab`)
- `--no-debug`: Skip debug render output

**Secrets location:**
- No secrets stored in codebase
- No `.env` file
- Model weights and data stored locally on filesystem

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Model & Weight Downloads

**Bundled (vendored):**
- `third_party/MangaLineExtraction/erika.pth` - Structural line extraction weights (PyTorch state dict, ~50MB)
  - Loaded by `MangaLineExtractor` in `src/comiccolor/extract/manga_line.py`
  - Automatic fallback to default path if not found; raises FileNotFoundError with download instructions

**Downloaded at Runtime (future):**
- Cobra weights (not yet implemented)
  - Via `diffusers.PreTrainedModel.from_pretrained("zhuang2002/Cobra", ...)`
- PixArt-alpha/PixArt-XL-2-1024-MS (future)
  - Via `diffusers.PixArtTransformer2DModel.from_pretrained("PixArt-alpha/PixArt-XL-2-1024-MS", ...)`
  - Downloaded from huggingface.co (public, no auth required unless using API token for rate limiting)

## Data Format & Interoperability

**Input Formats:**
- Image files: `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, `.webp` (defined in `src/comiccolor/cli.py:IMAGE_SUFFIXES`)

**Output Formats (planned, §2.3 P4):**
- **PSD (Photoshop)** - Primary export format
  - One layer group per panel
  - One layer per colour (default option)
  - Flats layer (alternative)
  - Per-zone layers (alternative)
  - Reason: Compatible with both Clip Studio Paint and Photoshop; matches production workflow

**Intermediate Formats:**
- Label maps: `.png` (uint32 rasters, one pixel value per region)
- Protected masks: `.png` (binary masks for bubbles, SFX, text)
- JSON: Report metadata (P3 and A/B spike results in `reports/*/p3.json`, `reports/*/ab.json`)
- Markdown: Human-readable reports (`reports/*/p3.md`, `reports/*/ab.md`)

## Third-Party Licences Summary

| Component | Licence | Location | Status | Notes |
|-----------|---------|----------|--------|-------|
| LineFiller | MIT | `third_party/LineFiller/` | Vendored, integrated | Trapped-ball segmentation engine |
| MangaLineExtraction | MIT | `third_party/MangaLineExtraction/` | Vendored, integrated | Structural line extraction model + erika.pth weights |
| PixArt-alpha (code) | Apache-2.0 | huggingface.co (runtime) | Future dependency | Not redistributed; downloaded at runtime by Cobra |
| PixArt-alpha (diffusers weights) | openrail++ | huggingface.co (runtime) | Future dependency | **This is the licence in our chain** (NOT AGPL). Required propagation for hosted serving. |
| Cobra | Not explicitly licensed; inherits diffusers constraints | Future | Planned (§1.6) | Colour proposer model; no modifications to DiT |

**No AGPL in the chain (P1 resolved 2026-08-02):**
- The AGPL-3.0 sits only on PixArt's raw `.pth` mirror (`hf.co/PixArt-alpha/PixArt-alpha`), which is never accessed
- Cobra's runtime download uses diffusers distribution (openrail++), which is compatible with commercial deployment
- On-premise serving: No licence restrictions
- Cloud/SaaS serving: Must propagate openrail++-M use-based restrictions to terms of service (contract work, not architecture)

---

*Integration audit: 2026-08-02*
