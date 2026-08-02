# Coding Conventions

**Analysis Date:** 2026-08-02

## Naming Patterns

**Files:**
- Lowercase with underscores: `cli.py`, `manga_line.py`, `trapped_ball.py`
- Module/package names reflect functionality: `segmentation/`, `extract/`, `model/`
- Test files use `test_` prefix: `test_masks.py`, `test_trappedball.py`

**Functions:**
- Snake_case for all function and method names: `load_line_art()`, `measure_passage_width()`, `region_stats()`
- Private functions (module-internal) prefixed with single underscore: `_ball()`, `_box_page()`, `_install_quiet_logger()`
- Descriptive names that indicate purpose: `check_coverage()`, `relabel_sequential()`, `expand_under_lines()`

**Variables:**
- Snake_case for local variables and parameters: `line_mask`, `fillable`, `label_map`, `grey`
- Clear, specific names over abbreviations: `height, width` not `h, w`
- Type-indicating for optional values: `radii: tuple[int, ...] | None`

**Types:**
- Enum classes for domain concepts: `RegionStatus`, `ProtectedKind` in `src/comiccolor/model/entities.py`
- Dataclasses for data structures: `Series`, `Volume`, `Page`, `Panel`, `Entity`, `PaletteEntry`, `Region`, `ProtectedMask` in `src/comiccolor/model/entities.py`
- Protocol classes for interface contracts: `Segmenter` protocol in `src/comiccolor/segmentation/segmenter.py`
- UPPER_CASE for module-level constants: `DEFAULT_RADII`, `UNASSIGNED`, `IMAGE_SUFFIXES`, `_STRIDE`

## Code Style

**Formatting:**
- Black-style implicit (no explicit config found)
- Line length appears to follow conventional limits (~88 chars implied)
- Consistent indentation (4 spaces)

**Linting:**
- No explicit linting config files detected (`.eslintrc`, `.flake8`, etc.)
- Code appears to follow PEP 8 conventions through discipline

## Import Organization

**Order:**
1. Module docstring with `"""..."""`
2. `from __future__ import annotations` (always present at top of source files)
3. Standard library imports: `sys`, `time`, `pathlib`, `argparse`, `json`, `sqlite3`, `logging`, `types`
4. Third-party imports: `numpy`, `opencv-python` (`cv2`), `scipy`, `PIL/Pillow`
5. Relative imports from package: `from .module import Class`, `from ..model.entities import Region`
6. Blank line before code

**Example from `src/comiccolor/segmentation/trappedball.py`:**
```python
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..model.masks import UNASSIGNED, region_stats
```

**Path Aliases:**
- Relative imports used throughout: `from .masks import UNASSIGNED`, `from ..model.entities import Entity`
- No absolute path aliases (no `@` aliases in config)

## Type Hints

**Pattern:** 
- Complete type annotations on all function signatures
- Use of modern Python 3.10+ union syntax (`X | None` instead of `Optional[X]`)
- Type hints on dataclass fields

**Examples from `src/comiccolor/cli.py`:**
```python
def _collect_pages(inputs: list[str]) -> list[Path]:
def main(argv: list[str] | None = None) -> int:
```

**Examples from `src/comiccolor/segmentation/trappedball.py`:**
```python
def trapped_ball_segment(
    line_mask: np.ndarray,
    protected: np.ndarray | None = None,
    params: SegmentationParams | None = None,
) -> np.ndarray:
```

## Error Handling

**Patterns:**
- Raise specific exceptions: `FileNotFoundError`, `ValueError`, `SystemExit`
- Use `SystemExit` with message strings for CLI errors (`src/comiccolor/cli.py` line 22, 24, 67)
- Conditional checks before operations with descriptive error messages

**Examples:**
```python
# src/comiccolor/extract/manga_line.py line 76-81
if not self.weights.exists():
    raise FileNotFoundError(
        f"MangaLineExtraction weights not found at {self.weights}. "
        "Download erika.pth from ..."
    )

# src/comiccolor/segmentation/preprocess.py line 36-37
raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
if raw is None:
    raise FileNotFoundError(f"could not read image: {path}")

# src/comiccolor/extract/manga_line.py line 100-101
if grey.ndim != 2:
    raise ValueError("MangaLineExtractor expects a 2-D greyscale array")
```

**No try-except blocks found** in source code; errors propagate to caller (unit of responsibility pattern).

## Logging

**Framework:** 
- `logging` module used minimally
- Only found in `src/comiccolor/segmentation/segmenter.py` lines 34-40 to suppress vendored library output

