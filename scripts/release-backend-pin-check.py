#!/usr/bin/env python3
"""Fail closed when backend requirement inputs permit version drift."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_FILES = (
    ROOT / "backend" / "requirements.txt",
    ROOT / "backend" / "requirements-dev.txt",
)
EXACT_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?==[^;\s]+(?:\s*;\s*.+)?$"
)


def unpinned_requirements(path: Path) -> tuple[str, ...]:
    findings: list[str] = []
    try:
        display_path = path.relative_to(ROOT)
    except ValueError:
        display_path = path
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "-r ")):
            continue
        if not EXACT_REQUIREMENT.fullmatch(line):
            findings.append(f"{display_path}:{number}")
    return tuple(findings)


def main() -> int:
    findings = tuple(
        finding
        for path in REQUIREMENT_FILES
        for finding in unpinned_requirements(path)
    )
    if findings:
        print("Backend requirements are not exactly pinned: " + ", ".join(findings))
        return 1
    print("Backend direct requirements are exactly pinned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
