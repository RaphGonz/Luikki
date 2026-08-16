"""The stage-chain contract, as tests.

D-06 makes the pipeline a linear, page-scoped chain rather than a
per-panel state machine; D-07 says a freshly imported page starts life
already at ``panels``, not at some pre-import limbo stage; D-10 requires
the chain to be fully linked (every stage but the first has an
upstream); D-11 makes the registry declarative — one ``Stage`` entry per
``PipelineStage``, at most one non-``None`` runner, no dynamic dispatch.
"""

import cv2
import numpy as np
import pytest

from comiccolor.model import Page, PipelineStage, ProtectedKind, Project, Store, Volume
from comiccolor.pipeline import STAGES, StageNotImplementedError, run_import, run_stage, stage_for
from comiccolor.pipeline.runner import BubbleDetectionFailed, run_panels, run_protected
from tests.conftest import bubble_page


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s


def _new_page(store: Store, source_path: str) -> Page:
    project = store.add_project(Project(name="Kaito"))
    volume = store.add_volume(Volume(project_id=project.id, name="v1"))
    return store.add_page(Page(volume_id=volume.id, source_path=source_path, index=0))


@pytest.fixture
def page(store):
    return _new_page(store, "p1.png")


def _two_panel_grid_image() -> np.ndarray:
    """A page of two framed panels side by side, as an 8-bit greyscale raster
    (0 = ink, 255 = paper) suitable for ``cv2.imwrite`` -- the on-disk
    equivalent of ``test_panels.py``'s ``_grid_page`` boolean array. This
    lives here rather than in ``conftest.py`` because ``run_panels`` reads a
    real file via ``load_line_art``, not an in-memory mask, and no other
    test needs a rasterised grid on disk (plan 02-01 owns conftest.py's
    in-memory builders)."""
    size, gutter = 200, 30
    height = size + 2 * gutter
    width = 2 * size + 3 * gutter
    page = np.zeros((height, width), dtype=bool)
    for col in range(2):
        y = gutter
        x = gutter + col * (size + gutter)
        page[y, x : x + size] = True
        page[y + size - 1, x : x + size] = True
        page[y : y + size, x] = True
        page[y : y + size, x + size - 1] = True
        # Some content so the panel is not just a bare frame.
        page[y + 50 : y + 60, x + 50 : x + size - 50] = True
    return np.where(page, 0, 255).astype(np.uint8)


@pytest.fixture
def panels_page(store):
    page = _new_page(store, "panels_page.png")
    cv2.imwrite(str(store.path.parent / page.source_path), _two_panel_grid_image())
    return page


@pytest.fixture
def bubble_page_page(store):
    page = _new_page(store, "bubble_page.png")
    grey, _ = bubble_page()
    cv2.imwrite(str(store.path.parent / page.source_path), grey)
    return page


def test_stage_chain_is_declared_in_order():
    """D-11: STAGES declares import, panels, protected, zones, propose,
    snap, review, export in that order."""
    assert [stage.name for stage in STAGES] == [
        PipelineStage.IMPORT,
        PipelineStage.PANELS,
        PipelineStage.PROTECTED,
        PipelineStage.ZONES,
        PipelineStage.PROPOSE,
        PipelineStage.SNAP,
        PipelineStage.REVIEW,
        PipelineStage.EXPORT,
    ]


def test_only_import_has_a_runner():
    """D-11: exactly one Stage in the registry has a non-None runner —
    every later stage is a declared destination, not yet an implemented
    transition."""
    with_runner = [stage for stage in STAGES if stage.runner is not None]
    assert len(with_runner) == 1
    assert with_runner[0].name is PipelineStage.IMPORT


def test_every_stage_except_import_has_an_upstream():
    """D-10: the chain is fully linked. ``IMPORT.upstream`` is the only
    ``None`` in the registry; every other stage names its predecessor."""
    assert stage_for(PipelineStage.IMPORT).upstream is None
    for previous, current in zip(STAGES, STAGES[1:]):
        assert stage_for(current.name).upstream == previous.name


def test_run_import_advances_page_to_panels(store, page):
    """D-07: ``run_import`` moves a freshly added page's ``stage`` to
    ``PipelineStage.PANELS`` and persists the change — a page is never
    left sitting at ``import``."""
    run_import(store, page)

    assert page.stage is PipelineStage.PANELS
    assert store.page_by_id(page.id).stage is PipelineStage.PANELS


def test_stage_lookup_by_name():
    """``stage_for`` resolves a ``PipelineStage`` to its ``Stage`` entry
    and raises ``KeyError`` for a name the registry does not declare."""
    assert stage_for(PipelineStage.ZONES).name is PipelineStage.ZONES

    with pytest.raises(KeyError):
        stage_for("not-a-real-stage")  # type: ignore[arg-type]


