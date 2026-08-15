"""Project-folder layout constants and the recent-projects convenience index.

No new dependency added for this (RESEARCH.md § Supporting explicitly
recommends against ``platformdirs`` for a Windows-only v1) — a plain
``Path.home()``-anchored config directory is enough for one machine, one
artist.

D-04's folder-per-project layout (``project.db`` plus ``pages/``,
``references/pending/`` and ``label_maps/`` beside it) is what makes a
project portable by copying the folder. The recent-projects list is a
convenience index only — ``read_recents`` silently drops any entry whose
folder has moved or vanished, and nothing here ever treats the index as
authoritative over the folder itself.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_DB_NAME = "project.db"
PAGES_DIR = "pages"
REFERENCES_DIR = "references"
PENDING_DIR = "references/pending"
LABEL_MAPS_DIR = "label_maps"
CONFIG_DIR = Path.home() / ".comiccolor"
RECENTS_PATH = CONFIG_DIR / "recent.json"
DEFAULT_WORKSPACE = Path.home() / "ComicColor"
MAX_RECENTS = 10


@dataclass(frozen=True)
class RecentProject:
    name: str
    path: str
    opened_at: str


def create_project_folder(parent: Path, name: str) -> Path:
    """Lay out a new project's folder (D-04).

    Raises ``FileExistsError`` if ``project.db`` already exists at the
    target path — this function never overwrites an existing project;
    ``Store``'s own single-row ``project`` table constraint is the second,
    structural line of defence against a duplicate project.
    """
    project_dir = parent / name
    if (project_dir / PROJECT_DB_NAME).exists():
        raise FileExistsError(f"a project already exists at {project_dir}")
    (project_dir / PAGES_DIR).mkdir(parents=True, exist_ok=True)
    (project_dir / PENDING_DIR).mkdir(parents=True, exist_ok=True)
    (project_dir / LABEL_MAPS_DIR).mkdir(parents=True, exist_ok=True)
    return project_dir


def is_project_folder(path: Path) -> bool:
    """True if ``path`` is a directory containing ``project.db``.

    A freshly created folder from :func:`create_project_folder` is not yet
    a project by this definition — it becomes one only once ``Store``
    creates ``project.db`` inside it.
    """
    return path.is_dir() and (path / PROJECT_DB_NAME).is_file()


def read_recents() -> list[RecentProject]:
    """The recent-projects list, tolerant of a missing or corrupt file.

    D-04 is explicit that this index is a convenience only and must never
    be authoritative over the folder — every entry whose folder no longer
    passes :func:`is_project_folder` is silently dropped here, which is
    what enforces that rule structurally rather than by review.
    """
    if not RECENTS_PATH.exists():
        return []
    try:
        raw = json.loads(RECENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = [RecentProject(**item) for item in raw if _looks_like_recent(item)]
    return [entry for entry in entries if is_project_folder(Path(entry.path))]


def _looks_like_recent(item: object) -> bool:
    return isinstance(item, dict) and {"name", "path", "opened_at"} <= item.keys()


def record_recent(path: Path, name: str) -> None:
    """Upsert ``path`` to the head of the recent-projects list.

    Deduped by resolved path, capped at :data:`MAX_RECENTS`, written
    atomically (temp file in the same directory, then replaced) so a crash
    mid-write never leaves ``recent.json`` truncated or corrupt.
    """
    from datetime import datetime, timezone

    resolved = str(path.resolve())
    existing = [e for e in read_recents() if str(Path(e.path).resolve()) != resolved]
    entries = [
        RecentProject(
            name=name, path=resolved, opened_at=datetime.now(timezone.utc).isoformat()
        )
    ] + existing
    entries = entries[:MAX_RECENTS]

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = RECENTS_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps([asdict(e) for e in entries], indent=2), encoding="utf-8"
    )
    os.replace(tmp_path, RECENTS_PATH)


def forget_recent(path: Path) -> None:
    """Drop ``path`` from the recent-projects list, if present."""
    resolved = str(path.resolve())
    remaining = [e for e in read_recents() if str(Path(e.path).resolve()) != resolved]

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = RECENTS_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps([asdict(e) for e in remaining], indent=2), encoding="utf-8"
    )
    os.replace(tmp_path, RECENTS_PATH)
