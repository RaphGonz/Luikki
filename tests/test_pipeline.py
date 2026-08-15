"""The stage-chain contract, as tests.

D-06 makes the pipeline a linear, page-scoped chain rather than a
per-panel state machine; D-07 says a freshly imported page starts life
already at ``panels``, not at some pre-import limbo stage; D-10 requires
the chain to be fully linked (every stage but the first has an
upstream); D-11 makes the registry declarative — one ``Stage`` entry per
``PipelineStage``, at most one non-``None`` runner, no dynamic dispatch.
These stubs are Wave 0 scaffolding: they name the guarantee before the
registry exists, so plan 01-04 fills in behaviour against an assertion
that was already written.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-04")
def test_stage_chain_is_declared_in_order():
    """D-11: STAGES declares import, panels, protected, zones, propose,
    snap, review, export in that order."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-04")
def test_only_import_has_a_runner():
    """D-11: exactly one Stage in the registry has a non-None runner —
    every later stage is a declared destination, not yet an implemented
    transition."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-04")
def test_every_stage_except_import_has_an_upstream():
    """D-10: the chain is fully linked. ``IMPORT.upstream`` is the only
    ``None`` in the registry; every other stage names its predecessor."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-04")
def test_run_import_advances_page_to_panels():
    """D-07: ``run_import`` moves a freshly added page's ``stage`` to
    ``PipelineStage.PANELS`` and persists the change — a page is never
    left sitting at ``import``."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-04")
def test_stage_lookup_by_name():
    """``stage_for`` resolves a ``PipelineStage`` to its ``Stage`` entry
    and raises ``KeyError`` for a name the registry does not declare."""
    ...
