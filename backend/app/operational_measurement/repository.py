"""Append-only persistence boundary for operational measurement packets."""

from dataclasses import asdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .foundation import MeasurementPacket, _jsonable
from .models import OperationalMeasurementSnapshot


async def persist_packet(
    session: AsyncSession, packet: MeasurementPacket, *, created_by_user_id: UUID
) -> OperationalMeasurementSnapshot:
    record = OperationalMeasurementSnapshot(
        id=packet.packet_id,
        company_id=packet.company_id,
        branch_id=packet.branch_id,
        period_start=packet.period_start,
        period_end=packet.period_end,
        contract_version=packet.contract_version,
        facts=_jsonable(
            [asdict(item) | {"fact_digest": item.digest} for item in packet.facts]
        ),
        attribution=_jsonable([asdict(item) for item in packet.attribution]),
        source_matrix=list(packet.source_matrix),
        completeness=packet.readiness(),
        snapshot_digest=packet.digest,
        predecessor_snapshot_id=packet.predecessor_packet_id,
        correction_reason=packet.correction_reason,
        source_version_digest=packet.source_version_digest,
        created_by_user_id=created_by_user_id,
        created_at=packet.created_at,
    )
    session.add(record)
    await session.flush()
    return record
