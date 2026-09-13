"""The installed app: the local server in a thread, a native window on it (B4).

`luikki serve` and a browser tab is the same app. Here uvicorn listens on
127.0.0.1, on a port the system picks, so another program on 8000 or a second
copy never stops it from starting, and the window is the only thing that needs
the address. Closing the window stops the server: nothing stays running.

pywebview draws the window with the system's own web engine (WebView2 on
Windows, WebKit on the Mac), so the page is the one `static/` serves, unchanged.
"""

from __future__ import annotations

import faulthandler
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

# Long enough for a slow first start, short enough that a server that cannot
# start says so instead of leaving a blank window.
START_SECONDS = 30.0
# The log is started over past this size, keeping one previous file.
LOG_BYTES = 5_000_000


def log_to_file(folder: Path | None = None) -> Path | None:
    """Give an app built without a console somewhere to write.

    Such an app starts with `sys.stdout` and `sys.stderr` set to None, and the
    first thing that writes takes it down before the window opens — uvicorn's
    log setup asks `sys.stdout.isatty()`. Both go to one file instead, which is
    also the file a tester sends when something breaks. None when there is a
    console, and nothing changes.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    if folder is None:
        from platformdirs import user_log_dir

        folder = Path(user_log_dir("Luikki", appauthor=False))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "luikki.log"
    if path.exists() and path.stat().st_size > LOG_BYTES:
        path.replace(path.with_name(path.name + ".1"))
    stream = path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream
    # A crash inside the web engine or onnxruntime leaves a trace here too.
    faulthandler.enable(stream)
    return path


class LocalServer:
    """uvicorn on a free port of 127.0.0.1, in a daemon thread."""

    def __init__(self, app):
        # Bound here and handed to uvicorn, so nothing can take the port
        # between choosing it and listening on it.
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(("127.0.0.1", 0))
        self.port = self._socket.getsockname()[1]
        self._server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._socket]}, daemon=True, name="luikki-server"
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self, timeout: float = START_SECONDS) -> None:
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > deadline:
                self.stop()
                raise RuntimeError("the local server did not start")
            time.sleep(0.05)

    def stop(self, timeout: float = 5.0) -> None:
        """Ask uvicorn to finish. A step still waiting on the GPU server is not
        waited for past `timeout`: the thread is a daemon and ends with the app."""
        self._server.should_exit = True
        if self._thread.is_alive():
            self._thread.join(timeout)
        self._socket.close()


def run(app, debug: bool = False) -> None:
    """Serve `app` and show it in a window until the window is closed."""
    import webview
    from platformdirs import user_data_dir

    server = LocalServer(app)
    server.start()
    # The PSD export is a download. Allowed, it opens the system's Save dialog;
    # pywebview's default cancels it without a word.
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window("Luikki", server.url, maximized=True, text_select=True)
    updater = getattr(app.state, "updater", None)
    if updater is not None:
        # An update replaces this very program: the app closes for its installer.
        updater.quit = window.destroy
    try:
        webview.start(
            debug=debug,
            # Not private: the language the artist chose survives a restart.
            private_mode=False,
            storage_path=str(Path(user_data_dir("Luikki", appauthor=False)) / "webview"),
        )
    finally:
        server.stop()
