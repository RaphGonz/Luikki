"""Command line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def _collect_pages(inputs: list[str]) -> list[Path]:
    pages: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            pages += sorted(
                p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
            )
        elif path.is_file():
            pages.append(path)
        else:
            raise FileNotFoundError(item)
    if not pages:
        raise SystemExit("no images found")
    return pages


def _dump_steps(session, out: Path) -> list[Path]:
    """One image per stage boundary, numbered in the order the buttons run.

    The pipeline's claim is that every boundary is inspectable. That is easy
    to believe and hard to check while the only artefact is the PSD at the
    end, so this writes what each step actually handed to the next one.
    """
    import cv2
    import numpy as np

    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def save(name, image):
        path = out / name
        cv2.imencode(".png", image)[1].tofile(str(path))
        written.append(path)

    def over_page():
        """The page as BGR, to draw overlays on without touching the original."""
        return cv2.cvtColor(session.grey, cv2.COLOR_GRAY2BGR)

    save("01_page.png", session.grey)

    panels = over_page()
    for panel in session.panels:
        points = np.array(panel.polygon, np.int32).reshape(-1, 1, 2)
        cv2.polylines(panels, [points], True, (0, 0, 255), 3)
        cv2.putText(
            panels, str(panel.order + 1), (panel.x + 12, panel.y + 44),
            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3,
        )
    save("02_panels.png", panels)

    bubbles = over_page()
    for polygon in session.protected:
        points = np.array(polygon, np.int32).reshape(-1, 1, 2)
        cv2.polylines(bubbles, [points], True, (255, 0, 0), 3)
    save("03_bubbles.png", bubbles)

    save("04_zones.png", cv2.cvtColor(session.zones_rgba(), cv2.COLOR_RGBA2BGRA))
    if session.state()["done"]["planes"]:
        save("05_planes.png", cv2.cvtColor(session.planes_rgba(), cv2.COLOR_RGBA2BGRA))
    return written


def _dump_psd(psd_path, out: Path, name: str) -> Path | None:
    """The exported PSD, composited back down — proof it opens and has content."""
    try:
        from psd_tools import PSDImage
    except ImportError:  # pragma: no cover - psd-tools is a hard dependency
        return None
    image = PSDImage.open(psd_path).composite()
    if image is None:
        return None
    path = out / name
    image.convert("RGB").save(path)
    return path


def _app_options(parser: argparse.ArgumentParser) -> None:
    """What `serve` and `app` share."""
    parser.add_argument(
        "--workdir",
        default=None,
        help="the project folder (default: Luikki in the user's data folder)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="luikki")
    sub = parser.add_subparsers(dest="command", required=True)

    p3 = sub.add_parser("p3", help="run the P3 region-count spike")
    p3.add_argument("pages", nargs="+", help="image files or directories")
    p3.add_argument("-o", "--out", default="reports/p3", help="output directory")
    p3.add_argument("--weights", default=None, help="path to manga_line.onnx (default: models/)")
    p3.add_argument(
        "--reading", default="rtl", choices=["rtl", "ltr"], help="panel reading order"
    )
    p3.add_argument(
        "--conditions",
        default=None,
        help="comma-separated condition names; default runs all",
    )
    p3.add_argument("--no-debug", action="store_true", help="skip debug renders")

    ab = sub.add_parser("ab", help="compare our trapped-ball against LineFiller")
    ab.add_argument("pages", nargs="+", help="image files or directories")
    ab.add_argument("-o", "--out", default="reports/ab", help="output directory")
    ab.add_argument("--weights", default=None, help="path to manga_line.onnx (default: models/)")

    sub.add_parser(
        "models",
        help="fetch and build the model files the app runs (once, in a source checkout)",
    )
    ab.add_argument(
        "--conditions",
        default="raw,extracted",
        help="comma-separated: raw, extracted",
    )
    ab.add_argument("--no-debug", action="store_true", help="skip debug renders")

    serve = sub.add_parser("serve", help="run the flatting app, for a browser")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    _app_options(serve)

    window = sub.add_parser(
        "app", help="run the flatting app in its own window, as the installed app does"
    )
    _app_options(window)
    window.add_argument(
        "--debug", action="store_true", help="open the web inspector with the window"
    )

    flatten = sub.add_parser(
        "flatten",
        help="run every step on one page headlessly and write the PSD",
    )
    flatten.add_argument("page", help="the line-art page")
    flatten.add_argument("-o", "--out", default=None, help="where the PSD lands")
    flatten.add_argument(
        "--layers",
        default="plane",
        choices=["plane", "colour"],
        help=(
            "PSD stack: plane = one layer per plane; colour = one group per "
            "plane, one layer per colour inside it"
        ),
    )
    flatten.add_argument(
        "--no-planes",
        action="store_true",
        help="skip the planes: one Flats layer under the balloons",
    )
    flatten.add_argument(
        "--extract-lines",
        action="store_true",
        help=(
            "cut the zones from MangaLineExtraction's lines rather than from "
            "the whole of the ink (it erases small dense detail)"
        ),
    )
    flatten.add_argument(
        "--leak-gap",
        type=float,
        default=None,
        metavar="SHARE",
        help=(
            "how open a zone border may be before §1.3 reads it as a passage "
            "rather than a hole in a line (0-1, default 0.14). Raise it to cut "
            "more, lower it to cut less; it is a property of the ink, so sweep "
            "it on a page of the style before settling on one"
        ),
    )
    flatten.add_argument(
        "--steps",
        nargs="?",
        const=True,
        default=None,
        metavar="DIR",
        help="write one image per stage boundary (default: <out>/steps)",
    )

    args = parser.parse_args(argv)

    if args.command == "flatten":
        from .web.session import Session

        workdir = Path(args.out or ".luikki-work/flatten")
        session = Session(workdir=workdir)
        session.load_page(args.page, original_name=Path(args.page).name)

        steps_dir = None
        if args.steps is not None:
            steps_dir = Path(workdir / "steps" if args.steps is True else args.steps)

        session.detect_panels()
        session.detect_bubbles()
        session.segment_zones(leak_gap=args.leak_gap, extract_lines=args.extract_lines)
        if not args.no_planes:
            session.detect_planes()
        if steps_dir is not None:
            _dump_steps(session, steps_dir)
        zones = sum(panel.zone_count for panel in session.panels)
        print(f"{len(session.panels)} panels, {len(session.protected)} bubbles, {zones} zones")

        psd = session.export_psd(granularity=args.layers)
        layers = session.state()["export"]["layers"][args.layers]
        print(f"PSD: {psd} ({layers} layers, by {args.layers})")
        if steps_dir is not None:
            _dump_psd(psd, steps_dir, "06_psd_composite.png")
            print(f"steps: {steps_dir}")
        return 0

    if args.command == "serve":
        import uvicorn

        from .web.app import create_app

        print(f"Luikki on http://{args.host}:{args.port}")
        uvicorn.run(create_app(args.workdir), host=args.host, port=args.port)
        return 0

    if args.command == "app":
        from .desktop import run
        from .web.app import create_app

        run(create_app(args.workdir), debug=args.debug)
        return 0

    if args.command == "models":
        from .models import fetch_models

        try:
            fetch_models()
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        return 0

    if args.command == "p3":
        from .spike.p3 import DEFAULT_CONDITIONS, format_report, run_p3

        conditions = DEFAULT_CONDITIONS
        if args.conditions:
            wanted = {name.strip() for name in args.conditions.split(",")}
            conditions = [c for c in DEFAULT_CONDITIONS if c.name in wanted]
            if not conditions:
                raise SystemExit(f"no conditions matched: {sorted(wanted)}")

        report = run_p3(
            pages=_collect_pages(args.pages),
            out_dir=Path(args.out),
            conditions=conditions,
            weights=Path(args.weights) if args.weights else None,
            reading=args.reading,
            debug=not args.no_debug,
        )
        print(format_report(report))
        print(f"\nwritten to {args.out}/p3.json and {args.out}/p3.md")

    if args.command == "ab":
        from .spike.ab import format_report, run_ab

        report = run_ab(
            pages=_collect_pages(args.pages),
            out_dir=Path(args.out),
            conditions=tuple(n.strip() for n in args.conditions.split(",")),
            weights=Path(args.weights) if args.weights else None,
            debug=not args.no_debug,
        )
        print(format_report(report))
        print(f"\nwritten to {args.out}/ab.json and {args.out}/ab.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
