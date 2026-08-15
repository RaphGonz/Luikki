"""Project lifecycle routes.

PROJ-01 (create/open/list a project) and PROJ-05 (durable, portable project
state — nothing here writes to the wrong database or loses an edit on a
refresh). Registered as an empty stub by plan 01-06; filled by plan 01-07.
"""

from fastapi import APIRouter

router = APIRouter()
