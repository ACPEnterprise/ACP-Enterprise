import asyncio
import json
from pathlib import Path

from app.database.session import AsyncSessionFactory
from sqlalchemy import text

TABLES = {
    "customer": ("customer_source_identities", "source_customer_id", "NULL"),
    "service_location": (
        "service_location_source_identities",
        "source_location_id",
        "source_digest",
    ),
    "job": ("operational_migration_job_source_identities", "source_job_id", "NULL"),
    "appointment": (
        "operational_migration_appointment_source_identities",
        "source_appointment_id",
        "NULL",
    ),
}


async def main():
    packet = json.loads(
        Path(
            "/var/lib/acp-qbo-production-evidence/hcp-runtime-2307/quarantine/runtime-binding-quarantined-packet.json"
        ).read_text()
    )
    async with AsyncSessionFactory() as s:
        for item in packet["records"]:
            if (
                str(item.get("disposition", "")).upper() != "UPDATE"
                or item["domain"] not in TABLES
            ):
                continue
            table, field, digest_field = TABLES[item["domain"]]
            if item["domain"] == "customer":
                q = text(
                    f"SELECT 1 AS present, NULL AS external_metadata, NULL AS source_digest FROM {table} WHERE company_id=:company AND branch_id=:branch AND source_system=:source AND {field}=:sid LIMIT 1"
                )
            else:
                q = text(
                    f"SELECT external_metadata, {digest_field} AS source_digest FROM {table} WHERE company_id=:company AND branch_id=:branch AND source_system=:source AND {field}=:sid LIMIT 1"
                )
            row = (
                (
                    await s.execute(
                        q,
                        {
                            "company": "a56fc415-563b-459c-913f-2e6183109119",
                            "branch": "887f413a-70dc-4ab1-98aa-8e84f4e7efd0",
                            "source": "housecall_pro_source4",
                            "sid": item["source_id"],
                        },
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                continue
            md = row.get("external_metadata") or {}
            actual = md.get("current_overlay_source_digest") or row.get("source_digest")
            expected = item.get("prior_source_digest")
            if actual != expected:
                print(
                    json.dumps(
                        {
                            "domain": item["domain"],
                            "source_id": item["source_id"],
                            "expected_prior": expected,
                            "actual": actual,
                            "metadata": md,
                        },
                        sort_keys=True,
                    )
                )
                break


asyncio.run(main())
