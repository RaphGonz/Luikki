"""Pipeline stage routes.

PROJ-04/D-11: exposes the declarative ``comiccolor.pipeline`` registry
(``STAGES``) over HTTP so the frontend never hardcodes the eight-stage list
or restates which stages have a runner (RESEARCH.md § Architecture Patterns
Pattern 5). This is static registry metadata, not project data — the route
must not depend on ``get_store``/``get_project`` and must answer with no
project open.

It reports ``has_runner`` truthfully. 01-UI-SPEC.md §1 separately forbids
the *UI* from rendering that distinction in Phase 1 — both not-yet-reached
variants must look identical, because the artist should never see an
internal "not implemented" state. The API tells the truth; the UI chooses
what to show.
"""

from __future__ import annotations

from fastapi import APIRouter

from ...pipeline import STAGES
from ..schemas import StageResponse

router = APIRouter()


@router.get("/stages")
def list_stages() -> list[StageResponse]:
    return [
        StageResponse(
            name=stage.name,
            display_name=stage.display_name,
            upstream=stage.upstream,
            produces=stage.produces,
            has_runner=stage.runner is not None,
        )
        for stage in STAGES
    ]