**Pattern:**
```python
import logging
quiet = logging.getLogger("linefiller")
quiet.addHandler(logging.NullHandler())
quiet.setLevel(logging.WARNING)
```

- Used for integration concerns (controlling third-party library verbosity)
- No application-level logging observed (design expects explicit returns/exceptions)

## Docstrings

**Module Docstrings:**
- Comprehensive explanations of design, invariants, and references to specification
- Use § symbol to reference design sections (e.g., "§3 data model", "§1.4 Trapped-ball region segmentation")
- Explain WHY, not WHAT

**Example from `src/comiccolor/model/entities.py` lines 1-17:**
```python
"""§3 data model.

Everything downstream assumes these shapes. Retrofitting is a rewrite.

Two invariants are enforced structurally rather than by convention:

1. A Region stores ``palette_entry_id`` and has no RGB field at all. There is
   nowhere to bake a colour even by accident...
```

**Function/Method Docstrings:**
- Concise one-liner describing behavior
- Additional paragraphs for parameters and return values
- Use backticks for code references: `` `line_mask` ``, `` `palette_entry_id` ``

**Example from `src/comiccolor/segmentation/preprocess.py` lines 18-33:**
```python
def load_line_art(
    path: str | Path,
    threshold: int | None = None,
    supersample: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Load an ink layer and binarise it.

    Returns ``(line_mask, grey)`` where ``line_mask`` is boolean with True on
    ink, and ``grey`` is the 8-bit greyscale the mask was derived from...
    """
```

**Inline Comments:**
- Explain design decisions and non-obvious logic
- Usually appear above the block they explain
- Often reference specification sections or external constraints

**Example from `src/comiccolor/segmentation/preprocess.py` lines 40-45:**
```python
if raw.ndim == 3 and raw.shape[2] == 4:
    # Alpha is the ink channel on a real ink layer: transparent = no ink.
    alpha = raw[:, :, 3]
    rgb = raw[:, :, :3]
    luma = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
    # Composite over white so ink darkness and coverage both count.
```

## Function Design

**Size:** 
- Functions are compact, typically under 50 lines
- Segmented into clear steps with inline comments
- Longer functions appear only in specialized modules (e.g., `load_line_art()` at 56 lines for image format handling)

**Parameters:**
- Use dataclasses for multiple related parameters: `SegmentationParams` in `src/comiccolor/segmentation/trappedball.py`
- Default to None for optional/advanced parameters, then normalize: `params = params or SegmentationParams()`
- Accept Path objects or strings (`str | Path`), normalize to `Path()` immediately

**Return Values:**
- Explicit, single return value (no tuple unpacking patterns)
- Numpy arrays used directly for image data
- Dataclass instances returned for domain objects
- Dictionaries used for structured results: `dict[int, tuple[int, tuple[int, int, int, int]]]`

## Module Design

**Exports:**
- No `__all__` lists found; all public functions/classes are module-level and not prefixed with `_`
- Imports expected to be explicit: `from .module import SpecificClass`

**Barrel Files:**
- `src/comiccolor/model/__init__.py` re-exports public classes (lines 1-41)
- Pattern: import classes from submodules, add to `__all__`, then export

**Example from `src/comiccolor/model/__init__.py`:**
```python
from .entities import (
    Entity,
    Page,
    PaletteEntry,
    ...
)
from .store import Store
from .masks import ...

__all__ = [
    "Entity",
    "Page",
    "PaletteEntry",
    ...
]
```

## Class Design

**Dataclasses:**
- Used for data containers with structural invariants
- Type hints on every field
- Docstrings explain field meanings and constraints
- `field(default_factory=list)` for mutable defaults

**Example from `src/comiccolor/model/entities.py` lines 70-85:**
```python
@dataclass
class Panel:
    page_id: int
    # Panel bounds in page pixel coordinates.
    x: int
    y: int
    width: int
    height: int
    # Position in reading order within the page, 0-based.
    reading_order: int
    id: int | None = None
    # Relative path to the label map backing this panel's regions (masks.py).
    # None until segmentation has run.
    label_map_path: str | None = None
    polygon: list[tuple[int, int]] = field(default_factory=list)
```

**Protocol Classes:**
- Used to define interfaces without implementation
- Decorated with `@runtime_checkable`
- Minimal, focused on contract

**Example from `src/comiccolor/segmentation/segmenter.py` lines 51-60:**
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

---

*Convention analysis: 2026-08-02*
