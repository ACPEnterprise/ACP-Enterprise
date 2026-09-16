#!/usr/bin/env python3
"""Validate secret declarations and tracked-file custody without printing values."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,255}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    "stripe_live_key": re.compile(r"(?:sk|rk)_live_[A-Za-z0-9]{16,}"),
    "private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+"
        r"[A-Za-z0-9+/=\r\n]{64,}"
        r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
}


def scan_tracked_files(paths: list[Path]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in paths:
        try:
            contents = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(contents):
                findings.append((str(path), name))
    return findings


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
        "ALLOWED_HOSTS",
        "ACCESS_TOKEN_ACTIVE_KID",
        "DATABASE_URL",
        "ACCESS_TOKEN_KEYS",
        "CORS_ALLOWED_ORIGINS",
        "PLATFORM_CONTRACT_EXPECTED_FINGERPRINT",
        "REDIS_URL",
        "REDIS_USERNAME",
        "SECURITY_TOKEN_HMAC_KEY",
        "SECURITY_HEADERS_ENABLED",
        "TRUSTED_PROXY_CIDRS",
    }
    missing = sorted(required - names)
    tracked = subprocess.check_output(("git", "ls-files"), text=True).splitlines()
    forbidden = sorted(
        path for path in tracked if path in {".env", ".env.preview", ".env.production"}
    )
    leaked = scan_tracked_files([Path(path) for path in tracked])
    if missing or forbidden or leaked:
        if missing:
            print("Missing required secret declarations: " + ", ".join(missing))
        if forbidden:
            print("Runtime secret files are tracked: " + ", ".join(forbidden))
        for path, pattern in leaked:
            print(f"Potential {pattern} secret material in tracked file: {path}")
        return 1
    print(f"Required secret declarations present: {len(required)}")
    print("Runtime secret files tracked: 0")
    print("High-confidence tracked secret patterns found: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
