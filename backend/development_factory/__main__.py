from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from development_factory.engine import DevelopmentFactory
from development_factory.manifest import ManifestError
from development_factory.reports import render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="development-factory",
        description="Validate and report on ACP Enterprise without mutating source or Git.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--backend", action="store_true")
    validate.add_argument("--frontend", action="store_true")
    validate.add_argument("--migrations", action="store_true")
    validate.add_argument("--architecture", action="store_true")
    validate.add_argument("--changed", action="store_true")
    subparsers.add_parser("report")
    args = parser.parse_args()

    try:
        factory = DevelopmentFactory(args.repo_root)
        if args.command == "report":
            latest = args.repo_root / ".development-factory" / "latest.json"
            if not latest.exists():
                print("No report exists. Run validation first.", file=sys.stderr)
                return 2
            report = json.loads(latest.read_text(encoding="utf-8"))
            print(render_markdown(report))
            return int(report.get("exit_status", 1))

        selected = tuple(
            name
            for name in ("backend", "frontend", "migrations", "architecture")
            if getattr(args, name)
        )
        if not selected and not args.changed:
            selected = ("all",)
        report, json_path, markdown_path = factory.validate(
            selected, changed_only=args.changed
        )
        for result in report["checks"]:
            print(
                f"[{str(result['status']).upper():13}] "
                f"{result['id']}: {result['summary']}"
            )
        print(f"JSON report: {json_path}")
        print(f"Markdown report: {markdown_path}")
        print(f"Classification: {report['readiness']}")
        return int(report["exit_status"])
    except (ManifestError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Development Factory configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
