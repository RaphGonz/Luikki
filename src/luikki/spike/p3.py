"""P3: run trapped-ball on real pages and count regions per panel.

The spec's threshold: "~80 = viable. ~3000 = hatching is the real problem and
Tier 3 reorders."

The measurement is a comparison, not a single number. A region count only
means something relative to what produced the line raster it came from, so
every page is run under several conditions and the interesting quantity is the
ratio between them:

- passthrough vs. MangaLineExtraction tells us how much texture the extractor
  absorbs, which is the whole Tier 3 hatching question;
- with vs. without gap closure tells us whether §1.3 is helping or stitching
  hatching into a ladder;
- across binarisation thresholds tells us how fragile any of it is.

Panels are segmented **once** per page, from the original raster, and shared
by every condition. Region counts are then per-panel comparable.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..extract.base import LineExtractor
from ..extract.manga_line import MangaLineExtractor
from ..extract.passthrough import PassthroughExtractor
from ..model.masks import check_coverage, region_count, region_stats, regions_to_cover
from ..segmentation.closure import ClosureParams, close_line_gaps
from ..segmentation.panels import Panel, PanelParams, segment_panels
from ..segmentation.preprocess import estimate_line_width, ink_fraction, load_line_art
from ..segmentation.trappedball import SegmentationParams, trapped_ball_segment
from .visualise import colourise_labels, overlay_panels

# §P3's own numbers, as decision boundaries on median regions per panel.
VIABLE_CEILING = 150
COLLAPSE_FLOOR = 1000


@dataclass
class Condition:
    """One (extractor, threshold, closure) combination."""

    name: str
    extractor: str  # "passthrough" | "manga_line"
    threshold: int | None = None  # None = Otsu
    closure: bool = False


DEFAULT_CONDITIONS = [
    Condition("raw", extractor="passthrough"),
    Condition("extracted", extractor="manga_line"),
    Condition("extracted+closure", extractor="manga_line", closure=True),
    Condition("extracted@t200", extractor="manga_line", threshold=200),
    Condition("extracted@t240", extractor="manga_line", threshold=240),
]


@dataclass
class PanelResult:
    panel_index: int
    x: int
    y: int
    width: int
    height: int
    regions: int
    # Regions carrying 90% of the panel's area. The structural region count.
    structural_regions: int
    median_region_area: float
    largest_region_area: int
    coverage: float
    exhaustive: bool


@dataclass
class ConditionResult:
    condition: str
    ink_fraction: float
    line_width: float
    seconds: float
    panels: list[PanelResult] = field(default_factory=list)

    @property
    def total_regions(self) -> int:
        return sum(p.regions for p in self.panels)

    @property
    def median_regions_per_panel(self) -> float:
        if not self.panels:
            return 0.0
        return float(np.median([p.regions for p in self.panels]))

    @property
    def max_regions_per_panel(self) -> int:
        return max((p.regions for p in self.panels), default=0)

    @property
    def median_structural_per_panel(self) -> float:
        if not self.panels:
            return 0.0
        return float(np.median([p.structural_regions for p in self.panels]))

    @property
    def texture_share(self) -> float:
        """Share of regions that carry almost no area. The hatching signature."""
        total = self.total_regions
        if total == 0:
            return 0.0
        structural = sum(p.structural_regions for p in self.panels)
        return round(1.0 - structural / total, 3)


@dataclass
class PageResult:
    page: str
    width: int
    height: int
    panels_found: int
    conditions: list[ConditionResult] = field(default_factory=list)


def verdict(median_regions: float) -> str:
    """§P3's decision, stated in the spec's own terms."""
    if median_regions <= VIABLE_CEILING:
        return "VIABLE"
    if median_regions >= COLLAPSE_FLOOR:
        return "HATCHING DOMINATES"
    return "MARGINAL"


def _build_extractors(conditions: list[Condition], weights: Path | None) -> dict[str, LineExtractor]:
    """Instantiate each named extractor once; the model load is not cheap."""
    extractors: dict[str, LineExtractor] = {}
    for condition in conditions:
        if condition.extractor in extractors:
            continue
        if condition.extractor == "passthrough":
            extractors[condition.extractor] = PassthroughExtractor()
        elif condition.extractor == "manga_line":
            extractors[condition.extractor] = MangaLineExtractor(model=weights)
        else:
            raise ValueError(f"unknown extractor: {condition.extractor}")
    return extractors


def run_page(
    path: Path,
    conditions: list[Condition],
    extractors: dict[str, LineExtractor],
    out_dir: Path,
    panel_params: PanelParams,
    seg_params: SegmentationParams,
    debug: bool = True,
) -> PageResult:
    line_mask, grey = load_line_art(path)
    height, width = grey.shape

    # Panels come from the original raster, once, so counts stay comparable.
    boxes = segment_panels(line_mask, panel_params)
    if debug:
        out_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_dir / f"{path.stem}_panels.png"), overlay_panels(grey, boxes))

    page_result = PageResult(
        page=path.name, width=width, height=height, panels_found=len(boxes)
    )

    # Cache extractor output: several conditions share one extractor and only
    # differ in threshold or closure. The model pass is by far the slow part.
    line_images: dict[str, np.ndarray] = {}

    for condition in conditions:
        if condition.extractor not in line_images:
            line_images[condition.extractor] = extractors[condition.extractor].extract(grey).lines
        lines = line_images[condition.extractor]

        started = time.perf_counter()
        mask = _binarise(lines, condition.threshold)

        if condition.closure:
            mask, _ = close_line_gaps(mask, ClosureParams())

        result = ConditionResult(
            condition=condition.name,
            ink_fraction=round(ink_fraction(mask), 4),
            line_width=round(estimate_line_width(mask), 2),
            seconds=0.0,
        )

        for index, box in enumerate(boxes):
            crop = mask[box.y : box.y + box.height, box.x : box.x + box.width]
            labels = trapped_ball_segment(crop, params=seg_params)
            stats = region_stats(labels)
            areas = [area for area, _ in stats.values()]
            coverage = check_coverage(labels, crop)

            result.panels.append(
                PanelResult(
                    panel_index=index,
                    x=box.x,
                    y=box.y,
                    width=box.width,
                    height=box.height,
                    regions=region_count(labels),
                    structural_regions=regions_to_cover(labels, 0.9),
                    median_region_area=float(np.median(areas)) if areas else 0.0,
                    largest_region_area=int(max(areas)) if areas else 0,
                    coverage=round(float(coverage["coverage"]), 4),
                    exhaustive=bool(coverage["exhaustive"]),
                )
            )

            if debug:
                debug_dir = out_dir / condition.name
                debug_dir.mkdir(parents=True, exist_ok=True)
                canvas = colourise_labels(labels)
                canvas[crop] = (0, 0, 0)
                cv2.imwrite(
                    str(debug_dir / f"{path.stem}_panel{index:02d}.png"), canvas
                )

        result.seconds = round(time.perf_counter() - started, 2)
        page_result.conditions.append(result)

        if debug:
            cv2.imwrite(
                str(out_dir / f"{path.stem}_{condition.name}_lines.png"),
                (~mask).astype(np.uint8) * 255,
            )

    return page_result


def _binarise(lines: np.ndarray, threshold: int | None) -> np.ndarray:
    if threshold is None:
        _, binary = cv2.threshold(lines, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, binary = cv2.threshold(lines, threshold, 255, cv2.THRESH_BINARY_INV)
    return binary.astype(bool)


def run_p3(
    pages: list[Path],
    out_dir: Path,
    conditions: list[Condition] | None = None,
    weights: Path | None = None,
    reading: str = "rtl",
    debug: bool = True,
) -> dict:
    conditions = conditions or DEFAULT_CONDITIONS
    extractors = _build_extractors(conditions, weights)
    panel_params = PanelParams(reading=reading)  # type: ignore[arg-type]
    seg_params = SegmentationParams()

    out_dir.mkdir(parents=True, exist_ok=True)
    results = [
        run_page(page, conditions, extractors, out_dir, panel_params, seg_params, debug)
        for page in pages
    ]

    report = {
        "spec_thresholds": {
            "viable_ceiling": VIABLE_CEILING,
            "collapse_floor": COLLAPSE_FLOOR,
        },
        "conditions": [asdict(c) for c in conditions],
        "pages": [
            {
                "page": r.page,
                "width": r.width,
                "height": r.height,
                "panels_found": r.panels_found,
                "conditions": [
                    {
                        **{
                            k: v
                            for k, v in asdict(c).items()
                            if k != "panels"
                        },
                        "total_regions": c.total_regions,
                        "median_regions_per_panel": c.median_regions_per_panel,
                        "max_regions_per_panel": c.max_regions_per_panel,
                        "median_structural_per_panel": c.median_structural_per_panel,
                        "texture_share": c.texture_share,
                        "verdict": verdict(c.median_regions_per_panel),
                        "structural_verdict": verdict(c.median_structural_per_panel),
                        "panels": [asdict(p) for p in c.panels],
                    }
                    for c in r.conditions
                ],
            }
            for r in results
        ],
    }

    (out_dir / "p3.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "p3.md").write_text(format_report(report), encoding="utf-8")
    return report


def format_report(report: dict) -> str:
    lines = [
        "# P3 — trapped-ball region counts on real pages",
        "",
        "Spec thresholds: median regions/panel <= "
        f"{report['spec_thresholds']['viable_ceiling']} viable, "
        f">= {report['spec_thresholds']['collapse_floor']} hatching dominates.",
        "",
    ]

    for page in report["pages"]:
        lines += [
            f"## {page['page']}",
            "",
            f"{page['width']}x{page['height']}, {page['panels_found']} panel(s) found.",
            "",
            "| Condition | Total | Median/panel | Structural/panel | Texture share | Ink frac | Verdict (total) | Verdict (structural) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for condition in page["conditions"]:
            lines.append(
                f"| {condition['condition']} | {condition['total_regions']} | "
                f"{condition['median_regions_per_panel']:.0f} | "
                f"{condition['median_structural_per_panel']:.0f} | "
                f"{condition['texture_share']:.0%} | "
                f"{condition['ink_fraction']:.3f} | "
                f"{condition['verdict']} | {condition['structural_verdict']} |"
            )
        lines.append("")

    lines += [
        "**Structural regions** = the largest regions carrying 90% of panel area.",
        "**Texture share** = the fraction of regions that are area-negligible,",
        "i.e. hatching slivers. That gap is the size of the §7 Tier 3 problem.",
        "",
    ]

    return "\n".join(lines)
