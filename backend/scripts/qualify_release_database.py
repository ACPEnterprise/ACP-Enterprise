"""Fail-closed zero-to-head qualification against a pristine PostgreSQL DB."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Sequence
from typing import Any

import psycopg
from app.core.config import settings

CONTRACT = "enterprise-release.fresh-database/v1"
APPLICATION_OBJECTS_SQL = """
SELECT n.nspname, c.relname, c.relkind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
ORDER BY n.nspname, c.relname, c.relkind
"""


def sync_database_url(url: str) -> str:
    return url.replace("+asyncpg", "")


def application_objects(connection: psycopg.Connection[Any]) -> tuple[str, ...]:
    with connection.cursor() as cursor:
        cursor.execute(APPLICATION_OBJECTS_SQL)
        return tuple(f"{schema}.{name}:{kind}" for schema, name, kind in cursor)


def require_pristine_database(objects: Sequence[str]) -> None:
    if objects:
        raise RuntimeError(
            "qualification database is not pristine; found application objects: "
            + ", ".join(objects[:10])
        )


def require_utf8_database(encoding: str) -> None:
    if encoding != "UTF8":
        raise RuntimeError(f"qualification database must use UTF8, observed {encoding}")


def run_alembic(*arguments: str) -> str:
    completed = subprocess.run(
        ("alembic", *arguments),
        check=False,
        capture_output=True,
        text=True,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode:
        raise RuntimeError(
            f"alembic {' '.join(arguments)} failed with exit code "
            f"{completed.returncode}: {output.strip()}"
        )
    return output


def main() -> int:
    url = sync_database_url(settings.database_url)
    with psycopg.connect(url) as connection:
        encoding_row = connection.execute("SHOW server_encoding").fetchone()
        if encoding_row is None:
            raise RuntimeError("qualification database did not report its encoding")
        encoding = str(encoding_row[0])
        require_utf8_database(encoding)
        before = application_objects(connection)
    require_pristine_database(before)

    heads_output = run_alembic("heads")
    heads = tuple(
        line.strip().split()[0] for line in heads_output.splitlines() if line.strip()
    )
    if len(heads) != 1:
        raise RuntimeError(f"expected exactly one Alembic head, observed {len(heads)}")

    run_alembic("upgrade", "head")
    current_output = run_alembic("current")
    if "(head)" not in current_output:
        raise RuntimeError("fresh database did not reach the Alembic head")
    run_alembic("check")

    with psycopg.connect(url) as connection:
        after = application_objects(connection)
    if not after:
        raise RuntimeError("zero-to-head migration produced no application objects")

    evidence = {
        "contract": CONTRACT,
        "database_was_pristine": True,
        "database_encoding": encoding,
        "head": heads[0],
        "object_count_after_upgrade": len(after),
        "schema_drift": False,
        "zero_to_head": True,
    }
    evidence["digest"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
