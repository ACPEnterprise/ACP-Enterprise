"""Publish the verified owner-approved Sales Forward agreement exactly once."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.access_agreements.models import AccessAgreementDocument
from app.database.session import AsyncSessionFactory, engine
from sqlalchemy import select

AGREEMENT_CODE = "TWELVEHATS_SALES_DEMO_ACCESS"
AGREEMENT_TITLE = "TWELVEHATS — CONFIDENTIALITY, NON-DISCLOSURE, INTELLECTUAL PROPERTY PROTECTION & RESTRICTED SYSTEM ACCESS AGREEMENT"
AGREEMENT_VERSION = 1
EXPECTED_SHA256 = "aaf90aafe6aa6e10ef1ae7bc9d002634cad7fd36018a9279d77153fd5d804fd6"
DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "docs/legal/TwelveHats_NDA_v1.0_Approved_Source.md"
)


async def publish(
    *, source: Path, created_by_user_id: UUID, publish_document: bool
) -> dict[str, object]:
    content_bytes = source.read_bytes()
    digest = hashlib.sha256(content_bytes).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"Agreement source digest mismatch: {digest}")
    content = content_bytes.decode("utf-8")
    async with AsyncSessionFactory() as session, session.begin():
        existing = await session.scalar(
            select(AccessAgreementDocument).where(
                AccessAgreementDocument.code == AGREEMENT_CODE,
                AccessAgreementDocument.version == AGREEMENT_VERSION,
            )
        )
        if existing is not None:
            if (
                existing.content_sha256 != digest
                or existing.content.encode("utf-8") != content_bytes
            ):
                raise ValueError(
                    "Existing agreement version has different immutable content."
                )
            return {
                "action": "already_published"
                if existing.status == "published"
                else "already_present",
                "agreement_id": str(existing.id),
                "version": existing.version,
                "sha256": digest,
                "status": existing.status,
            }
        if not publish_document:
            return {
                "action": "verified_only",
                "version": AGREEMENT_VERSION,
                "sha256": digest,
                "status": "not_published",
            }
        document = AccessAgreementDocument(
            id=uuid4(),
            code=AGREEMENT_CODE,
            title=AGREEMENT_TITLE,
            version=AGREEMENT_VERSION,
            effective_at=datetime.now(UTC),
            content=content,
            content_sha256=digest,
            status="published",
            mandatory=True,
            created_by_user_id=created_by_user_id,
        )
        session.add(document)
        await session.flush()
        return {
            "action": "published",
            "agreement_id": str(document.id),
            "version": document.version,
            "sha256": digest,
            "status": document.status,
        }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    result.add_argument("--created-by-user-id", type=UUID, required=True)
    result.add_argument(
        "--publish",
        action="store_true",
        help="Commit the verified document as the mandatory published version.",
    )
    return result


async def main() -> None:
    try:
        args = parser().parse_args()
        result = await publish(
            source=args.source,
            created_by_user_id=args.created_by_user_id,
            publish_document=args.publish,
        )
        print(result)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
