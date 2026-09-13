"""The installed app learns of a new version and installs it on a press."""

from __future__ import annotations

import hashlib
import threading

import pytest

httpx = pytest.importorskip("httpx")

from luikki.web.progress import Progress  # noqa: E402
from luikki.web.session import StepError  # noqa: E402
from luikki.web.update import Updater, version_key  # noqa: E402

INSTALLER = b"the published installer" * 1000
LATEST_URL = "https://releases.test/latest.json"


def _latest(version: str = "0.2.0") -> dict:
    return {
        "version": version,
        "notes": "https://releases.test/notes",
        "windows": {
            "url": "https://releases.test/Luikki-0.2.0-setup.exe",
            "size": len(INSTALLER),
            "sha256": hashlib.sha256(INSTALLER).hexdigest(),
        },
        "mac": {"url": "https://releases.test/Luikki-0.2.0-mac-arm64.dmg", "size": 1, "sha256": "0" * 64},
    }


def _updater(tmp_path, latest: dict | None = None, served: bytes = INSTALLER, **options) -> Updater:
    def answer(request):
        if request.url.path.endswith("latest.json"):
            return httpx.Response(200, json=latest or _latest())
        return httpx.Response(200, content=served)

    options.setdefault("frozen", True)
    options.setdefault("system", "windows")
    return Updater(
        current="0.1.0",
        url=LATEST_URL,
        client=httpx.Client(transport=httpx.MockTransport(answer)),
        folder=tmp_path,
        **options,
    )


def test_versions_compare_as_numbers():
    assert version_key("0.10.0") > version_key("0.9.1")


def test_a_source_checkout_offers_nothing(tmp_path):
    assert _updater(tmp_path, frozen=False).check() == {"available": False}


def test_the_running_version_offers_nothing(tmp_path):
    assert _updater(tmp_path, latest=_latest("0.1.0")).check() == {"available": False}


def test_no_connection_offers_nothing(tmp_path):
    def offline(request):
        raise httpx.ConnectError("offline")

    updater = Updater(
        current="0.1.0",
        url=LATEST_URL,
        client=httpx.Client(transport=httpx.MockTransport(offline)),
        frozen=True,
        system="windows",
    )
    assert updater.check() == {"available": False}


def test_windows_installs_only_from_the_window(tmp_path):
    updater = _updater(tmp_path)
    assert updater.check() == {"available": True, "version": "0.2.0", "install": False}
    updater.quit = lambda: None
    assert updater.check()["install"] is True


def test_the_press_downloads_launches_and_closes(tmp_path):
    launched, closed = [], threading.Event()
    updater = _updater(tmp_path, launch=launched.append)
    updater.quit = closed.set

    updater.install(Progress())

    assert [path.name for path in launched] == ["Luikki-0.2.0-setup.exe"]
    assert launched[0].read_bytes() == INSTALLER
    assert closed.wait(5)


def test_a_download_that_is_not_the_published_installer_is_never_run(tmp_path):
    launched = []
    updater = _updater(tmp_path, served=b"something else", launch=launched.append)
    updater.quit = lambda: None

    with pytest.raises(StepError) as refused:
        updater.install(Progress())

    assert refused.value.code == "update_corrupt"
    assert launched == []
    assert list(tmp_path.iterdir()) == []


def test_the_mac_press_opens_the_disk_image_in_the_browser(tmp_path):
    opened = []
    updater = _updater(tmp_path, system="mac", open_url=opened.append)
    updater.quit = lambda: None

    updater.install(Progress())

    assert opened == ["https://releases.test/Luikki-0.2.0-mac-arm64.dmg"]


def test_pressing_with_nothing_newer_is_refused(tmp_path):
    with pytest.raises(StepError) as refused:
        _updater(tmp_path, latest=_latest("0.1.0")).install(Progress())
    assert refused.value.code == "update_none"


def test_the_header_button_reaches_the_updater(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from luikki.extract.passthrough import PassthroughExtractor
    from luikki.web.app import create_app

    opened = []
    updater = _updater(tmp_path / "update", system="mac", open_url=opened.append)
    client = TestClient(create_app(tmp_path / "work", extractor=PassthroughExtractor(), updater=updater))

    assert client.get("/api/update").json() == {"available": True, "version": "0.2.0", "install": False}
    assert client.post("/api/update").status_code == 200
    assert opened == [_latest()["mac"]["url"]]
