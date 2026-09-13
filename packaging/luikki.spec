# PyInstaller build of the installed app, one folder (ROADMAP B4).
#
#     python -m venv .venv-build
#     .venv-build\Scripts\pip install -e ".[desktop]" pyinstaller
#     .venv-build\Scripts\luikki models
#     .venv-build\Scripts\pyinstaller packaging\luikki.spec --noconfirm
#
# Out: dist\Luikki\Luikki.exe on Windows, dist/Luikki.app on the Mac (arm64,
# signed ad hoc by PyInstaller). From a venv without torch, so nothing of it
# can be pulled in; `third_party/LineFiller` must be cloned. The release build
# is `.github/workflows/release.yml`.

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
MODELS = ROOT / "models"
LINEFILLER = ROOT / "third_party" / "LineFiller"
MAC = sys.platform == "darwin"
VERSION = re.search(r'__version__ = "(.+)"', (ROOT / "src" / "luikki" / "__init__.py").read_text())[1]

for required in (MODELS / "manga_line.onnx", MODELS / "comic_bubble_detector.onnx", LINEFILLER / "linefiller"):
    if not required.exists():
        raise SystemExit(f"{required} is missing; see the top of this file")

sys.path.insert(0, SPECPATH)
from icon import write_icon  # noqa: E402

# The .ico is also read by `luikki.iss`. On the Mac PyInstaller turns the PNG
# into the bundle's .icns itself, with Pillow.
ICON = write_icon(
    ROOT / "src" / "luikki" / "web" / "static" / "favicon.svg",
    ROOT / "build" / ("luikki.png" if MAC else "luikki.ico"),
)

a = Analysis(
    [str(ROOT / "packaging" / "luikki_app.py")],
    # `linefiller` is imported from the vendored folder, not an installed package.
    pathex=[str(ROOT / "src"), str(LINEFILLER)],
    datas=[
        (str(ROOT / "src" / "luikki" / "web" / "static"), "luikki/web/static"),
        (str(MODELS / "manga_line.onnx"), "models"),
        (str(MODELS / "comic_bubble_detector.onnx"), "models"),
    ],
    hiddenimports=["linefiller.trappedball_fill", *collect_submodules("uvicorn")],
    # Development and server-side only. The client never imports them at run
    # time, but `cobra.py` and `models.py` name them.
    excludes=["torch", "torchvision", "onnx", "onnxscript", "modal", "matplotlib", "tkinter", "pytest", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Luikki",
    # A window app: no console behind it. `desktop.log_to_file` catches output.
    console=False,
    icon=str(ICON),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Luikki", upx=False)

if MAC:
    app = BUNDLE(
        coll,
        name="Luikki.app",
        icon=str(ICON),
        bundle_identifier="app.luikki",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            # The window shows the app's own server on 127.0.0.1, over http.
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
