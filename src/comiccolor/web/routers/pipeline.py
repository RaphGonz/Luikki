"""Pipeline stage routes.

PROJ-02/PROJ-04: exposes the declarative ``comiccolor.pipeline`` registry
(``STAGES``) over HTTP for the page detail stage strip. Registered as an
empty stub by plan 01-06; filled by plan 01-08 alongside ``volume.py`` and
``page.py``.
"""

from fastapi import APIRouter

router = APIRouter()
