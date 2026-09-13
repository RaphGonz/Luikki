"""The installed app's entry point: a server on a port of its own, a window on it.

No window opens here. A stand-in for `webview` takes the window's place and
asks the server for the page while it is "open", the way the real one would.
"""

from __future__ import annotations

import sys
import types

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from luikki import desktop  # noqa: E402
from luikki.desktop import LocalServer  # noqa: E402
from luikki.extract.passthrough import PassthroughExtractor  # noqa: E402
from luikki.web.app import create_app  # noqa: E402


def _app(tmp_path):
    return create_app(tmp_path / "work", extractor=PassthroughExtractor())


def test_an_app_without_a_console_writes_to_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(desktop.faulthandler, "enable", lambda stream: None)

    path = desktop.log_to_file(tmp_path)
    print("hello")
    sys.stdout.close()

    assert path.read_text(encoding="utf-8") == "hello\n"


def test_with_a_console_nothing_moves(tmp_path):
    assert desktop.log_to_file(tmp_path) is None
    assert not (tmp_path / "luikki.log").exists()


def test_two_servers_each_take_a_free_port_and_stop(tmp_path):
    servers = [LocalServer(_app(tmp_path)), LocalServer(_app(tmp_path))]
    assert servers[0].port != servers[1].port
    for server in servers:
        server.start()
    try:
        for server in servers:
            assert httpx.get(server.url + "api/state").status_code == 200
    finally:
        for server in servers:
            server.stop()

    with pytest.raises(httpx.ConnectError):
        httpx.get(servers[0].url + "api/state")


def test_the_window_opens_on_the_server_and_closing_it_stops_the_server(tmp_path, monkeypatch):
    seen = {}
    window = types.SimpleNamespace(destroy=lambda: None)

    def create_window(title, url, **options):
        seen["url"] = url
        return window

    def start(**options):
        # The window is open for as long as this runs.
        seen["answer"] = httpx.get(seen["url"] + "api/state").status_code
        seen["options"] = options

    fake = types.SimpleNamespace(settings={}, create_window=create_window, start=start)
    monkeypatch.setitem(sys.modules, "webview", fake)
    app = _app(tmp_path)

    desktop.run(app)

    # An update closes this window for its installer (`web/update.py`).
    assert app.state.updater.quit == window.destroy
    assert seen["url"].startswith("http://127.0.0.1:")
    assert seen["answer"] == 200
    # The PSD export is a download, which pywebview cancels unless told otherwise.
    assert fake.settings["ALLOW_DOWNLOADS"] is True
    assert seen["options"]["private_mode"] is False
    with pytest.raises(httpx.ConnectError):
        httpx.get(seen["url"] + "api/state")
