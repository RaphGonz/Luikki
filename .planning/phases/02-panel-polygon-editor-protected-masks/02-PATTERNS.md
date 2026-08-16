# Phase 2: Panel Polygon Editor & Protected Masks - Pattern Map

**Mapped:** 2026-08-16
**Files analyzed:** 17
**Analogs found:** 15 / 17

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/comiccolor/segmentation/panels.py` (extend: `box_to_polygon`, lower `min_solidity`) | service/utility | transform | itself (existing module) | exact |
| `src/comiccolor/segmentation/bubbles.py` (new) | service | transform (CV pipeline) | `src/comiccolor/segmentation/panels.py` | exact (same module shape: dataclass params + pure `np.ndarray`-in/out function) |
| `src/comiccolor/model/entities.py` (extend `ProtectedMask`, `Panel.polygon` usage) | model | CRUD | itself — `Panel`/`ProtectedMask` dataclasses already present | exact |
| `src/comiccolor/model/store.py` (schema: `protected_mask.panel_id`→`page_id`, `polygon`, `touched`; new query/CRUD methods) | model/persistence | CRUD | itself — `add_protected_mask`/`protected_for_panel`, and `palette_entry` CRUD methods (`add_palette_entry`, `update_palette_label`, `delete_palette_entry`) | exact |
| `src/comiccolor/pipeline/stages.py` (fill `panels`/`protected` `runner=`) | config/registry | event-driven (gate transition) | `src/comiccolor/pipeline/runner.py::run_import` | exact — same `StageRunner` signature |
| `src/comiccolor/web/routers/panel.py` (new) | controller/route | request-response, CRUD | `src/comiccolor/web/routers/palette.py` | exact |
| `src/comiccolor/web/routers/protected.py` (new) | controller/route | request-response, CRUD | `src/comiccolor/web/routers/palette.py` | exact |
| `src/comiccolor/web/schemas.py` (extend: vertex/polygon request/response models) | model/DTO | transform | itself — `PaletteEntryCreateRequest`/`PaletteEntryResponse`/`PaletteUpdateResponse` | exact |
| `tests/test_panels.py` (extend) | test | — | itself | exact |
| `tests/test_bubbles.py` (new) | test | — | `tests/test_panels.py` (pure numpy-array-in, dataclass-list-out unit tests) | exact |
| `tests/test_web/test_panel_routes.py` (new) | test | request-response | `tests/test_web/test_palette_routes.py` | exact |
| `tests/test_web/test_protected_routes.py` (new) | test | request-response | `tests/test_web/test_palette_routes.py` | exact |
| `tests/test_trappedball.py` (extend: boundary-crossing protected case) | test | — | itself | exact |
| `frontend/src/editor/canvasEditor.ts` (new) | component/controller | event-driven (pointer events) | `frontend/src/components/swatchCard.ts` (commit-on-release pattern) + `frontend/src/geometry/transform.ts` (coordinate math) | role-match |
| `frontend/src/editor/polygonState.ts` (new) | store/reducer | transform | `frontend/src/geometry/transform.ts` (pure, DOM-free, unit-tested module shape) | role-match |
| `frontend/src/editor/hitTest.ts` (new) | utility | transform | `frontend/src/geometry/transform.ts` | exact (same "pure arithmetic only" doc convention) |
| `frontend/src/editor/undoStack.ts` (new) | utility/store | transform | `frontend/src/geometry/transform.ts` | role-match |
| `frontend/src/views/pageEditor.ts` (new) | component/view | request-response + event-driven | `frontend/src/views/palette.ts` (screen orchestrating a component + api client calls) | role-match |
| `frontend/tests/editor/*.test.ts` (new) | test | — | `frontend/tests/transform.test.ts` | exact |

## Pattern Assignments

### `src/comiccolor/segmentation/bubbles.py` (service, CV transform)

**Analog:** `src/comiccolor/segmentation/panels.py`

**Module docstring / imports pattern** (lines 1-39):
```python
"""§1.1 Panel segmentation. ... """
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import cv2
import numpy as np
```
Mirror this shape for `bubbles.py`: a `§`-referenced module docstring explaining the WHY (D-22/D-23 seed→flood→cap algorithm), then `@dataclass` params class (`BubbleParams`, mirroring `PanelParams`'s per-field inline comments), then pure functions taking/returning `np.ndarray`/dataclass lists — never a class with mutable state.

**Core pattern — dataclass params + pure function returning a list of typed boxes** (`panels.py` lines 43-105):
```python
@dataclass
class PanelParams:
    min_gutter_frac: float = 0.012
    ...

@dataclass
class PanelBox:
    x: int
    y: int
    width: int
    height: int

def segment_panels(line_mask: np.ndarray, params: PanelParams | None = None) -> list[PanelBox]:
    params = params or PanelParams()
    ...
    return _reading_order(boxes, params.reading)
```
`detect_bubbles(grey, line_mask, params: BubbleParams | None = None) -> list[np.ndarray]` and `mask_to_polygon(mask, epsilon_frac) -> list[tuple[int,int]]` should follow this exact `params = params or Params()` normalization idiom and single-purpose private helpers (`_glyph_candidates` mirrors `_gutter_network`/`_reinforce_frames`).

**Guard-shape reuse** (`panels.py` line 91, `min_area_frac`): the bubble area cap (D-22 point 3) reuses this exact "discard below/above a page-area-fraction threshold" idiom — `if area < min_area: continue` / the inverse for a max cap.

---

### `src/comiccolor/segmentation/panels.py` (extend — `box_to_polygon`, D-17/D-18)

**Analog:** itself.

Add a pure function beside `PanelBox` (same file, same style as `_reading_order`):
```python
def box_to_polygon(box: PanelBox) -> list[tuple[int, int]]:
    """D-17: seed with the box corners, clockwise from top-left."""
    return [
        (box.x, box.y),
        (box.x + box.width, box.y),
        (box.x + box.width, box.y + box.height),
        (box.x, box.y + box.height),
    ]
```
Lower `min_solidity` default at line 54 per D-18 (do not raise it back — see CONTEXT.md D-18's explicit warning).

---

### `src/comiccolor/model/entities.py` (extend `ProtectedMask`)

**Analog:** itself — `Panel` (line 103) and current `ProtectedMask` (line 167) dataclasses.

Read lines 103-116 (`Panel`) and 167-end (`ProtectedMask`) directly before editing — `Panel.polygon` already exists at line 116 unused; the field type/shape to match for `ProtectedMask.polygon` is that same `list[tuple[int, int]]`. Add `page_id: int` (replacing `panel_id`), `touched: bool = False`. Keep the dataclass field-ordering convention: required fields first, `id: int | None = None` and defaulted fields last, matching `Panel`'s and `PaletteEntry`'s existing shape.

---

### `src/comiccolor/model/store.py` (schema + CRUD)

**Analog:** itself — `protected_mask` table (lines 110-125) and `palette_entry` CRUD methods.

**Schema pattern** (lines 110-125, current):
```sql
CREATE TABLE IF NOT EXISTS protected_mask (
    ...
    panel_id  INTEGER NOT NULL REFERENCES panel(id) ON DELETE CASCADE,
    ...
);
...
CREATE INDEX IF NOT EXISTS idx_protected_panel ON protected_mask(panel_id);
```
Rewrite (no `ALTER TABLE`; D-20/Pitfall 5 — no shipped data exists yet) to `page_id INTEGER NOT NULL REFERENCES page(id) ON DELETE CASCADE`, add `polygon TEXT NOT NULL DEFAULT '[]'`, `touched INTEGER NOT NULL DEFAULT 0`; rename the index to `idx_protected_page`.

**CRUD method pattern** — mirror `add_palette_entry`/`update_palette_label`/`delete_palette_entry` (referenced via `palette.py` router calls) and existing `add_protected_mask`/`protected_for_panel` (lines 538-550) for the new `update_panel_vertex`, `update_protected_mask_polygon`, `protected_for_page` methods: parameterized `self._execute(...)` calls, row re-read after write, no raw SQL in routers (per RESEARCH.md's Integration Points note).

---

### `src/comiccolor/pipeline/stages.py` (fill `panels`/`protected` runners)

**Analog:** `src/comiccolor/pipeline/runner.py::run_import` (referenced at `stages.py` line 44, `from .runner import run_import`).

**StageRunner contract** (`stages.py` lines 46-48):
```python
StageRunner = Callable[[Store, Page], None]
```
New `run_panels`/`run_protected` functions in `pipeline/runner.py` (or a sibling module) must match this exact signature — mutate `page`/`store` to advance the gate, never walk the chain (module docstring point 2, D-10). Wire into `Stage(..., runner=run_panels)` / `Stage(..., runner=run_protected)` at lines 82 and 89, replacing `runner=None`.

---

### `src/comiccolor/web/routers/panel.py` and `protected.py` (new)

**Analog:** `src/comiccolor/web/routers/palette.py` (full file read, 208 lines).

**Imports pattern** (lines 1-28):
```python
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from ...model import PaletteEntry, Project, Store
from ..deps import get_current_project_path, get_project, get_store
from ..schemas import (...)
router = APIRouter()
ENTRY_NOT_FOUND_DETAIL = "..."
```
Mirror `..._NOT_FOUND_DETAIL` module constants (`PANEL_NOT_FOUND_DETAIL`, `PROTECTED_MASK_NOT_FOUND_DETAIL`) and the same `get_store`/`get_project`/`get_current_project_path` dependency trio.

**Response-adapter pattern** (lines 36-44, `_entry_response`):
```python
def _entry_response(entry: PaletteEntry) -> PaletteEntryResponse:
    """The one adapter from the domain dataclass to the HTTP contract."""
    return PaletteEntryResponse(...)
```
One private `_panel_response(panel) -> PanelResponse` / `_protected_response(mask) -> ProtectedMaskResponse` adapter per router, called from every route — never construct the response model inline at each call site.

**PATCH pattern with 404-after-concurrent-delete guard** (lines 92-131, `update_palette_entry`):
```python
@router.patch("/{entry_id}", response_model=PaletteUpdateResponse)
def update_palette_entry(entry_id, body, store=Depends(get_store)) -> PaletteUpdateResponse:
    entry = store.palette_entry_by_id(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=ENTRY_NOT_FOUND_DETAIL)
    if body.label is not None:
        store.update_palette_label(entry_id, body.label)
    ...
    updated = store.palette_entry_by_id(entry_id)
    if updated is None:
        # row can disappear between the existence check and re-read
        raise HTTPException(status_code=404, detail=ENTRY_NOT_FOUND_DETAIL)
    return ...
```
Copy this exact "check exists → mutate → re-read → guard the re-read too" shape for `PATCH /panel/{panel_id}/vertex/{vertex_index}` (sketched already in RESEARCH.md's own Code Examples section, same shape confirmed here against the real file).

**DELETE pattern** (lines 134-147): existence check, then `store.delete_...(id)`, `204 NO_CONTENT`, no confirmation dialog server-side (matches D-19/§5's no-confirm delete).

**Sync `def` route rationale** (docstring lines 181-187) — copy verbatim reasoning for why bubble-detection's POST route must also stay a sync `def`, not `async def`, given `Store`'s one-per-thread contract (also directly relevant to RESEARCH.md Pitfall 6).

---

### `src/comiccolor/web/schemas.py` (extend)

**Analog:** itself — `PaletteEntryCreateRequest`/`PaletteEntryResponse`/`PaletteUpdateResponse` (imported at `palette.py` lines 22-28; read the actual class bodies in `schemas.py` before writing new models — not re-read here, but follow the same `RGBChannel = Annotated[int, Field(ge=0, le=255)]`-style bounded-field convention RESEARCH.md's Security Domain section already names for vertex-coordinate bounds).

---

### `tests/test_web/test_panel_routes.py`, `test_protected_routes.py` (new)

**Analog:** `tests/test_web/test_palette_routes.py` (lines 1-60 read).

**Module docstring pattern** (lines 1-14): explain the requirement IDs and decision IDs the file covers, referencing CONTEXT.md decisions by number (`PAN-02, D-19: ...`).

**Test shape** (lines 16-39, `test_swatch_upload_creates_colour_n_entries`): `client` + fixture-built input → `client.post(...)` → assert `resp.status_code` → assert on `resp.json()` fields → cross-check via a subsequent `client.get(...)`. Use `client`/`make_png` fixtures from `tests/test_web/conftest.py` unchanged.

---

### `tests/test_bubbles.py` (new)

**Analog:** `tests/test_panels.py` (lines 1-50 read).

**Fixture pattern** (`_grid_page` helper, lines 6-22): a private `_page_with_bubble(...)` numpy-array builder function, same shape — build a synthetic boolean/uint8 array with `page[y, x:x+w] = True` slicing, no image files. Test functions are short, one assertion focus each (`test_finds_every_panel_in_a_grid`, `test_single_panel_page`, `test_manga_reading_order_is_right_to_left`).

---

## Shared Patterns

### Backend: params dataclass + pure function
**Source:** `src/comiccolor/segmentation/panels.py` (`PanelParams`, `segment_panels`)
**Apply to:** `bubbles.py`'s `BubbleParams`/`detect_bubbles`/`mask_to_polygon`, and `rasterize_protected_for_panel` (Pattern 4 in RESEARCH.md). Always `params = params or Params()` normalize; every numeric threshold is a named dataclass field with an inline comment explaining the tradeoff, never a bare literal in the function body.

### Backend: route existence-check → mutate → re-read → guard
**Source:** `src/comiccolor/web/routers/palette.py` lines 92-131
**Apply to:** every PATCH/DELETE route in `panel.py` and `protected.py`.

### Backend: per-domain `_xxx_response` adapter + `XXX_NOT_FOUND_DETAIL` constant
**Source:** `src/comiccolor/web/routers/palette.py` lines 32, 36-44
**Apply to:** `panel.py`, `protected.py`.

### Backend: sync `def` routes only (never `async def`)
**Source:** `src/comiccolor/web/routers/palette.py` lines 181-187 docstring
**Apply to:** every new route, including the bubble-detection trigger route (RESEARCH.md Pitfall 6) — `Store`'s one-per-thread contract is violated by `async def` + sync `get_store`.

### Frontend: pure, DOM-free, unit-tested module (no side effects, no imports beyond types)
**Source:** `frontend/src/geometry/transform.ts` (full file, "Pure arithmetic only: no DOM access, no imports" — final line of module docstring)
**Apply to:** `hitTest.ts`, `polygonState.ts`, `undoStack.ts` — every module RESEARCH.md's Pitfall 3 says must stay canvas-free and DOM-free so it can be unit-tested under the existing `node`-environment vitest config without `jsdom`/`canvas`.

### Frontend: commit-on-release, not commit-on-every-frame (T-01-FLOOD)
**Source:** `frontend/src/components/swatchCard.ts` lines 59-71 (`picker.addEventListener('input', ...)` updates the visual only; `'change'`/`'blur'` fire `commitRecolour`, gated by `lastCommittedHex` to skip no-op writes)
**Apply to:** `canvasEditor.ts`'s `pointermove` (local-only `polygonState` mutation + `requestAnimationFrame` redraw) vs `pointerup` (the one API write) — RESEARCH.md's own Pattern 5 sketch already names this analog; this is the concrete source excerpt to copy the debounce-by-comparing-last-committed-value idiom from.

### Frontend: `textContent`/`.value`, never `innerHTML` (T-01-XSS)
**Source:** `frontend/src/components/swatchCard.ts` line 11 docstring + line 107 (`deleteButton.textContent = "×"`)
**Apply to:** any label/badge text the canvas editor or `pageEditor.ts` renders as DOM (reading-order badges, toolbar labels).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `frontend/src/editor/canvasEditor.ts` draw-loop internals (z-order layering, `requestAnimationFrame` redraw loop itself) | component | streaming (render loop) | No existing canvas/rendering code in the frontend at all — Phase 1 has no `<canvas>` consumer. Follow RESEARCH.md's own Pattern 5 sketch and Pointer Events (not mouse events) per its explicit recommendation; there is no in-repo precedent to copy beyond the coordinate math (`transform.ts`) and the commit-on-release idiom (`swatchCard.ts`) already mapped above. |
| `frontend/vitest.config.ts` jsdom-environment addition | config | — | Current config is `environment: "node"` project-wide with zero DOM tests (WR-14). No existing per-file `// @vitest-environment jsdom` docblock or dual-config precedent in this repo to copy; RESEARCH.md's Wave 0 Gaps section is the only guidance. |

## Metadata

**Analog search scope:** `src/comiccolor/segmentation/`, `src/comiccolor/model/`, `src/comiccolor/pipeline/`, `src/comiccolor/web/routers/`, `frontend/src/`, `tests/`, `tests/test_web/`
**Files scanned:** panels.py, entities.py, store.py, stages.py, runner.py (referenced), palette.py, schemas.py (referenced), transform.ts, swatchCard.ts, test_panels.py, test_web/test_palette_routes.py
**Pattern extraction date:** 2026-08-16
