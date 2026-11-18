"""Encrypted append-only persistence for blind Payroll replay evidence."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.payroll.blind_replay import (
    BlindComparison,
    BlindReplayError,
    BlindReplayInput,
    FrozenShadowPayroll,
    QBOAnswerKey,
    verify_frozen_result,
)
from app.payroll.contracts import canonical_digest
from app.payroll.models import (
    PayrollQBOAnswerKeyRecord,
    PayrollShadowComparisonRecord,
    PayrollShadowSnapshotRecord,
)
from app.payroll.tax_authority import ProtectedPayrollInputCipher


class BlindReplayEvidenceService:
    """Store sensitive values as ciphertext and expose only safe metadata."""

    def __init__(self, cipher: ProtectedPayrollInputCipher) -> None:
        self._cipher = cipher

    async def freeze(
        self,
        session: AsyncSession,
        *,
        packet: BlindReplayInput,
        result: FrozenShadowPayroll,
        actor_user_id: UUID,
        replay_identity: str,
        commit: bool = True,
    ) -> PayrollShadowSnapshotRecord:
        if not replay_identity.strip():
            raise BlindReplayError("freeze replay identity is required")
        if (
            packet.company_id != result.company_id
            or not result.frozen_before_qbo_reveal
        ):
            raise BlindReplayError(
                "calculation cannot be admitted as a frozen shadow result"
            )
        verify_frozen_result(result)
        if canonical_digest(asdict(packet)) != result.input_digest:
            raise BlindReplayError(
                "frozen result does not match the supplied input packet"
            )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"payroll-shadow-freeze:{packet.company_id}:{replay_identity}"},
        )
        replay = await session.scalar(
            select(PayrollShadowSnapshotRecord).where(
                PayrollShadowSnapshotRecord.company_id == packet.company_id,
                PayrollShadowSnapshotRecord.replay_identity == replay_identity,
            )
        )
        if replay is not None:
            if (
                replay.input_digest != result.input_digest
                or replay.result_digest != result.result_digest
            ):
                raise BlindReplayError(
                    "freeze replay identity conflicts with prior evidence"
                )
            return replay
        version = (
            await session.scalar(
                select(func.max(PayrollShadowSnapshotRecord.snapshot_version)).where(
                    PayrollShadowSnapshotRecord.company_id == packet.company_id,
                    PayrollShadowSnapshotRecord.input_digest == result.input_digest,
                )
            )
            or 0
        ) + 1
        payload: dict[str, object] = {
            "input": asdict(packet),
            "result": asdict(result),
        }
        key_id, nonce, ciphertext, content_digest = self._cipher.encrypt(
            company_id=packet.company_id, payload=payload
        )
        value = PayrollShadowSnapshotRecord(
            company_id=packet.company_id,
            calculation_id=result.calculation_id,
            snapshot_version=version,
            period_start=result.period_start,
            period_end=result.period_end,
            pay_date=result.pay_date,
            input_digest=result.input_digest,
            engine_version=result.engine_version,
            engine_sha=result.engine_sha,
            tax_table_version=result.tax_table_version,
            key_id=key_id,
            nonce=nonce,
            ciphertext=ciphertext,
            content_digest=content_digest,
            result_digest=result.result_digest,
            frozen_before_qbo_reveal=True,
            replay_identity=replay_identity,
            created_by_user_id=actor_user_id,
            frozen_at=result.calculated_at,
        )
        session.add(value)
        if commit:
            await session.commit()
            await session.refresh(value)
        else:
            await session.flush()
        return value

    async def import_answer_key(
        self,
        session: AsyncSession,
        *,
        snapshot: PayrollShadowSnapshotRecord,
        answer_key: QBOAnswerKey,
        actor_user_id: UUID,
        commit: bool = True,
    ) -> PayrollQBOAnswerKeyRecord:
        if (
            snapshot.company_id != answer_key.company_id
            or not snapshot.frozen_before_qbo_reveal
        ):
            raise BlindReplayError("answer key requires a prior Company-scoped freeze")
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {
                "key": f"payroll-answer-key:{answer_key.company_id}:{answer_key.source_file_digest}"
            },
        )
        existing = await session.scalar(
            select(PayrollQBOAnswerKeyRecord).where(
                PayrollQBOAnswerKeyRecord.company_id == answer_key.company_id,
                PayrollQBOAnswerKeyRecord.source_file_digest
                == answer_key.source_file_digest,
            )
        )
        if existing is not None:
            if (
                existing.shadow_snapshot_id != snapshot.id
                or existing.answer_key_digest != answer_key.answer_key_digest
            ):
                raise BlindReplayError("answer-key file conflicts with prior import")
            return existing
        key_id, nonce, ciphertext, content_digest = self._cipher.encrypt(
            company_id=answer_key.company_id, payload=asdict(answer_key)
        )
        value = PayrollQBOAnswerKeyRecord(
            company_id=answer_key.company_id,
            shadow_snapshot_id=snapshot.id,
            answer_key_id=answer_key.answer_key_id,
            source_file_digest=answer_key.source_file_digest,
            report_type=answer_key.report_type,
            key_id=key_id,
            nonce=nonce,
            ciphertext=ciphertext,
            content_digest=content_digest,
            answer_key_digest=answer_key.answer_key_digest,
            imported_by_user_id=actor_user_id,
            imported_at=answer_key.imported_at,
        )
        session.add(value)
        if commit:
            await session.commit()
            await session.refresh(value)
        else:
            await session.flush()
        return value

    async def persist_comparison(
        self,
        session: AsyncSession,
        *,
        snapshot: PayrollShadowSnapshotRecord,
        answer_key_record: PayrollQBOAnswerKeyRecord,
        comparison: BlindComparison,
        actor_user_id: UUID,
        commit: bool = True,
    ) -> PayrollShadowComparisonRecord:
        if (
            snapshot.company_id != answer_key_record.company_id
            or snapshot.id != answer_key_record.shadow_snapshot_id
            or snapshot.calculation_id != comparison.calculation_id
            or answer_key_record.answer_key_id != comparison.answer_key_id
        ):
            raise BlindReplayError("comparison evidence scope is inconsistent")
        existing = await session.scalar(
            select(PayrollShadowComparisonRecord).where(
                PayrollShadowComparisonRecord.company_id == snapshot.company_id,
                PayrollShadowComparisonRecord.shadow_snapshot_id == snapshot.id,
                PayrollShadowComparisonRecord.answer_key_record_id
                == answer_key_record.id,
            )
        )
        if existing is not None:
            if existing.comparison_digest != comparison.comparison_digest:
                raise BlindReplayError("comparison pair conflicts with prior evidence")
            return existing
        key_id, nonce, ciphertext, content_digest = self._cipher.encrypt(
            company_id=snapshot.company_id, payload=asdict(comparison)
        )
        value = PayrollShadowComparisonRecord(
            company_id=snapshot.company_id,
            shadow_snapshot_id=snapshot.id,
            answer_key_record_id=answer_key_record.id,
            key_id=key_id,
            nonce=nonce,
            ciphertext=ciphertext,
            content_digest=content_digest,
            comparison_digest=comparison.comparison_digest,
            unexplained_count=comparison.unexplained_count,
            created_by_user_id=actor_user_id,
        )
        session.add(value)
        if commit:
            await session.commit()
            await session.refresh(value)
        else:
            await session.flush()
        return value
