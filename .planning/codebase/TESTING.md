# Testing Patterns

**Analysis Date:** 2026-08-02

## Test Framework

**Runner:**
- pytest (v8.0+) - specified in `pyproject.toml` line 14 under `[project.optional-dependencies] dev`
- Config: `pyproject.toml` lines 26-27:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  ```

**Assertion Library:**
- pytest's built-in assertions (no extra library)
- Uses `assert` statements with optional messages for clarity

**Run Commands:**
```bash
pytest                           # Run all tests
pytest -v                        # Verbose output
pytest tests/test_specific.py    # Run single test file
pytest --cov=src                 # Coverage (if coverage plugin installed)
```

**Test Cache:**
- `.pytest_cache/` directory present (tests have been run)

## Test File Organization

**Location:**
- All test files in `tests/` directory at repository root
- Co-located pattern: `tests/` directory separate from `src/`
- One test file per module tested (not 1:1 but grouped by functionality)

**Naming:**
- `test_*.py` prefix: `test_masks.py`, `test_trappedball.py`, `test_panels.py`, `test_store.py`, `test_hatching.py`
- Test functions start with `test_`: `test_region_stats_areas_and_boxes()`, `test_closed_box_gives_inside_and_outside()`
- Descriptive names that indicate the scenario being tested

**Structure:**
```
tests/
├── test_hatching.py           # Regression tests for hatching behavior
├── test_masks.py              # Label map and region statistics tests
├── test_panels.py             # Panel segmentation and reading order tests
├── test_store.py              # Database schema and invariant tests
└── test_trappedball.py        # Trapped-ball segmentation algorithm tests
```

## Test Structure

**Suite Organization:**
```python
# tests/test_masks.py
def test_region_stats_areas_and_boxes():
    labels = np.zeros((10, 10), dtype=np.int32)
    labels[2:5, 3:7] = 1
    
    stats = region_stats(labels)
    assert stats[1] == (12, (3, 2, 4, 3))
```

**Patterns:**
- **Setup:** Create minimal test fixtures at function level (numpy arrays, test data)
- **Teardown:** Implicit; pytest cleans up fixtures and temporary files
- **Assertion:** Direct assertions with optional explanatory message strings

**Example with explanation from `tests/test_trappedball.py` lines 30-35:**
```python
def test_small_gap_does_not_leak():
    """A ball wider than the gap cannot escape. This is §1.3 gap closure."""
    labels = trapped_ball_segment(
        _box_page(gap=3), params=SegmentationParams(radii=(5, 4, 3), min_area=4)
    )
    assert labels[60, 60] != labels[5, 5], "ball leaked through a 3px gap"
```

## Fixtures

**Module-Level Helper Functions:**
- Used to generate synthetic test data (not pytest fixtures, just functions)
- Named with leading underscore: `_box_page()`, `_grid_page()`, `parallel_lines()`

**Example from `tests/test_panels.py` lines 6-22:**
```python
def _grid_page(rows: int, cols: int, size: int = 300, gutter: int = 30) -> np.ndarray:
    """A page of framed panels separated by empty gutters."""
    height = rows * size + (rows + 1) * gutter
    width = cols * size + (cols + 1) * gutter
    page = np.zeros((height, width), dtype=bool)
    
    for r in range(rows):
        for c in range(cols):
            y = gutter + r * (size + gutter)
            x = gutter + c * (size + gutter)
            page[y, x : x + size] = True
            page[y + size - 1, x : x + size] = True
            page[y : y + size, x] = True
            page[y : y + size, x + size - 1] = True
            page[y + 50 : y + 60, x + 50 : x + 200] = True
    return page
```

**Pytest Fixtures (when used):**
- Defined with `@pytest.fixture` decorator
- Used for stateful test setup (database connections, temporary directories)
- Context manager pattern for resource management

**Example from `tests/test_store.py` lines 23-41:**
```python
@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s

@pytest.fixture
def volume(store):
    series = store.add_series(Series(name="Kaito"))
    return store.add_volume(Volume(series_id=series.id, name="v1"))

@pytest.fixture
def panel(store, volume):
    page = store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))
    return store.add_panel(
        Panel(page_id=page.id, x=0, y=0, width=100, height=100, reading_order=0)
    )
