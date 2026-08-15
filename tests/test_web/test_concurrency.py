"""The two thread-affinity rules ``web/deps.py`` documents, enforced.

``TestClient`` is sequential by construction — it drives the app one
request at a time — so the rest of this package is structurally blind to
every failure mode that needs two requests in flight at once. That is not
a gap in those tests; it is why this module exists separately and drives
the app through ``httpx.ASGITransport`` instead.

Both tests here fail against the pre-fix code:

- ``test_concurrent_store_requests_do_not_raise`` raised
  ``sqlite3.ProgrammingError`` ("SQLite objects created in a thread can
  only be used in that same thread") on its first round, because FastAPI
  resolves a sync generator dependency's ``__enter__``, the endpoint, and
  its ``__exit__`` as three separate ``run_in_threadpool`` calls and anyio
  does not pin them to one worker.
- ``test_no_store_dependent_route_is_async`` is the standing guard for the
  companion rule: the first ``async def`` handler added over ``get_store``
  would silently move blocking sqlite calls onto the event loop.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest


CONCURRENT_REQUESTS = 8
ROUNDS = 3


@pytest.fixture
def asgi_app(project_dir):
    """The real app with a real project open, for transport-level driving.

    Deliberately not the ``client`` fixture: that one yields a
    ``TestClient``, and a ``TestClient`` cannot express concurrency.
    """
    from comiccolor.model import Project, Store
    from comiccolor.web.app import create_app
    from comiccolor.web.appconfig import PROJECT_DB_NAME
    from comiccolor.web.deps import set_current_project

    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.add_project(Project(name=project_dir.name))

    app = create_app()
    set_current_project(app, project_dir)
    return app


def test_concurrent_store_requests_do_not_raise(asgi_app):
    """Concurrent store-backed requests all succeed (CR-01).

    The frontend guarantees this shape: ``sidebar.refresh`` fires
    ``Promise.all([projects.current(), volumes.list()])`` on every load,
    and the sidebar boots in parallel with whichever view the router
    mounts. Several rounds are run because which worker anyio hands out is
    a scheduling detail — one round can pass by luck, a handful cannot.
    """
    import httpx

    async def hammer() -> list[int]:
        transport = httpx.ASGITransport(app=asgi_app)
        statuses: list[int] = []
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            for _ in range(ROUNDS):
                responses = await asyncio.gather(
                    *(
                        client.get("/api/palette")
                        for _ in range(CONCURRENT_REQUESTS)
                    )
                )
                statuses += [r.status_code for r in responses]
        return statuses

    statuses = asyncio.run(hammer())

    assert len(statuses) == ROUNDS * CONCURRENT_REQUESTS
    assert set(statuses) == {200}


def test_store_is_usable_from_a_different_thread_than_it_was_built_on():
    """The narrow mechanic CR-01 turns on, asserted directly.

    The end-to-end test above is the real proof, but it depends on anyio's
    scheduler choosing to move work between workers. This one removes that
    dependence: it moves a ``Store`` across threads by hand, which is
    exactly what FastAPI's three-separate-``run_in_threadpool`` resolution
    does within a single request.
    """
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from comiccolor.model import Project, Store

    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "project.db")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(store.add_project, Project(name="Kaito")).result()
            with ThreadPoolExecutor(max_workers=1) as pool:
                project = pool.submit(store.the_project).result()
            assert project is not None
            assert project.name == "Kaito"
        finally:
            store.close()


def test_no_store_dependent_route_is_async(asgi_app):
    """No route depending on ``get_store`` may be a coroutine (WR-01).

    The rule was written down exactly once, buried in one handler's
    docstring, where nobody adding a route to another module would find
    it. This walks the real dependency graph instead.
    """
    from comiccolor.web.deps import get_store

    def all_routes(router):
        """Flatten nested routers.

        ``include_router`` wraps each router in an ``_IncludedRouter``,
        which holds the real ``APIRoute`` objects on ``original_router``
        rather than exposing them as its own ``routes``. A flat scan of
        ``app.routes`` therefore finds only ``/api/health`` and passes
        vacuously — hence this walk, and the ``checked > 0`` guard below.
        """
        for route in getattr(router, "routes", []):
            yield route
            nested = getattr(route, "original_router", None)
            if nested is not None:
                yield from all_routes(nested)
            elif hasattr(route, "routes"):
                yield from all_routes(route)

    def depends_on_store(dependant, seen=None) -> bool:
        seen = seen if seen is not None else set()
        if id(dependant) in seen:
            return False
        seen.add(id(dependant))
        if dependant.call is get_store:
            return True
        return any(depends_on_store(sub, seen) for sub in dependant.dependencies)

    checked = 0
    for route in all_routes(asgi_app):
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        if not depends_on_store(dependant):
            continue
        checked += 1
        assert not inspect.iscoroutinefunction(route.endpoint), (
            f"{route.endpoint.__qualname__} depends on get_store but is"
            " async def — see web/deps.py's module docstring"
        )

    # Guards against the walk silently matching nothing (a refactor that
    # renames or wraps get_store would otherwise make this test vacuous).
    assert checked > 0
