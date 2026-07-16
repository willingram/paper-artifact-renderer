from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .renderer import render_job
from .verify import verify_output


def main() -> int:
    parser = argparse.ArgumentParser(prog="par")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="Render a JSON job file")
    render_parser.add_argument("--job", required=True, type=Path)
    render_parser.add_argument("--out", required=True, type=Path)

    verify_parser = subparsers.add_parser("verify", help="Verify a rendered output directory")
    verify_parser.add_argument("--out", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "render":
        manifest = render_job(args.job, args.out)
        print(f"Rendered {manifest['page_count']} page(s) to {args.out}")
        if manifest.get("pdf"):
            print(f"PDF: {manifest['pdf']}")
        print(f"Truth sidecar: {manifest['truth']}")
        return 0

    if args.command == "verify":
        report = verify_output(args.out)
        print("Verification PASS")
        for line in report:
            print(f"- {line}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2
