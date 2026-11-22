import asyncio
import json
from pathlib import Path

from app.database.session import AsyncSessionFactory
from app.operational_migration.models import JobSourceIdentity
from sqlalchemy import select


async def main():
    packet = json.loads(
        Path(
            "/var/lib/acp-qbo-production-evidence/hcp-runtime-2307/quarantine/runtime-binding-quarantined-packet.json"
        ).read_text()
    )
    recs = packet["records"]
    from collections import Counter

    print(
        json.dumps(
            {
                "domains": Counter(str(x.get("domain")) for x in recs),
                "dispositions": Counter(str(x.get("disposition")) for x in recs),
            },
            sort_keys=True,
        )
    )
    async with AsyncSessionFactory() as s:
        rows = (await s.scalars(select(JobSourceIdentity))).all()
        by = {(str(x.source_system), str(x.source_job_id)): x for x in rows}
        for i, x in enumerate(recs):
            if str(x.get("domain")) == "estimate" and str(
                x.get("disposition", "")
            ).upper() in {"CREATE", "UPDATE", "REPLAY"}:
                job = next(
                    (p for p in x.get("parent_keys", []) if p.get("domain") == "job"),
                    None,
                )
                print(
                    json.dumps(
                        {
                            "first_estimate": x["source_id"],
                            "estimate_index": i,
                            "parents": x.get("parent_keys", []),
                            "job_record_ids": [
                                r["source_id"] for r in recs if r["domain"] == "job"
                            ][:3],
                        },
                        sort_keys=True,
                    )
                )
                break
                key = ("housecall_pro_source4", str(job["source_id"])) if job else None
                if i > 0 and key:
                    job_record = next(
                        (
                            r
                            for r in recs
                            if r["domain"] == "job" and r["source_id"] == key[1]
                        ),
                        None,
                    )
                    if job_record is not None:
                        print(
                            json.dumps(
                                {
                                    "index": i,
                                    "estimate": x["source_id"],
                                    "estimate_disp": x["disposition"],
                                    "job_key": key,
                                    "job_disposition": job_record.get("disposition"),
                                    "job_index": next(
                                        (
                                            j
                                            for j, r in enumerate(recs)
                                            if r is job_record
                                        ),
                                        None,
                                    ),
                                    "identity_exists": key in by,
                                },
                                sort_keys=True,
                            )
                        )
                        break
                    break


asyncio.run(main())
