"""HTTP routers for the phase-1 API surface.

Every submodule exposes a module-level ``router = APIRouter()``. Registering
all six here as (mostly empty) stubs up front is deliberate: it keeps
``app.py`` and ``schemas.py`` out of every later plan's ``files_modified``,
which is what lets plans 01-07 through 01-10 fill exactly one router module
each in parallel.
"""
