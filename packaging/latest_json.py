"""The file an installed app reads to learn that a new version is out.

    python packaging/latest_json.py <tag> <owner/repo> <folder>

Written by the release build (`.github/workflows/release.yml`) next to the
installers it describes: the version, and for each system the installer's URL,
size and sha256. The app fetches it from `releases/latest/download/latest.json`,
a plain download, which GitHub's API rate limit does not count.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

INSTALLERS = {"windows": "-setup.exe", "mac": ".dmg"}


def describe(tag: str, repo: str, folder: Path) -> dict:
    latest: dict = {"version": tag.removeprefix("v"), "notes": f"https://github.com/{repo}/releases/tag/{tag}"}
    for system, suffix in INSTALLERS.items():
        found = [path for path in folder.iterdir() if path.name.endswith(suffix)]
        if len(found) != 1:
            raise SystemExit(f"expected one *{suffix} in {folder}, found {len(found)}")
        installer = found[0]
        latest[system] = {
            "url": f"https://github.com/{repo}/releases/download/{tag}/{installer.name}",
            "size": installer.stat().st_size,
            "sha256": hashlib.sha256(installer.read_bytes()).hexdigest(),
        }
    return latest


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    tag, repo, folder = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    (folder / "latest.json").write_text(json.dumps(describe(tag, repo, folder), indent=2))
