#!/usr/bin/env python3
"""Validate the single committed release-qualification configuration."""

from __future__ import annotations

import re
from pathlib import Path


def violations(root: Path) -> list[str]:
    compose = root / "docker-compose.release-qualification.yml"
    content = compose.read_text(encoding="utf-8")
    problems: list[str] = []
    candidates = sorted(root.glob("*release*qualification*.yml"))
    if candidates != [compose]:
        problems.append(
            "release qualification must have exactly one Compose configuration"
        )
    if "ENVIRONMENT: test" not in content:
        problems.append("qualifier must select the canonical test environment")
    if content.count("POSTGRES_PASSWORD_FILE: /run/secrets/postgres-password") != 2:
        problems.append("source and restore PostgreSQL must use password-file secrets")
    if "release_qualification_postgres_password:" not in content:
        problems.append("PostgreSQL password secret must be declared")
    if content.count("POSTGRES_INITDB_ARGS: --encoding=UTF8") != 2:
        problems.append("source and restore PostgreSQL must initialize as UTF8")
    if "internal: true" not in content:
        problems.append("qualification network must be internal")
    if re.search(r"(?im)^\s*(?:POSTGRES|REDIS|DATABASE)_PASSWORD\s*:", content):
        problems.append(
            "database or cache password is committed instead of file-backed"
        )
    if re.search(r"postgresql[^\s]*://[^\s:@]+:(?!\$\$\{)[^\s@]+@", content):
        problems.append("database URL contains committed credentials")
    if (
        "qualification-postgres:" not in content
        or "qualification-restore-postgres:" not in content
    ):
        problems.append(
            "source and restore PostgreSQL need separate qualification volumes"
        )
    expected_command = "exec python -m scripts.qualify_release_database"
    if expected_command not in content:
        problems.append("qualifier must use the fresh-database enforcement module")
    return problems


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    problems = violations(root)
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print("canonical_configs=1")
    print("committed_secret_values=0")
    print("postgres_passwords=secret-indirected")
    print("postgres_encoding=UTF8")
    print("source_restore_volumes=isolated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
