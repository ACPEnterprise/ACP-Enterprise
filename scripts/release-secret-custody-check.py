#!/usr/bin/env python3
"""Validate secret declarations and tracked-file custody without printing values."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-example", type=Path, required=True)
    args = parser.parse_args()
    names = {
        line.split("=", 1)[0]
        for line in args.env_example.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    required = {
        "DATABASE_URL",
        "ACCESS_TOKEN_KEYS",
        "PLATFORM_CONTRACT_EXPECTED_FINGERPRINT",
    }
    missing = sorted(required - names)
    tracked = subprocess.check_output(("git", "ls-files"), text=True).splitlines()
    forbidden = sorted(
        path for path in tracked if path in {".env", ".env.preview", ".env.production"}
    )
    if missing or forbidden:
        if missing:
            print("Missing required secret declarations: " + ", ".join(missing))
        if forbidden:
            print("Runtime secret files are tracked: " + ", ".join(forbidden))
        return 1
    print(f"Required secret declarations present: {len(required)}")
    print("Runtime secret files tracked: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
