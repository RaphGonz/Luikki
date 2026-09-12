# PyInstaller build of the installed app, one folder (ROADMAP B4).
#
#     python -m venv .venv-build
#     .venv-build\Scripts\pip install -e ".[desktop]" pyinstaller
#     .venv-build\Scripts\pyinstaller packaging\luikki.spec --noconfirm
#
# Out: dist\Luikki\Luikki.exe. From a venv without torch, so nothing of it can
# be pulled in; `models/` must be filled first (`luikki models`, in a venv that
# has torch) and `third_party/LineFiller` cloned.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
MODELS = ROOT / "models"
LINEFILLER = ROOT / "third_party" / "LineFiller"

for required in (MODELS / "manga_line.onnx", MODELS / "comic_bubble_detector.onnx", LINEFILLER / "linefiller"):
    if not required.exists():
        raise SystemExit(f"{required} is missing; see the top of this file")

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
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Luikki", upx=False)
