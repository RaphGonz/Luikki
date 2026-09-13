"""The model files the client runs, and where a copy of the app finds them.

Nothing downloads at launch. An installed app carries `models/` inside its
bundle (B4); a source checkout, and the release build, fill `models/` once with
`luikki models`. Both files are too large for git history, which is why they
are fetched rather than committed, and each is checked against a pinned sha256.

- `manga_line.onnx` — MangaLineExtraction (MIT), exported from the upstream
  `erika.pth` so the client runs it on onnxruntime and never needs torch. The
  export the parity test was read on is published as a release asset, so no
  build needs torch either; `export_manga_line` is how that file was made.
- `comic_bubble_detector.onnx` — RT-DETR-v2 (Apache-2.0), downloaded as
  published and checked against the file the test pages were measured with.
"""

from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

MANGA_LINE = "manga_line.onnx"
BUBBLE_DETECTOR = "comic_bubble_detector.onnx"

DETECTOR_URL = (
    "https://huggingface.co/ogkalu/comic-text-and-bubble-detector/"
    "resolve/main/detector.onnx"
)
# The file `segmentation/bubbles.py` was measured with on the six test pages.
DETECTOR_SHA256 = "065744e91c0594ad8663aa8b870ce3fb27222942eded5a3cc388ce23421bd195"

MANGA_LINE_URL = "https://github.com/RaphGonz/Luikki/releases/download/models-1/manga_line.onnx"
# The export read against torch on teddy and laurine (`reports/onnx_parity/`).
MANGA_LINE_SHA256 = "0395b38ae61258b81485b7ba60b857df6542d923801fee2f17470439c7bcbf58"

_REPO = Path(__file__).resolve().parents[2]
ERIKA = _REPO / "third_party" / "MangaLineExtraction" / "erika.pth"
ERIKA_URL = "https://github.com/ljsabc/MangaLineExtraction_PyTorch/releases/download/v1/erika.pth"


def model_dir() -> Path:
    """`LUIKKI_MODELS`, else the installed app's bundle, else the checkout's `models/`."""
    override = os.environ.get("LUIKKI_MODELS")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        # PyInstaller unpacks bundled data under `_MEIPASS`.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "models"
    return _REPO / "models"


def model_file(name: str) -> Path:
    """A model the app needs, or an error that says how to get it."""
    path = model_dir() / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Run `luikki models` once to fetch the model files."
        )
    return path


def fetch_models(log: Callable[[str], None] = print) -> None:
    """Fill `models/` with the pinned files. Safe to rerun."""
    folder = model_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for name, url, sha256 in (
        (BUBBLE_DETECTOR, DETECTOR_URL, DETECTOR_SHA256),
        (MANGA_LINE, MANGA_LINE_URL, MANGA_LINE_SHA256),
    ):
        path = folder / name
        if not path.exists():
            log(f"downloading {url}")
            _download(url, sha256, path)
        log(f"ready: {path}")


def export_manga_line(weights: Path, out: Path) -> None:
    """`erika.pth` to ONNX, with the page's height and width left free.

    Development only, and once per model: this is how the published
    `manga_line.onnx` was made. A new export is a new release asset and a new
    `MANGA_LINE_SHA256`, after the parity test has been read again.
    """
    import torch

    vendor = str(weights.parent)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from model_torch import res_skip  # type: ignore[import-not-found]

    model = res_skip()
    model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
    model.eval()

    # Five stride-2 stages, and the skip connections add each one to its
    # upsampled twin: both sides must be multiples of 16. Saying so is what
    # lets the exporter keep them free instead of fixing the sample's size.
    height = torch.export.Dim("height", min=1, max=1024)
    width = torch.export.Dim("width", min=1, max=1024)
    sample = torch.ones(1, 1, 256, 384)
    partial = out.with_name(out.name + ".part")
    torch.onnx.export(
        model,
        (sample,),
        str(partial),
        input_names=["grey"],
        output_names=["lines"],
        dynamic_shapes={"x": {2: 16 * height, 3: 16 * width}},
        dynamo=True,
        external_data=False,
    )
    partial.replace(out)


def _download(url: str, sha256: str, out: Path) -> None:
    partial = out.with_name(out.name + ".part")
    urllib.request.urlretrieve(url, partial)
    digest = _sha256(partial)
    if digest != sha256:
        partial.unlink()
        raise RuntimeError(f"{url} is not the file the app was measured with: sha256 {digest}")
    partial.replace(out)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
