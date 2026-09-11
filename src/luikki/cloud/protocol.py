"""What the client and the server agree on, and nothing that imports FastAPI.

`colour/remote.py` and `cloud/server.py` both read this file, so a field name
or an encoding cannot drift between them.

Every pixel crosses as PNG: lossless, so the raster the server paints is the
raster the zone modes are read from, and a format the server can refuse
anything else by.
"""

from __future__ import annotations

import cv2
import numpy as np

# Bumped whenever a field changes meaning. The server answers an older client
# with `protocol_unsupported` instead of guessing.
PROTOCOL = 1

PANEL_ROUTE = "/v1/panel"
MODEL_VERSION_HEADER = "x-luikki-model-version"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def encode_png(pixels: np.ndarray) -> bytes:
    """HxWx3 RGB or HxW grey uint8 -> PNG bytes."""
    if pixels.ndim == 3:
        pixels = cv2.cvtColor(np.ascontiguousarray(pixels, dtype=np.uint8), cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".png", pixels)
    if not ok:
        raise ValueError("could not encode PNG")
    return encoded.tobytes()


def decode_png(data: bytes, grey: bool = False) -> np.ndarray:
    """PNG bytes -> HxWx3 RGB uint8, or HxW when `grey`. Anything else raises."""
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError("not a PNG")
    flag = cv2.IMREAD_GRAYSCALE if grey else cv2.IMREAD_COLOR
    pixels = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flag)
    if pixels is None:
        raise ValueError("corrupt PNG")
    return pixels if grey else cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB)
