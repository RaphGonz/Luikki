"""A project is a folder; a page is a folder inside it (SPEC 1–4).

    <project>/
      references/  palette.json   the book's, kept by `ReferenceStore` and `Session`
      project.json                which page is open, the leak gap, the export stack
      pages/0001/
        source.png                the artist's upload, copied in
        page.json                 everything decided about the page
        panel0.npy …              one zone map per panel, once the zones are cut
        lines-<extractor>.png     the extractor's output, so reopening skips it

Files rather than SQLite: the state is small, and a folder of JSON and images
is one anybody can open, read and copy. Rule 1 holds on disk as it does in
memory — `page.json` gives each zone a palette entry id, and an RGB value only
ever sits beside an entry.

Every edit saves before it returns (SPEC 4). Each file is written beside
itself and then swapped in, so a crash mid-save leaves the previous version
whole rather than half of each.

This is the persistence half of `Session` and reads its attributes directly:
what a page *is* is defined there, and this only puts it on disk and back.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import cv2
import numpy as np

from ..colour.segments import build_segments
from ..model.entities import PaletteEntry
from ..segmentation.preprocess import load_line_art

FORMAT = 1
PROJECT_FILE = "project.json"
PAGE_FILE = "page.json"
PAGES_DIR = "pages"


def _replace(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _write_json(path: Path, data: dict) -> None:
    _replace(path, json.dumps(data, indent=1).encode("utf-8"))


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def default_workdir() -> Path:
    """The project folder when `luikki serve` is given none.

    The user's data folder (`%LOCALAPPDATA%\\Luikki`, `~/Library/Application
    Support/Luikki`), not the temp folder the app used before: the system's
    disk cleanup empties that one, and every page with it. Local rather than
    roaming on Windows, because zone maps are not something to sync.

    A project still in the old place is copied across once, through a staging
    folder, so a copy cut short is never taken for the project.
    """
    from platformdirs import user_data_dir

    workdir = Path(user_data_dir("Luikki", appauthor=False))
    legacy = Path(tempfile.gettempdir()) / "luikki"
    if not workdir.exists() and legacy.is_dir():
        staging = workdir.with_name(workdir.name + ".part")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(legacy, staging)
        staging.rename(workdir)
    return workdir


def page_folder(workdir: Path, page_id: int) -> Path:
    return workdir / PAGES_DIR / f"{page_id:04d}"


def page_ids(workdir: Path) -> list[int]:
    root = workdir / PAGES_DIR
    if not root.is_dir():
        return []
    return sorted(
        int(folder.name)
        for folder in root.iterdir()
        if folder.name.isdigit() and (folder / PAGE_FILE).exists()
    )


def stage(record: dict) -> str:
    """How far a page has got: the last step it has run."""
    done = record["done"]
    if done["flats"]:
        return "flats"
    if done["zones"]:
        return "zones"
    if done["bubbles"]:
        return "bubbles"
    return "panels" if record["panels"] else "page"


def summaries(workdir: Path) -> dict[int, dict]:
    """Every page's name and stage, for the page list. Unreadable pages are left out."""
    found = {}
    for page_id in page_ids(workdir):
        record = _read_json(page_folder(workdir, page_id) / PAGE_FILE)
        if record is not None:
            found[page_id] = {"name": record["name"], "stage": stage(record)}
    return found


def new_page(workdir: Path, source: Path) -> tuple[int, Path]:
    """A fresh page folder holding a copy of `source`. Returns its id and the copy."""
    page_id = max(page_ids(workdir), default=0) + 1
    folder = page_folder(workdir, page_id)
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"source{Path(source).suffix.lower()}"
    shutil.copyfile(source, copy)
    return page_id, copy


def delete_page(workdir: Path, page_id: int) -> None:
    shutil.rmtree(page_folder(workdir, page_id), ignore_errors=True)


# -- the project ---------------------------------------------------------------


def save_project(session) -> None:
    _write_json(
        session.workdir / PROJECT_FILE,
        {
            "format": FORMAT,
            "current": session.page_id,
            "leak_gap": session.leak_gap,
            "granularity": session.granularity,
        },
    )


def load_project(session) -> int | None:
    """Put the book-scoped settings back. Returns the page that was open."""
    record = _read_json(session.workdir / PROJECT_FILE)
    if record is None:
        return None
    session.leak_gap = float(record.get("leak_gap", session.leak_gap))
    session.granularity = record.get("granularity", session.granularity)
    return record.get("current")


# -- one page ------------------------------------------------------------------


def _lines_file(session) -> str:
    # Named by extractor: a page reopened under `--extractor raw` must not be
    # segmented from the lines MangaLineExtraction drew last week.
    return f"lines-{session.extractor.name}.png"


def save_page(session, maps="all") -> dict:
    """Write the open page. `maps` is "all" or the panel orders whose zones changed.

    Zone maps are the only large files, so a snap rewrites `page.json` alone
    and a merge rewrites one panel's map. Arrays go first and `page.json` last,
    so the record never names a file that is not there yet.
    """
    folder = page_folder(session.workdir, session.page_id)

    if session._zones_done:
        orders = range(len(session.panels)) if maps == "all" else maps
        for order in orders:
            label_map = session.panels[order].label_map
            if label_map is not None:
                with open(folder / f"panel{order}.npy.tmp", "wb") as handle:
                    np.save(handle, label_map)
                os.replace(folder / f"panel{order}.npy.tmp", folder / f"panel{order}.npy")
    else:
        # Re-running an earlier step threw the zones away; the files go too.
        for stale in folder.glob("panel*.npy"):
            stale.unlink()

    lines = folder / _lines_file(session)
    if session._structural_lines is not None and not lines.exists():
        ok, encoded = cv2.imencode(".png", session._structural_lines)
        if ok:
            _replace(lines, encoded.tobytes())

    record = {
        "format": FORMAT,
        "uid": session.page_uid,
        "name": session.original_name,
        "source": session.source.name,
        "protected": [[list(point) for point in polygon] for polygon in session.protected],
        "panels": [
            {
                "polygon": [list(point) for point in panel.polygon],
                "x": panel.x,
                "y": panel.y,
                "width": panel.width,
                "height": panel.height,
                "orphans": panel.orphans,
                # zone label -> palette entry id. Never an RGB (rule 1).
                "assignments": {str(label): entry for label, entry in panel.assignments.items()},
            }
            for panel in session.panels
        ],
        # The page's own entries: one per zone, the colour the proposer gave it.
        "proposed": [
            {"id": entry.id, "rgb": list(entry.rgb), "label": entry.label, "revision": entry.revision}
            for entry in session._created_palette
        ],
        "auto_entry": [[panel, label, entry] for (panel, label), entry in session._auto_entry.items()],
        "flats_references": session._flats_references,
        "done": {
            "bubbles": session._bubbles_done,
            "zones": session._zones_done,
            "flats": session._flats_done,
        },
    }
    _write_json(folder / PAGE_FILE, record)
    return record


def open_page(session, page_id: int) -> None:
    """Load a page into `session`, replacing whatever was open.

    Raises `OSError` or `ValueError` for a page that cannot be read, leaving
    the session reset rather than half-loaded.
    """
    from .session import PanelState

    folder = page_folder(session.workdir, page_id)
    record = _read_json(folder / PAGE_FILE)
    if record is None:
        raise ValueError(f"page {page_id} has no readable {PAGE_FILE}")

    session.reset()
    try:
        source = folder / record["source"]
        line_mask, grey = load_line_art(source)
        done = record["done"]
        panels = [
            PanelState(
                order=order,
                x=panel["x"],
                y=panel["y"],
                width=panel["width"],
                height=panel["height"],
                polygon=[tuple(point) for point in panel["polygon"]],
                assignments={int(label): int(entry) for label, entry in panel["assignments"].items()},
                orphans=panel["orphans"],
            )
            for order, panel in enumerate(record["panels"])
        ]
        if done["zones"]:
            for order, panel in enumerate(panels):
                panel.label_map = np.load(folder / f"panel{order}.npy")
        lines = folder / _lines_file(session)
        structural_lines = cv2.imread(str(lines), cv2.IMREAD_GRAYSCALE) if lines.exists() else None
        created = [
            PaletteEntry(
                project_id=0,
                rgb=tuple(entry["rgb"]),
                label=entry["label"],
                id=int(entry["id"]),
                revision=int(entry["revision"]),
            )
            for entry in record["proposed"]
        ]
        auto_entry = {(int(p), int(l)): int(e) for p, l, e in record["auto_entry"]}
    except (KeyError, TypeError) as exc:
        session.reset()
        raise ValueError(f"page {page_id} is not a page this version can read: {exc}") from exc
    except (OSError, ValueError):
        session.reset()
        raise

    if not record.get("uid"):
        # A page saved before pages had one. Written at once, so it keeps the
        # same id however often it is opened before its next edit.
        record["uid"] = str(uuid.uuid4())
        _write_json(folder / PAGE_FILE, record)

    session.page_id = page_id
    session.page_uid = record["uid"]
    session.source = source
    session.original_name = record["name"]
    session.line_mask, session.grey = line_mask, grey
    session.height, session.width = line_mask.shape
    session._structural_lines = structural_lines
    session.protected = [[tuple(point) for point in polygon] for polygon in record["protected"]]
    session.panels = panels
    session._created_palette = created
    session._auto_entry = auto_entry
    session._flats_references = [int(ref) for ref in record.get("flats_references", [])]
    session._bubbles_done = bool(done["bubbles"])
    session._zones_done = bool(done["zones"])
    session._flats_done = bool(done["flats"])

    if session._flats_done:
        # A colour taken out of the palette while this page was closed. Done
        # to an open page, `delete_palette_entry` puts each zone back on its
        # proposed colour; a closed page gets the same when it opens.
        known = set(session.palette_by_id)
        for panel in panels:
            for label, entry in list(panel.assignments.items()):
                if entry not in known and (panel.order, label) in auto_entry:
                    panel.assignments[label] = auto_entry[(panel.order, label)]
        for panel in panels:
            segments = build_segments(panel.order, panel.label_map, panel.assignments, (panel.x, panel.y))
            for segment in segments:
                segment.snapped = segment.palette_entry_id != auto_entry.get(segment.key)
            session.segments.extend(segments)
