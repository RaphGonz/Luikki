"""P3 follow-up: does the reference trapped-ball implementation change the verdict?

P3 measured our own segmenter and returned MARGINAL almost everywhere — region
counts far above the spec's "~80 = viable" but far below "~3000 = collapse".
That result is only decision-grade if the count is a property of *the art*
rather than of our implementation. LineFiller does two things ours does not
(drop small fills per radius, merge afterwards), either of which could move the
count by an order of magnitude.

So the question here is narrow: holding the line raster fixed, how much of P3's
region count is hatching and how much is us?

Results are written after every page. The run is slow enough that losing it to
a closed terminal is a real cost, and a partial report is still evidence.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from ..extract.manga_line import MangaLineExtractor
from ..extract.passthrough import PassthroughExtractor
from ..model.masks import check_coverage, region_count, regions_to_cover
from ..segmentation.preprocess import ink_fraction, load_line_art
from ..segmentation.segmenter import LineFillerSegmenter, TrappedBallSegmenter
from .p3 import VIABLE_CEILING, verdict
from .visualise import colourise_labels


def _segmenters() -> list:
    return [
        TrappedBallSegmenter(),
        LineFillerSegmenter(merge=False),
        LineFillerSegmenter(merge=True),
    ]


def _binarise(lines: np.ndarray, threshold: int | None) -> np.ndarray:
    if threshold is None:
        _, binary = cv2.threshold(
            lines, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
    else:
        _, binary = cv2.threshold(lines, threshold, 255, cv2.THRESH_BINARY_INV)
    return binary.astype(bool)


def run_ab(
    pages: list[Path],
    out_dir: Path,
    conditions: tuple[str, ...] = ("raw", "extracted"),
    weights: Path | None = None,
    debug: bool = True,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    extractors = {
        "raw": PassthroughExtractor(),
        "extracted": MangaLineExtractor(weights=weights),
    }

    report: dict = {
        "thresholds": {"viable_ceiling": VIABLE_CEILING},
        "note": "Whole-page segmentation. Verdicts use P3's per-panel ceiling "
        "and are therefore optimistic for multi-panel pages.",
        "pages": [],
    }

    # Resume rather than restart. A merged LineFiller pass is minutes per page,
    # so adding a fourth page to a finished run should cost one page, not four.
    existing = out_dir / "ab.json"
    if existing.exists():
        previous = json.loads(existing.read_text(encoding="utf-8"))
        # A page interrupted mid-run is present but partial. Keeping it would
        # silently skip the rest of its work on resume, so completeness is
        # checked rather than assumed: every condition, every segmenter.
        report["pages"] = [
            page
            for page in previous.get("pages", [])
            if _is_complete(page, conditions)
        ]
    done = {p["page"] for p in report["pages"]}

    for path in pages:
        if path.name in done:
            print(f"skipping {path.name} (already in {existing})", flush=True)
            continue
        line_mask, grey = load_line_art(path)
        height, width = grey.shape
        page_entry: dict = {
            "page": path.name,
            "width": width,
            "height": height,
            "conditions": [],
        }
        # Attached before it is filled, so the flushes below reach it by
        # reference. Appending at the end of the page would mean every
        # mid-page flush wrote a report with no rows in it.
        report["pages"].append(page_entry)

        for condition in conditions:
            lines = extractors[condition].extract(grey).lines
            mask = _binarise(lines, None)

            entry: dict = {
                "condition": condition,
                "ink_fraction": round(ink_fraction(mask), 4),
                "segmenters": [],
            }
            page_entry["conditions"].append(entry)

            for segmenter in _segmenters():
                started = time.perf_counter()
                labels = segmenter.segment(mask)
                seconds = round(time.perf_counter() - started, 2)

                total = region_count(labels)
                structural = regions_to_cover(labels, 0.9)
                coverage = check_coverage(labels, mask)

                entry["segmenters"].append(
                    {
                        "segmenter": segmenter.name,
                        "regions": total,
                        "structural_regions": structural,
                        "texture_share": round(1.0 - structural / total, 3)
                        if total
                        else 0.0,
                        "coverage": round(float(coverage["coverage"]), 4),
                        "exhaustive": bool(coverage["exhaustive"]),
                        "seconds": seconds,
                        "timing": getattr(segmenter, "last_timing", {}),
                        "verdict": verdict(total),
                        "structural_verdict": verdict(structural),
                    }
                )

                if debug:
                    canvas = colourise_labels(labels)
                    canvas[mask] = (0, 0, 0)
                    cv2.imwrite(
                        str(
                            out_dir
                            / f"ab_{path.stem}_{condition}_{segmenter.name}.png"
                        ),
                        canvas,
                    )

                # Written after every segmenter, not at the end: this run is
                # long and a half-finished table still answers the question.
                _flush(report, out_dir)

            _flush(report, out_dir)

        _flush(report, out_dir)

    return report


def _is_complete(page: dict, conditions: tuple[str, ...]) -> bool:
    present = {c["condition"]: c for c in page.get("conditions", [])}
    if not all(name in present for name in conditions):
        return False
    expected = len(_segmenters())
    return all(len(present[name]["segmenters"]) == expected for name in conditions)


def _flush(report: dict, out_dir: Path) -> None:
    (out_dir / "ab.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "ab.md").write_text(format_report(report), encoding="utf-8")


def format_report(report: dict) -> str:
    lines = [
        "# P3 follow-up — our trapped-ball vs. LineFiller",
        "",
        f"Viable ceiling: {report['thresholds']['viable_ceiling']} regions.",
        "",
        report["note"],
        "",
    ]

    for page in report["pages"]:
        lines += [f"## {page['page']} ({page['width']}x{page['height']})", ""]
        for condition in page["conditions"]:
            lines += [
                f"### {condition['condition']} "
                f"(ink {condition['ink_fraction']:.3f})",
                "",
                "| Segmenter | Regions | Structural | Texture share | Coverage | Seconds | Verdict | Verdict (structural) |",
                "|---|---|---|---|---|---|---|---|",
            ]
            for s in condition["segmenters"]:
                lines.append(
                    f"| {s['segmenter']} | {s['regions']} | "
                    f"{s['structural_regions']} | {s['texture_share']:.0%} | "
                    f"{s['coverage']:.3f} | {s['seconds']} | "
                    f"{s['verdict']} | {s['structural_verdict']} |"
                )
            lines.append("")

    return "\n".join(lines)