def test_run_stage_refuses_a_stage_with_no_runner(store, page):
    """D-11: a declared-but-unimplemented stage refuses to run rather than
    silently doing nothing or falling through to a different stage."""
    with pytest.raises(StageNotImplementedError):
        run_stage(store, page, PipelineStage.ZONES)


def test_the_registry_never_advances_a_page_on_its_own(store, page):
    """D-10: the registry declares, it does not orchestrate. Calling
    ``run_stage`` for IMPORT twice leaves the page on ``panels`` and never
    reaches ``protected`` — nothing here chases ``next_stage`` on its own."""
    run_stage(store, page, PipelineStage.IMPORT)
    run_stage(store, page, PipelineStage.IMPORT)

    assert page.stage is PipelineStage.PANELS
    assert store.page_by_id(page.id).stage is PipelineStage.PANELS


# ---- run_panels (PAN-01) ---------------------------------------------------


def test_run_panels_persists_two_panels_in_reading_order(store, panels_page):
    run_panels(store, panels_page)

    panels = store.panels_for_page(panels_page.id)
    assert len(panels) == 2
    assert [panel.reading_order for panel in panels] == [0, 1]
    assert panels[0].x < panels[1].x, "ltr default: leftmost panel reads first"


def test_run_panels_polygon_is_four_box_corners_clockwise(store, panels_page):
    run_panels(store, panels_page)

    for panel in store.panels_for_page(panels_page.id):
        assert panel.polygon == [
            (panel.x, panel.y),
            (panel.x + panel.width, panel.y),
            (panel.x + panel.width, panel.y + panel.height),
            (panel.x, panel.y + panel.height),
        ]


def test_run_panels_is_idempotent_on_rerun(store, panels_page):
    run_panels(store, panels_page)
    run_panels(store, panels_page)

    assert len(store.panels_for_page(panels_page.id)) == 2


def test_run_panels_does_not_change_page_stage(store, panels_page):
    original_stage = panels_page.stage

    run_panels(store, panels_page)

    assert panels_page.stage is original_stage
    assert store.page_by_id(panels_page.id).stage is original_stage


def test_run_panels_raises_file_not_found_when_source_path_missing(store, page):
    """No file ever touches disk for the ``page`` fixture, so
    ``store.path.parent / page.source_path`` does not resolve — this must
    raise rather than silently persist zero panels."""
    with pytest.raises(FileNotFoundError):
        run_panels(store, page)

    assert store.panels_for_page(page.id) == []


# ---- run_protected (PROT-01, PROT-04) --------------------------------------


def test_run_protected_persists_one_bubble_mask(store, bubble_page_page):
    run_protected(store, bubble_page_page)

    masks = store.protected_for_page(bubble_page_page.id)
    assert len(masks) == 1
    mask = masks[0]
    assert mask.kind == ProtectedKind.BUBBLE
    assert mask.touched is False
    assert len(mask.polygon) >= 3
    assert mask.area > 0


def test_run_protected_zero_bubbles_is_not_an_error(store, page):
    """A splash page with no dialogue is a legitimate page, not a failure."""
    blank = np.full((200, 200), 255, dtype=np.uint8)
    cv2.imwrite(str(store.path.parent / page.source_path), blank)

    run_protected(store, page)

    assert store.protected_for_page(page.id) == []


def test_run_protected_is_idempotent_on_rerun(store, bubble_page_page):
    run_protected(store, bubble_page_page)
    run_protected(store, bubble_page_page)

    assert len(store.protected_for_page(bubble_page_page.id)) == 1


def test_run_protected_does_not_change_page_stage(store, bubble_page_page):
    original_stage = bubble_page_page.stage

    run_protected(store, bubble_page_page)

    assert bubble_page_page.stage is original_stage


def test_run_protected_raises_typed_error_and_preserves_prior_masks(
    store, bubble_page_page, monkeypatch
):
    run_protected(store, bubble_page_page)
    assert len(store.protected_for_page(bubble_page_page.id)) == 1

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("comiccolor.segmentation.bubbles.detect_bubbles", _boom)

    with pytest.raises(BubbleDetectionFailed):
        run_protected(store, bubble_page_page)

    # The previously persisted mask from the first, successful run survives
    # a subsequent failed run untouched.
    assert len(store.protected_for_page(bubble_page_page.id)) == 1


def test_run_protected_raises_file_not_found_when_source_path_missing(store, page):
    with pytest.raises(FileNotFoundError):
        run_protected(store, page)
