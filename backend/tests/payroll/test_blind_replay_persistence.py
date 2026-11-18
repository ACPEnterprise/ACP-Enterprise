from datetime import timedelta

import pytest
from app.payroll.blind_replay import (
    BlindReplayError,
    calculate_shadow_payroll,
    compare_frozen_to_qbo,
    import_qbo_answer_key_csv,
)
from app.payroll.blind_replay_persistence import BlindReplayEvidenceService
from app.payroll.models import (
    PayrollQBOAnswerKeyRecord,
    PayrollShadowComparisonRecord,
    PayrollShadowSnapshotRecord,
)
from app.payroll.tax_authority import ProtectedPayrollInputCipher
from sqlalchemy import func, select

from tests.payroll.test_blind_replay import (
    ENGINE_SHA,
    WHEN,
    _answer_csv,
    employee,
    packet,
)

pytest_plugins = ("tests.accounting.test_service_persistence",)


@pytest.mark.asyncio
async def test_encrypted_freeze_answer_key_and_comparison_are_append_only(
    accounting_fixture,
) -> None:
    factory, company, _branch, contexts, _period, _accounts = accounting_fixture
    actor_id = contexts[0].user.id
    cipher = ProtectedPayrollInputCipher(
        active_key_id="shadow-test", keys={"shadow-test": b"s" * 32}
    )
    service = BlindReplayEvidenceService(cipher)
    source = packet(employee())
    source = source.__class__(
        company.id,
        source.period_start,
        source.period_end,
        source.pay_date,
        source.pay_frequency,
        source.employees,
        source.packet_provenance,
    )
    first = calculate_shadow_payroll(source, engine_sha=ENGINE_SHA, calculated_at=WHEN)
    async with factory() as session:
        snapshot = await service.freeze(
            session,
            packet=source,
            result=first,
            actor_user_id=actor_id,
            replay_identity="blind-freeze-1",
        )
        assert snapshot.snapshot_version == 1
        assert b"Synthetic Technician" not in snapshot.ciphertext
        unsealed = cipher.decrypt(
            company_id=company.id,
            key_id=snapshot.key_id,
            nonce=snapshot.nonce,
            ciphertext=snapshot.ciphertext,
            expected_digest=snapshot.content_digest,
        )
        assert unsealed["result"]["result_digest"] == first.result_digest
        replay = await service.freeze(
            session,
            packet=source,
            result=first,
            actor_user_id=actor_id,
            replay_identity="blind-freeze-1",
        )
        assert replay.id == snapshot.id

        answer = import_qbo_answer_key_csv(
            _answer_csv(first),
            company_id=company.id,
            report_type="Payroll Details",
            frozen_result=first,
        )
        answer_record = await service.import_answer_key(
            session,
            snapshot=snapshot,
            answer_key=answer,
            actor_user_id=actor_id,
        )
        answer_replay = await service.import_answer_key(
            session,
            snapshot=snapshot,
            answer_key=answer,
            actor_user_id=actor_id,
        )
        assert answer_replay.id == answer_record.id
        comparison = compare_frozen_to_qbo(first, answer)
        comparison_record = await service.persist_comparison(
            session,
            snapshot=snapshot,
            answer_key_record=answer_record,
            comparison=comparison,
            actor_user_id=actor_id,
        )
        comparison_replay = await service.persist_comparison(
            session,
            snapshot=snapshot,
            answer_key_record=answer_record,
            comparison=comparison,
            actor_user_id=actor_id,
        )
        assert comparison_record.id == comparison_replay.id
        assert comparison_record.unexplained_count == 0

    second = calculate_shadow_payroll(
        source, engine_sha=ENGINE_SHA, calculated_at=WHEN + timedelta(minutes=1)
    )
    async with factory() as session:
        successor = await service.freeze(
            session,
            packet=source,
            result=second,
            actor_user_id=actor_id,
            replay_identity="blind-freeze-2",
        )
        assert successor.snapshot_version == 2
        assert successor.id != snapshot.id
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PayrollShadowSnapshotRecord)
                .where(PayrollShadowSnapshotRecord.company_id == company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PayrollQBOAnswerKeyRecord)
                .where(PayrollQBOAnswerKeyRecord.company_id == company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PayrollShadowComparisonRecord)
                .where(PayrollShadowComparisonRecord.company_id == company.id)
            )
            == 1
        )
        with pytest.raises(BlindReplayError, match="conflicts"):
            await service.freeze(
                session,
                packet=source,
                result=second,
                actor_user_id=actor_id,
                replay_identity="blind-freeze-1",
            )
        await session.rollback()
