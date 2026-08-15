"""The stage-chain contract, as tests.

D-06 makes the pipeline a linear, page-scoped chain rather than a
per-panel state machine; D-07 says a freshly imported page starts life
already at ``panels``, not at some pre-import limbo stage; D-10 requires
the chain to be fully linked (every stage but the first has an
upstream); D-11 makes the registry declarative — one ``Stage`` entry per
``PipelineStage``, at most one non-``None`` runner, no dynamic dispatch.
"""

import pytest

from comiccolor.model import Page, PipelineStage, Project, Store, Volume
from comiccolor.pipeline import STAGES, StageNotImplementedError, run_import, run_stage, stage_for


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as s:
        yield s


@pytest.fixture
def page(store):
    project = store.add_project(Project(name="Kaito"))
    volume = store.add_volume(Volume(project_id=project.id, name="v1"))
    return store.add_page(Page(volume_id=volume.id, source_path="p1.png", index=0))


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