```

- Fixtures can depend on other fixtures (dependency injection pattern)
- `tmp_path` fixture provided by pytest for temporary directories

## Test Patterns

### Parametrized Tests

**Framework:** `pytest.mark.parametrize`

**Example from `tests/test_hatching.py` lines 44-52:**
```python
@pytest.mark.parametrize(
    "count,pitch,wobble",
    [
        (8, 20, 0.0),                       # clean, widely spaced
        (8, 20, 4.0),                       # hand-drawn wobble
        pytest.param(18, 9, 2.0, marks=DENSE),  # dense hatching
        pytest.param(24, 7, 1.0, marks=DENSE),  # denser still
    ],
)
def test_each_strip_is_one_region(count, pitch, wobble):
    """A corridor between two parallel lines is ONE region. Ground truth."""
    page = parallel_lines(count, pitch, wobble)
    expected = count + 1
    
    labels = trapped_ball_segment(page, params=SegmentationParams(min_area=1))
    
    assert region_count(labels) == expected
```

### Expected Failures (xfail)

**Pattern:** Tests marked as expected to fail with `pytest.mark.xfail`

**Example from `tests/test_hatching.py` lines 33-41:**
```python
DENSE = pytest.mark.xfail(
    reason=(
        "Our hand-rolled trapped-ball still shatters dense hatching; the "
        "adaptive radius estimate is not tight enough. Not being tuned — this "
        "is the acceptance bar for swapping in hepesu/LineFiller, which ships "
        "the merge/grouping step this implementation lacks."
    ),
    strict=False,
)
```

- Used when implementation is known to have limitations
- Reason explains the limitation and context for future fix
- `strict=False` allows the test to pass if implementation improves

### Exception Testing

**Pattern:** `pytest.raises()` context manager

**Example from `tests/test_store.py` lines 99-102:**
```python
def test_one_label_per_panel_is_unique(store, panel):
    store.add_regions([Region(panel_id=panel.id, label=1)])
    with pytest.raises(sqlite3.IntegrityError):
        store.add_regions([Region(panel_id=panel.id, label=1)])
```

- Tests schema constraints that prevent invalid operations
- Verifies expected exceptions are raised for invariant violations

## Mocking

**Framework:** None explicitly used (minimal mocking observed)

**Pattern:** Tests use real implementations and synthetic data instead of mocks

**Example approach from `tests/test_trappedball.py`:**
```python
def test_closed_box_gives_inside_and_outside():
    # Create synthetic data instead of mocking
    labels = trapped_ball_segment(_box_page(), params=SegmentationParams(min_area=4))
    assert region_count(labels) == 2
    assert labels[60, 60] != labels[5, 5]
