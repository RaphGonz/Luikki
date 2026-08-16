"""Regression tests for this phase's geometry bounds and router mounting.

These bounds are the mitigation for the two Denial-of-Service rows in
02-RESEARCH.md's Security Domain table: every polygon body eventually
reaches ``cv2.fillPoly``, which allocates and writes based on the numbers a
client supplies. Pinning the bound here — not just "large is bad" but the
exact boundary value — is what keeps a future edit to ``schemas.py`` from
silently widening it back open.

The route-level test pins T-2-04: both new routers must stay mounted under
``/api``, the prefix Phase 1's ``_reject_foreign_origins`` middleware scopes
to. A router later mounted at a different prefix would slip state-changing
routes past that check entirely.
"""

from __future__ import annotations

import pydantic
import pytest
from pydantic import TypeAdapter

from comiccolor.web.schemas import (
    MAX_PAGE_PIXEL,
    Polygon,
    ProtectedMaskCreateRequest,
    VertexUpdateRequest,
)

_polygon_adapter: TypeAdapter[list] = TypeAdapter(Polygon)


def _polygon(n: int) -> list[list[int]]:
    """``n`` distinct, in-range vertices, cheap to build for any ``n``."""
    return [[i % MAX_PAGE_PIXEL, 0] for i in range(n)]


# ---- Vertex count bound (T-2-01) -----------------------------------------


def test_a_513_vertex_polygon_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _polygon_adapter.validate_python(_polygon(513))


def test_a_512_vertex_polygon_is_accepted():
    validated = _polygon_adapter.validate_python(_polygon(512))
    assert len(validated) == 512


def test_a_2_vertex_polygon_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _polygon_adapter.validate_python([[0, 0], [1, 0]])


def test_a_3_vertex_polygon_is_accepted():
    validated = _polygon_adapter.validate_python([[0, 0], [1, 0], [1, 1]])
    assert len(validated) == 3


# ---- Coordinate range bound (T-2-01) --------------------------------------


def test_a_negative_coordinate_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _polygon_adapter.validate_python([[-1, 0], [1, 0], [1, 1]])


def test_a_coordinate_above_max_page_pixel_is_rejected():
    with pytest.raises(pydantic.ValidationError):
        _polygon_adapter.validate_python(
            [[MAX_PAGE_PIXEL + 1, 0], [1, 0], [1, 1]]
        )


def test_vertex_update_request_rejects_a_negative_coordinate():
    with pytest.raises(pydantic.ValidationError):
        VertexUpdateRequest(x=-1, y=0)


# ---- ProtectedKind must be the real enum (T-2-20) -------------------------


def test_protected_mask_create_request_rejects_an_unknown_kind():
    with pytest.raises(pydantic.ValidationError):
        ProtectedMaskCreateRequest(kind="not-a-kind", polygon=[[0, 0], [1, 0], [1, 1]])


# ---- Router mounting (T-2-04) ----------------------------------------------


def _routes_contributed_by(router) -> list[str]:
    """Every path this specific router (or a router nested inside it)
    contributes to a live app, found by walking ``app.routes``.

    ``include_router`` wraps each router in an ``_IncludedRouter``, which
    holds the real ``APIRoute`` objects on ``original_router`` rather than
    exposing them as its own ``routes`` — a flat scan of ``app.routes``
    would find only the top-level stub entries. See
    ``test_concurrency.py::test_no_store_dependent_route_is_async`` for the
    same walk against a different question.
    """
    from comiccolor.web.app import create_app

    def all_routes(node):
        for route in getattr(node, "routes", []):
            yield route
            nested = getattr(route, "original_router", None)
            if nested is not None:
                yield from all_routes(nested)
            elif hasattr(route, "routes"):
                yield from all_routes(route)

    app = create_app()
    paths: list[str] = []
    for top in app.routes:
        if getattr(top, "original_router", None) is router:
            paths.extend(r.path for r in all_routes(top) if hasattr(r, "path"))
    return paths


def test_every_panel_router_path_starts_with_api():
    from comiccolor.web.routers import panel

    for path in _routes_contributed_by(panel.router):
        assert path.startswith("/api"), path


def test_every_protected_router_path_starts_with_api():
    from comiccolor.web.routers import protected

    for path in _routes_contributed_by(protected.router):
        assert path.startswith("/api"), path
