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

    serve = sub.add_parser("serve", help="start the local web app")
    # Loopback default: PROJECT.md scopes v1 to one machine, and the app has
    # no authentication by design, so binding a routable interface would
    # expose an unauthenticated file-writing API to the local network.
    serve.add_argument("--host", default="127.0.0.1", help="bind address")
    serve.add_argument("--port", type=int, default=8000, help="bind port")
    serve.add_argument(
        "--project", default=None, help="project folder to open at startup"
    )
    serve.add_argument(
        "--reload", action="store_true", help="reload on source changes (development)"
    )

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

    if args.command == "serve":
        import os

        import uvicorn

        from .web.appconfig import is_project_folder

        project_path = None
        if args.project:
            # expanduser/resolve: `--project ~/ComicColor/Kaito` is the
            # obvious thing to type and used to fail with "not a project
            # folder" because the tilde was never expanded.
            project_path = Path(args.project).expanduser().resolve()
            if not is_project_folder(project_path):
                raise SystemExit(f"not a project folder: {project_path}")

        if args.reload:
            # uvicorn can only reload from an *import string* — handed an app
            # instance it logs a warning and silently runs without reloading,
            # which is what --help was advertising. Because the reloader
            # re-imports the app in a fresh process, the project can't be set
            # on an object here; it travels through the environment and
            # web.app picks it up at startup.
            if project_path is not None:
                os.environ["COMICCOLOR_PROJECT"] = str(project_path)
            uvicorn.run(
                "comiccolor.web.app:create_app",
                factory=True,
                host=args.host,
                port=args.port,
                reload=True,
            )
        else:
            from .web.app import create_app
            from .web.deps import set_current_project

            app = create_app()
            if project_path is not None:
                set_current_project(app, project_path)
            uvicorn.run(app, host=args.host, port=args.port)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
