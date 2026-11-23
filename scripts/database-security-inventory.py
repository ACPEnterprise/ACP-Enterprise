#!/usr/bin/env python3
"""Read-only PostgreSQL tenant-scope inventory.

The output intentionally contains schema metadata only: table names, direct
scope columns, and foreign-key relationships.  It never reads business rows.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

import psycopg


def _query(dsn: str) -> list[tuple[str, str, str]]:
    sql = """
SELECT c.relname,
       string_agg(a.attname, ',' ORDER BY a.attnum),
       COALESCE(string_agg(DISTINCT att.attname || '->' || c2.relname || '.' || att2.attname, ','), '')
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
LEFT JOIN pg_constraint fk ON fk.conrelid = c.oid AND fk.contype = 'f'
LEFT JOIN LATERAL unnest(fk.conkey) WITH ORDINALITY k(attnum, ord) ON true
LEFT JOIN pg_attribute att ON att.attrelid = c.oid AND att.attnum = k.attnum
LEFT JOIN pg_class c2 ON c2.oid = fk.confrelid
LEFT JOIN LATERAL unnest(fk.confkey) WITH ORDINALITY k2(attnum, ord) ON k2.ord = k.ord
LEFT JOIN pg_attribute att2 ON att2.attrelid = c2.oid AND att2.attnum = k2.attnum
WHERE n.nspname = 'public' AND c.relkind = 'r'
GROUP BY c.relname ORDER BY c.relname;
"""
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(sql)
        return [
            (str(table), str(columns), str(foreign_keys))
            for table, columns, foreign_keys in cursor.fetchall()
        ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records: list[dict[str, object]] = []
    for table, columns, foreign_keys in _query(args.dsn):
        names = set(columns.split(","))
        if {"company_id", "branch_id"} <= names:
            scope = "direct_company_and_branch"
        elif "company_id" in names:
            scope = "direct_company"
        elif "branch_id" in names:
            scope = "direct_branch"
        else:
            scope = "shared_or_relational"
        records.append(
            {
                "table": table,
                "scope": scope,
                "columns": sorted(names),
                "foreign_keys": sorted(filter(None, foreign_keys.split(","))),
            }
        )
    counts = Counter(str(record["scope"]) for record in records)
    payload = {
        "contract": "twelvehats-database-tenant-scope-inventory/v1",
        "table_count": len(records),
        "direct_tenant_table_count": sum(
            counts[name]
            for name in (
                "direct_company",
                "direct_company_and_branch",
                "direct_branch",
            )
        ),
        "scope_counts": dict(sorted(counts.items())),
        "tables": records,
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
