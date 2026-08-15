"""The thin runner: stage seams call into ``Store``, no orchestration.

D-10 requires this file to be individually triggerable per stage — it must
never walk the chain, run upstream stages implicitly, or advance a page past
its own gate. The obvious "helpful" change a later contributor would make
here — have ``run_stage`` chase ``next_stage`` and keep going — is exactly
the thing the design forbids: every stage stays individually triggerable and
individually inspectable (flatting-pipeline-spec.md §315).

Only ``run_import`` is implemented this phase (D-11); every other stage is
declared in ``stages.STAGES`` with ``runner=None`` and refuses to run via
``StageNotImplementedError`` until a later phase fills it in.

Imports only from ``..model`` at module level, never from ``.stages`` — the
registry (``stages.py``) imports ``run_import`` from this module at import
time, so a module-level import running the other way would be circular.
``run_stage`` resolves ``stage_for`` with a local import instead, which is
safe because by call time both modules are fully loaded.
"""

from __future__ import annotations

from ..model import Page, PipelineStage, Store


class StageNotImplementedError(RuntimeError):
    """Raised when a stage with no runner (D-11) is asked to run."""


def run_import(store: Store, page: Page) -> None:
    """Advance a freshly uploaded page past the import boundary.

    Import means "the file is on disk and the row exists" — there is
    nothing for the artist to review at that boundary yet, so the page
    auto-advances straight to ``panels`` rather than sitting at ``import``
    (01-UI-SPEC.md §1, D-11). This is the whole job: no segmentation, no
    validation beyond what already happened at upload time.
    """
    page.stage = PipelineStage.PANELS
    store.set_page_stage(page.id, PipelineStage.PANELS)


def run_stage(store: Store, page: Page, name: PipelineStage) -> None:
    """Run exactly the named stage. Never walks the chain (D-10).

    Looks the stage up in the registry, raises ``StageNotImplementedError``
    if it has no runner yet, and otherwise calls that runner and stops. Does
    not run upstream stages implicitly and does not advance the page past
    this stage's own gate — the registry declares, it does not orchestrate
    (flatting-pipeline-spec.md §315).
    """
    from .stages import stage_for  # local: avoids a module-level cycle with stages.py

    stage = stage_for(name)
    if stage.runner is None:
        raise StageNotImplementedError(f"stage {name.value!r} has no runner yet")
    stage.runner(store, page)
