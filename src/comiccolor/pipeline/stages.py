"""The declarative eight-stage pipeline registry.

Four things this module is load-bearing for:

1. **Forward-only, one confirmation gate per page (D-06, D-07).** There is
   deliberately no "stale downstream" concept anywhere in the system. Once a
   stage is confirmed the model never permits stale state to exist — nothing
   here recomputes or invalidates a later stage just because an earlier one
   changed.

2. **This is a declaration, not an orchestrator (D-10).** ``STAGES`` names
   every stage and its relationships; it must never advance a page past a
   gate on its own. Every stage stays individually triggerable and
   individually inspectable — flatting-pipeline-spec.md §315.

3. **Phase 1 declares all eight, implements only import (D-11).** Later
   phases fill in the remaining seven runners against the contract declared
   here. Some of the declared shapes — ``produces``, in particular — are
   expected to need amending once Phases 3-5 build against them. This
   declaration is not frozen.

4. **``upstream`` is what a future Go-Back flow (D-08) walks** to compute
   the concrete "discards N edits on M panels" sentence 01-UI-SPEC.md §3
   requires. Phase 1 ships no Go-Back entry point — no stage past Import
   exists yet to go back from — but the chain it will walk is already
   linked. 01-UI-SPEC.md is explicit that a vague sentence must never ship
   in place of a computed one, which is why the link exists now rather than
   being bolted on when Go-Back is finally built.

Deliberately absent: a per-panel run-tracking table, a status field per
panel, or any per-panel run tracking of any kind. D-07 locked stage
tracking to a single ``page.stage`` value; RESEARCH.md § Anti-Patterns rules
the heavier per-panel design out for this phase as premature scope no
requirement asks for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..model.entities import Page, PipelineStage
from ..model.store import Store
from .runner import run_import

# A stage runner mutates the page/store to advance past its own gate. It
# never walks the chain — see the module docstring's point 2 (D-10).
StageRunner = Callable[[Store, Page], None]


@dataclass(frozen=True)
class Stage:
    """One entry in the declared chain.

    ``runner`` is ``None`` for every stage that has no implementation yet
    (D-11) — a declared-but-unimplemented stage is a normal, expected state
    this phase, not an error condition.
    """

    name: PipelineStage
    display_name: str
    upstream: PipelineStage | None
    produces: str  # short human phrase naming the artefact this stage yields
    runner: StageRunner | None


# Display names taken from 01-UI-SPEC.md §1 — the eight segment names as the
# artist sees them in the stage strip.
STAGES: list[Stage] = [
    Stage(
        name=PipelineStage.IMPORT,
        display_name="Import",
        upstream=None,
        produces="a page row with source_path set",
        runner=run_import,
    ),
    Stage(
        name=PipelineStage.PANELS,
        display_name="Panels",
        upstream=PipelineStage.IMPORT,
        produces="panel polygons",
        runner=None,
    ),
    Stage(
        name=PipelineStage.PROTECTED,
        display_name="Protected",
        upstream=PipelineStage.PANELS,
        produces="protected masks (bubbles, SFX, borders, text)",
        runner=None,
    ),
    Stage(
        name=PipelineStage.ZONES,
        display_name="Zones",
        upstream=PipelineStage.PROTECTED,
        produces="a label map per panel",
        runner=None,
    ),
    Stage(
        name=PipelineStage.PROPOSE,
        display_name="Propose",
        upstream=PipelineStage.ZONES,
        produces="Cobra colour proposals per panel",
        runner=None,
    ),
    Stage(
        name=PipelineStage.SNAP,
        display_name="Snap",
        upstream=PipelineStage.PROPOSE,
        produces="CIELAB-snapped palette assignments per region",
        runner=None,
    ),
    Stage(
        name=PipelineStage.REVIEW,
        display_name="Review",
        upstream=PipelineStage.SNAP,
        produces="artist-confirmed colour corrections",
        runner=None,
    ),
    Stage(
        name=PipelineStage.EXPORT,
        display_name="Export",
        upstream=PipelineStage.REVIEW,
        produces="a layered PSD",
        runner=None,
    ),
]

_BY_NAME: dict[PipelineStage, Stage] = {stage.name: stage for stage in STAGES}


def stage_for(name: PipelineStage) -> Stage:
    """Look up a declared stage by name. Raises ``KeyError`` if undeclared."""
    return _BY_NAME[name]


def next_stage(name: PipelineStage) -> PipelineStage | None:
    """The stage after ``name`` in the chain, or ``None`` at EXPORT."""
    index = STAGES.index(stage_for(name))
    if index + 1 < len(STAGES):
        return STAGES[index + 1].name
    return None
