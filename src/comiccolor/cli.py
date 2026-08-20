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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comiccolor")
    sub = parser.add_subparsers(dest="command", required=True)

    p3 = sub.add_parser("p3", help="run the P3 region-count spike")
    p3.add_argument("pages", nargs="+", help="image files or directories")
    p3.add_argument("-o", "--out", default="reports/p3", help="output directory")
    p3.add_argument("--weights", default=None, help="path to erika.pth")
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
    ab.add_argument("--weights", default=None, help="path to erika.pth")
    ab.add_argument(
        "--conditions",
        default="raw,extracted",
        help="comma-separated: raw, extracted",
    )
    ab.add_argument("--no-debug", action="store_true", help="skip debug renders")

    serve = sub.add_parser("serve", help="run the flatting app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument(
        "--workdir", default=None, help="where uploads and the exported PSD land"
    )
    serve.add_argument(
        "--proposer",
        default=None,
        choices=["distinct", "cobra"],
        help="colour proposer; cobra needs an NVIDIA GPU and its weights",
    )
    serve.add_argument(
        "--extractor",
        default=None,
        choices=["manga", "raw"],
        help="line extractor before segmentation; raw skips it (§2.2 chose manga)",
    )

    flatten = sub.add_parser(
        "flatten",
        help="run every step on one page headlessly, snapping all segments",
    )
    flatten.add_argument("page", help="the line-art page")
    flatten.add_argument(
        "-r",
        "--reference",
        action="append",
        default=[],
        help="character sheet or coloured page; repeatable. Cobra needs one",
    )
    flatten.add_argument("-o", "--out", default=None, help="where the PSD lands")
    flatten.add_argument(
        "--proposer", default="distinct", choices=["distinct", "cobra"]
    )
    flatten.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=(
            "max weighted CIELAB distance to snap; omit for the default guard, "
            "pass 0 to snap nothing, pass inf to snap everything regardless"
        ),
    )
    flatten.add_argument(
        "--no-snap",
        action="store_true",
        help="stop after flats, leaving every segment its own colour",
    )

    args = parser.parse_args(argv)

    if args.command == "flatten":
        from .colour.snap import SNAP_MAX_DELTA
        from .web.session import Session

        proposer = None
        if args.proposer == "cobra":
            from .colour.cobra import CobraProposer

            proposer = CobraProposer()

        workdir = Path(args.out or ".comiccolor-work/flatten")
        session = Session(workdir=workdir, proposer=proposer)
        for reference in args.reference:
            session.add_reference(reference, original_name=Path(reference).name)
        session.load_page(args.page, original_name=Path(args.page).name)

        session.detect_panels()
        session.detect_bubbles()
        session.segment_zones()
        flats = session.generate_flats()
        print(
            f"{len(session.panels)} panels, {len(session.protected)} bubbles, "
            f"{flats['segments']} segments, {flats['colours']} palette entries"
        )

        if args.no_snap:
            print("not snapping: every segment keeps its own proposed colour")
        else:
            threshold = SNAP_MAX_DELTA if args.threshold is None else args.threshold
            if threshold == float("inf"):
                threshold = None
            result = session.snap_all(threshold)
            print(
                f"snap-all: {result['snapped']} snapped, "
                f"{result['skipped']} left as proposed "
                f"(threshold {'none' if threshold is None else threshold})"
            )

        psd = session.export_psd()
        print(f"PSD: {psd}")
        return 0



    if args.command == "serve":
        import os

        import uvicorn

        if args.proposer:
            os.environ["COMICCOLOR_PROPOSER"] = args.proposer
        if args.extractor:
            os.environ["COMICCOLOR_EXTRACTOR"] = args.extractor

        from .web.app import create_app

        print(f"ComicColor on http://{args.host}:{args.port}")
        uvicorn.run(create_app(args.workdir), host=args.host, port=args.port)
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
