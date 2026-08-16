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


    args = parser.parse_args(argv)

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
