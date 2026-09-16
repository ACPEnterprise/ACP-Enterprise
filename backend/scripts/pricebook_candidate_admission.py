"""Admit the sealed All County candidate packet as native Price Book drafts."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID

from app.database.session import AsyncSessionFactory
from app.price_book.candidate_admission import admit_candidate_plan, classify_packet


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run(args: argparse.Namespace) -> None:
    configuration = json.loads(args.configuration.read_text())
    readiness = json.loads(args.readiness.read_text())
    plan = classify_packet(
        configuration,
        readiness,
        packet_digest=file_digest(args.configuration),
        readiness_digest=file_digest(args.readiness),
    )
    async with AsyncSessionFactory() as session:
        admitted = await admit_candidate_plan(
            session,
            company_id=args.company_id,
            actor_user_id=args.actor_user_id,
            plan=plan,
            idempotency_key=args.idempotency_key,
        )
    print(
        json.dumps(
            {
                "admission_run_id": str(admitted.id),
                "configuration_version": admitted.configuration_version,
                "packet_digest": admitted.packet_digest,
                "result_counts": admitted.result_counts,
            },
            indent=2,
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay-safe All County Price Book draft admission"
    )
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--company-id", type=UUID, required=True)
    parser.add_argument("--actor-user-id", type=UUID, required=True)
    parser.add_argument("--idempotency-key", required=True)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
