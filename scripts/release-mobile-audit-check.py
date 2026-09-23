#!/usr/bin/env python3
"""Fail closed on mobile dependency findings except reviewed build-only advisories."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MOBILE_ROOT = REPOSITORY_ROOT / "mobile"
REVIEWED_ADVISORY = 1119441
REVIEWED_CHAIN = {
    "@expo/cli",
    "@expo/config",
    "@expo/config-plugins",
    "@expo/inline-modules",
    "@expo/local-build-cache-provider",
    "@expo/metro-config",
    "@expo/prebuild-config",
    "expo",
    "uuid",
    "xcode",
}


def source_uses_affected_uuid_api() -> list[str]:
    findings: list[str] = []
    for root in ("src", "scripts", "__tests__"):
        for path in sorted((MOBILE_ROOT / root).rglob("*")):
            if path.suffix not in {".js", ".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            if "from \"uuid\"" in text or "from 'uuid'" in text or "require(\"uuid\")" in text or "require('uuid')" in text:
                findings.append(str(path.relative_to(REPOSITORY_ROOT)))
    return findings


def main() -> int:
    completed = subprocess.run(
        ["npm", "audit", "--prefix", "mobile", "--omit=dev", "--json"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(completed.stdout + completed.stderr)
        return 2

    counts = report.get("metadata", {}).get("vulnerabilities", {})
    vulnerabilities = report.get("vulnerabilities", {})
    print("Mobile npm audit counts: " + json.dumps(counts, sort_keys=True))
    if not vulnerabilities:
        return 0
    if counts.get("critical", 0) or counts.get("high", 0):
        print("BLOCKING: mobile dependency audit contains HIGH or CRITICAL findings")
        return 1
    if set(vulnerabilities) != REVIEWED_CHAIN:
        print("BLOCKING: mobile dependency audit contains an unreviewed package chain")
        return 1

    uuid_advisories = vulnerabilities.get("uuid", {}).get("via", [])
    sources = {
        item.get("source")
        for item in uuid_advisories
        if isinstance(item, dict)
    }
    if sources != {REVIEWED_ADVISORY}:
        print("BLOCKING: mobile uuid advisory set changed and requires review")
        return 1
    direct_usage = source_uses_affected_uuid_api()
    if direct_usage:
        print("BLOCKING: application source imports the affected uuid API: " + ", ".join(direct_usage))
        return 1

    print(
        "REVIEWED_NON_RUNTIME: GHSA-w5hq-g745-h8pq is confined to "
        "Expo -> config-plugins -> xcode build tooling; ACP Mobile does not import "
        "uuid v3/v5/v6, and npm offers only a breaking Expo downgrade."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
