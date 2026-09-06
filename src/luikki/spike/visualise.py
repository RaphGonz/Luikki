"""Debug renders. Every stage boundary is inspectable (§1.9) — including in a
spike, because a region count you cannot eyeball is a number you cannot trust.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..segmentation.panels import Panel


def colourise_labels(label_map: np.ndarray, seed: int = 0) -> np.ndarray:
    """Random distinct colour per region. BGR uint8, black on unassigned."""
    max_label = int(label_map.max())
    rng = np.random.default_rng(seed)
    lut = rng.integers(40, 255, size=(max_label + 1, 3), dtype=np.uint8)
    lut[0] = (0, 0, 0)
    return lut[label_map]


def overlay_panels(
    grey: np.ndarray, boxes: list[Panel], reading_labels: bool = True
) -> np.ndarray:
    """Draw panel boxes and reading order over the page."""
    canvas = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
    for order, box in enumerate(boxes):
        cv2.rectangle(
            canvas, (box.x, box.y), (box.x + box.width, box.y + box.height), (0, 0, 255), 3
        )
        if reading_labels:
            cv2.putText(
                canvas,
                str(order),
                (box.x + 12, box.y + 48),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.4,
                (0, 0, 255),
                3,
            )
    return canvas


def write_panel_debug(
    out_dir: Path,
    page_stem: str,
    panel_index: int,
    label_map: np.ndarray,
    line_crop: np.ndarray,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    coloured = colourise_labels(label_map)
    # Composite the ink back over the flats so leaks are obvious at a glance.
    coloured[line_crop] = (0, 0, 0)
    cv2.imwrite(str(out_dir / f"{page_stem}_panel{panel_index:02d}.png"), coloured)
