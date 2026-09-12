"""Check a build: one page through every step, in the built app, without a window.

    python packaging/smoke.py <page> [dist/Luikki]

`Luikki flatten` loads the page, finds panels and balloons (the RT-DETR model),
extracts lines (MangaLineExtraction), segments with LineFiller, proposes with
`distinct` and writes the PSD — every library and model file the bundle has to
carry. A missing one fails here rather than on a tester's machine. The app has
no console, so what it printed is read back from its log.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from platformdirs import user_log_dir


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    page = Path(sys.argv[1]).resolve()
    bundle = Path(sys.argv[2] if len(sys.argv) > 2 else "dist/Luikki").resolve()
    executable = bundle / ("Luikki.exe" if sys.platform == "win32" else "Luikki")
    log = Path(user_log_dir("Luikki", appauthor=False)) / "luikki.log"
    offset = log.stat().st_size if log.exists() else 0

    with tempfile.TemporaryDirectory() as out:
        started = time.monotonic()
        code = subprocess.run([str(executable), "flatten", str(page), "-o", out], timeout=900).returncode
        seconds = time.monotonic() - started
        psds = list(Path(out).rglob("*.psd"))

        printed = ""
        if log.exists():
            with log.open(encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                printed = handle.read()
        print(printed.rstrip() or "(the app wrote nothing to its log)")

        if code != 0 or not psds:
            print(f"FAILED: exit {code}, {len(psds)} PSD, {seconds:.0f} s")
            return 1
        print(f"ok: {psds[0].name}, {psds[0].stat().st_size} bytes, {seconds:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
