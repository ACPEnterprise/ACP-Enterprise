#!/usr/bin/env python3
"""Validate secret declarations and tracked-file custody without printing values."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

SECRET_SIGNATURES = {
    "aws_access_key": re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    "github_token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    "gitlab_token": re.compile(rb"glpat-[A-Za-z0-9_-]{20,}"),
    "google_api_key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "npm_token": re.compile(rb"npm_[A-Za-z0-9]{36}"),
    "sendgrid_api_key": re.compile(
        rb"SG\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"
    ),
    "slack_token": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "stripe_live_key": re.compile(rb"sk_live_[A-Za-z0-9]{16,}"),
    "twilio_api_key": re.compile(rb"SK[0-9a-fA-F]{32}"),
    "private_key": re.compile(
        rb"-----BEGIN (?:(?:RSA|EC|OPENSSH|ENCRYPTED) )?PRIVATE KEY-----"
        rb"[A-Za-z0-9+/=\r\n]{64,}"
        rb"-----END (?:(?:RSA|EC|OPENSSH|ENCRYPTED) )?PRIVATE KEY-----"
    ),
}


def tracked_secret_findings(repository_root: Path, tracked: list[str]) -> list[str]:
    findings: list[str] = []
    for relative in tracked:
        path = repository_root / relative
        if not path.is_file():
            continue
        content = path.read_bytes()
        if b"\x00" in content:
            continue
        for classification, signature in SECRET_SIGNATURES.items():
            if signature.search(content):
                findings.append(f"{relative} ({classification})")
    return sorted(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-example", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
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
    repository_root = args.repository_root.resolve()
    tracked = subprocess.check_output(
        ("git", "-C", str(repository_root), "ls-files"), text=True
    ).splitlines()
    forbidden = sorted(
        path for path in tracked if path in {".env", ".env.preview", ".env.production"}
    )
    secret_findings = tracked_secret_findings(repository_root, tracked)
    if missing or forbidden or secret_findings:
        if missing:
            print("Missing required secret declarations: " + ", ".join(missing))
        if forbidden:
            print("Runtime secret files are tracked: " + ", ".join(forbidden))
        if secret_findings:
            print("Credential signatures detected in tracked paths:")
            for finding in secret_findings:
                print(f"- {finding}")
        return 1
    print(f"Required secret declarations present: {len(required)}")
    print("Runtime secret files tracked: 0")
    print("Tracked credential signatures detected: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