```

**Design Philosophy:**
- Tests use actual image processing functions with synthetic images
- Database tests use real SQLite with `tmp_path` for isolation
- Avoids mocking to test integration of components

**When would you mock:** External ML model loading (weights files), but this is handled via dependency injection (passing weights path to constructor).

## Fixtures and Factories

**Test Data:**
All synthetic data is generated inline or via helper functions. No separate factory module.

**Examples:**

1. **Numpy array fixtures:** Created directly in tests
   ```python
   labels = np.zeros((10, 10), dtype=np.int32)
   labels[2:5, 3:7] = 1
   ```

2. **Geometry fixtures:** Helper functions return structured data
   ```python
   def _box_page(gap: int = 0) -> np.ndarray:
       line = np.zeros((120, 120), dtype=bool)
       line[30, 30:90] = True
       ...
       return line
   ```

3. **Database fixtures:** Pytest fixtures with context managers
   ```python
   @pytest.fixture
   def store(tmp_path):
       with Store(tmp_path / "test.db") as s:
           yield s
   ```

**Location:**
- Helpers: Module-level in `tests/test_*.py` files
- Pytest fixtures: Defined at module level in same test file
- No conftest.py (shared fixtures across test modules) found

## Coverage

**Requirements:** Not enforced (no coverage configuration in `pyproject.toml`)

**View Coverage:**
```bash
# If pytest-cov installed:
pytest --cov=src --cov-report=html
# Opens htmlcov/index.html in browser
```

**Observation:** `.pytest_cache/` exists, indicating tests are run regularly. Coverage is not gated but is achievable.

## Test Types

**Unit Tests:**
- **Scope:** Individual functions and small modules
- **Approach:** Test algorithmic correctness with synthetic inputs
- **Examples:** `test_region_stats_*` (label map statistics), `test_measure_passage_width()` (distance calculations)
- **Location:** `tests/test_masks.py`, `tests/test_trappedball.py`, `tests/test_panels.py`

**Integration Tests:**
- **Scope:** Multi-component workflows (segmentation pipeline)
- **Approach:** End-to-end operations with synthetic data
- **Examples:** `test_closed_box_gives_inside_and_outside()` (combines trapped-ball segmentation, region counting, and label checking)
- **Location:** `tests/test_trappedball.py` (tests both algorithm and output invariants)

**Schema/Invariant Tests:**
- **Scope:** Database structure and design constraints
- **Approach:** Verify schema prevents invalid states
- **Examples:** `test_region_table_has_no_rgb_column()`, `test_rgb_lives_only_on_palette_entry()`
- **Location:** `tests/test_store.py` (asserts structure, not behavior)
- **Philosophy:** Tests document design invariants; most assertions are "what should NOT be possible"

**E2E Tests:**
- **Status:** Not found in test suite
- **Note:** CLI integration (`comiccolor p3`, `comiccolor ab`) is tested manually via `src/comiccolor/spike/` modules, not in automated tests

## Common Patterns

### Testing Invariants

**Pattern:** Assert structural properties rather than computed results

**Example from `tests/test_masks.py` lines 71-79:**
```python
def test_exclusivity_is_structural():
    """A pixel holds one label. Overlap is not representable."""
    labels = np.zeros((5, 5), dtype=np.int32)
    labels[1:4, 1:4] = 1
    labels[2:3, 2:3] = 2  # "adding" region 2 necessarily removes those px from 1
    
    stats = region_stats(labels)
    assert stats[1][0] + stats[2][0] == 9
    assert stats[2][0] == 1
```

### Docstring Commentary

Tests include module-level docstrings that explain the testing philosophy:

**From `tests/test_store.py` lines 1-5:**
```python
"""The §3 invariants, as tests.

The point of most of these is that the *schema* prevents the mistake, so the
assertions are about what is impossible rather than what is computed.
"""
```

**From `tests/test_hatching.py` lines 1-7:**
```python
"""Regression tests for strip fragmentation.

A corridor between two parallel lines is ONE region. A ball too wide to fit
inside it finds cores only where it happens to widen, and each of those becomes
a separate region — so one hatching strip shatters into dozens. These pin that
behaviour with synthetic art whose region count is known exactly.
"""
```

### Comprehensive Scenario Testing

**Pattern:** Multiple assertions per test covering different aspects of one scenario

**Example from `tests/test_trappedball.py` lines 81-92:**
```python
def test_expand_under_lines_covers_ink_but_not_protected():
    line = _box_page()
    protected = np.zeros_like(line)
    protected[95:110, 95:110] = True

    labels = trapped_ball_segment(line, protected=protected, params=SegmentationParams(min_area=4))
    expanded = expand_under_lines(labels, line)

    assert expanded[line].all(), "ink pixels should take a neighbouring label"
    assert not expanded[protected].any(), "protected pixels must stay unpainted"
    # Region identities are preserved, only extended.
    assert region_count(expanded) == region_count(labels)
```

### Comparison Testing

**Pattern:** Test behavior against multiple configurations to verify relative properties

**Example from `tests/test_hatching.py` lines 63-76:**
```python
def test_oversized_radius_shatters_strips():
    """The bug itself, pinned: 19 true regions reported as hundreds."""
    page = parallel_lines(18, 9, 2.0)

    oversized = trapped_ball_segment(
        page, params=SegmentationParams(radii=(5, 4, 3, 2, 1), min_area=1)
    )
    narrow = trapped_ball_segment(
        page, params=SegmentationParams(radii=(2, 1), min_area=1)
    )

    assert region_count(oversized) > 100, "the shattering failure mode"
    assert region_count(narrow) == 19, "a ball that fits recovers ground truth"
```

### Assertions with Messages

All complex assertions include explanatory messages for failure clarity:

```python
assert labels[60, 60] != labels[5, 5], "ball leaked through a 3px gap"
assert region_count(labels) == expected, report  # Shows report on failure
assert all(label > 0 for label in stats), "labels must be positive"
```

---

*Testing analysis: 2026-08-02*
