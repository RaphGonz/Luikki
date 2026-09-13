"""A new version of the installed app: offered at launch, installed on a press.

The release build publishes `latest.json` next to the installers
(`packaging/latest_json.py`). The app reads it once per launch, as a plain
download from GitHub: it wakes no GPU, and GitHub's API limit does not count
it. Nothing is installed until the artist presses.

On Windows, in the app's window, the press downloads the installer, checks its
sha256 against `latest.json`, starts it silently and closes the window; the
installer replaces the program and opens it again (`packaging/luikki.iss`).
Anywhere else — the Mac until the app is notarised (B6), or `luikki serve` in a
browser — the press opens the download in the browser. A source checkout
offers nothing: its version is whatever was checked out, not a release.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .. import __version__
from .progress import Progress
from .session import StepError

LATEST_URL = "https://github.com/RaphGonz/Luikki/releases/latest/download/latest.json"
CHECK_SECONDS = 5.0
# Between two reads of the download, not for the whole file.
DOWNLOAD_SECONDS = 60.0
# Long enough for the answer to reach the window before it closes.
QUIT_SECONDS = 1.0
SYSTEMS = ("windows", "mac")


def version_key(version: str) -> tuple[int, ...]:
    """`0.10.0` after `0.9.1`: versions compare as numbers, not as text."""
    return tuple(int(part) for part in re.findall(r"\d+", version))


def current_system() -> str | None:
    return {"win32": "windows", "darwin": "mac"}.get(sys.platform)


class Updater:
    def __init__(
        self,
        current: str = __version__,
        url: str | None = None,
        client: Any = None,
        frozen: bool | None = None,
        system: str | None = None,
        launch: Callable[[Path], None] | None = None,
        open_url: Callable[[str], Any] = webbrowser.open,
        folder: Path | None = None,
    ):
        self.current = current
        self.url = url or os.environ.get("LUIKKI_UPDATE_URL") or LATEST_URL
        self.client = client
        self.frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self.system = current_system() if system is None else system
        self.launch = launch or _launch_installer
        self.open_url = open_url
        self.folder = folder or Path(tempfile.gettempdir()) / "Luikki-update"
        # Closes the window, set by `desktop.run`. Without a window there is
        # no app for the installer to replace and reopen.
        self.quit: Callable[[], None] | None = None
        self._latest: dict | None = None
        self._guard = threading.Lock()

    def check(self) -> dict:
        """What the header offers: nothing, or a version and whether pressing installs it."""
        if self._newer() is None:
            return {"available": False}
        return {"available": True, "version": self._latest["version"], "install": self._installs}

    def install(self, progress: Progress) -> None:
        entry = self._newer()
        if entry is None:
            raise StepError("update_none")
        if not self._installs:
            self.open_url(entry["url"])
            return
        installer = self._download(entry, progress)
        self.launch(installer)
        threading.Timer(QUIT_SECONDS, self.quit).start()

    @property
    def _installs(self) -> bool:
        return self.system == "windows" and self.quit is not None

    def _newer(self) -> dict | None:
        latest = self._fetch()
        if latest is None or version_key(latest["version"]) <= version_key(self.current):
            return None
        return latest.get(self.system)

    def _fetch(self) -> dict | None:
        """`latest.json`, read once per launch. A read that failed is tried again."""
        if not self.frozen:
            return None
        import httpx

        with self._guard:
            if self._latest is None:
                client = self.client or httpx.Client()
                try:
                    response = client.get(self.url, timeout=CHECK_SECONDS, follow_redirects=True)
                    response.raise_for_status()
                    latest = response.json()
                except (httpx.HTTPError, ValueError):
                    return None
                if _readable(latest):
                    self._latest = latest
            return self._latest

    def _download(self, entry: dict, progress: Progress) -> Path:
        import httpx

        self.folder.mkdir(parents=True, exist_ok=True)
        installer = self.folder / Path(urlparse(entry["url"]).path).name
        partial = installer.with_name(installer.name + ".part")
        digest = hashlib.sha256()
        client = self.client or httpx.Client()
        try:
            with (
                progress.run(entry.get("size") or 1) as tracked,
                partial.open("wb") as handle,
                client.stream("GET", entry["url"], timeout=DOWNLOAD_SECONDS, follow_redirects=True) as response,
            ):
                response.raise_for_status()
                for block in response.iter_bytes(1 << 20):
                    handle.write(block)
                    digest.update(block)
                    tracked.tick(len(block))
        except httpx.HTTPError as exc:
            partial.unlink(missing_ok=True)
            raise StepError("update_download", status=502) from exc
        # The file is run next: one that is not the published installer never is.
        if digest.hexdigest() != entry["sha256"]:
            partial.unlink()
            raise StepError("update_corrupt", status=502)
        partial.replace(installer)
        return installer


def _readable(latest: Any) -> bool:
    return (
        isinstance(latest, dict)
        and isinstance(latest.get("version"), str)
        and all(
            isinstance(latest[system], dict)
            and isinstance(latest[system].get("url"), str)
            and isinstance(latest[system].get("sha256"), str)
            for system in SYSTEMS
            if system in latest
        )
    )


def _launch_installer(installer: Path) -> None:
    """Start the installer on its own, so it outlives the app it replaces."""
    subprocess.Popen(
        [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
