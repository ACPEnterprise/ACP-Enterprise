from datetime import datetime, timezone

import pytest
from app.operational_migration.hcp_owner_disposition import (
    DispositionAlternative,
    NonProductionTarget,
    OwnerDecisionBinding,
    OwnerDecisionGroup,
    OwnerDecisionRecordBinding,
    RecordDisposition,
    seal_owner_packet,
)


def alternative(identifier: str) -> DispositionAlternative:
    return DispositionAlternative(
        identifier, "preserve_source", "reviewed effect", True
    )


def group(identifier: str) -> OwnerDecisionGroup:
    return OwnerDecisionGroup(
        identifier,
        2,
        "owner judgment is required",
        "a" * 64,
        "preserve",
        (alternative("preserve"), alternative("hold")),
        ("b" * 64,),
    )


def test_owner_packet_is_order_independent_and_machine_bindable() -> None:
    first = group("HCP1A.JOBS.V1")
    second = group("HCP1A.EMPLOYEES.V1")
    assert seal_owner_packet((first, second)) == seal_owner_packet((second, first))
    assert len(first.binding_digest) == 64


def test_owner_packet_rejects_implicit_or_duplicate_decisions() -> None:
    with pytest.raises(ValueError, match="recommended default"):
        OwnerDecisionGroup(
            "HCP1A.BAD.V1",
            1,
            "reason",
            "a" * 64,
            "missing",
            (alternative("available"),),
            (),
        )
    with pytest.raises(ValueError, match="duplicate owner decision"):
        seal_owner_packet((group("HCP1A.JOBS.V1"), group("HCP1A.JOBS.V1")))


def test_non_production_target_fails_closed() -> None:
    target = NonProductionTarget(
        "migration_rehearsal",
        "postgresql+asyncpg://user:secret@127.0.0.1:55432/acp_hcp_rehearsal_import",
        "acp_hcp_rehearsal_import",
        False,
        False,
        True,
    )
    assert len(target.validate()) == 64
    with pytest.raises(ValueError, match="not isolated"):
        NonProductionTarget(
            "migration_rehearsal",
            "postgresql://user:secret@production-db/acp_hcp_rehearsal_import",
            "acp_hcp_rehearsal_import",
            False,
            False,
            True,
        ).validate()


def test_owner_binding_requires_exact_reviewed_digest_and_alternative() -> None:
    decision = group("HCP1A.JOBS.V1")
    binding = OwnerDecisionBinding.bind(
        decision,
        binding_digest=decision.binding_digest,
        selected_alternative="hold",
        authority="owner directive",
        bound_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    assert binding.group_identifier == decision.identifier
    assert len(binding.receipt_digest) == 64

    with pytest.raises(ValueError, match="binding digest"):
        OwnerDecisionBinding.bind(
            decision,
            binding_digest="0" * 64,
            selected_alternative="hold",
            authority="owner directive",
        )
    with pytest.raises(ValueError, match="not defined"):
        OwnerDecisionBinding.bind(
            decision,
            binding_digest=decision.binding_digest,
            selected_alternative="invented",
            authority="owner directive",
        )


def test_mixed_record_binding_requires_complete_unique_native_id_set() -> None:
    decision = group("HCP1A.EMPLOYEES.V1")
    binding = OwnerDecisionRecordBinding.bind(
        decision,
        binding_digest=decision.binding_digest,
        record_dispositions=(
            RecordDisposition("pro_2", "hold", "system identity"),
            RecordDisposition("pro_1", "preserve", "human candidate"),
        ),
        authority="owner directive",
    )
    assert [item.native_id for item in binding.record_dispositions] == [
        "pro_1",
        "pro_2",
    ]

    with pytest.raises(ValueError, match="every affected"):
        OwnerDecisionRecordBinding.bind(
            decision,
            binding_digest=decision.binding_digest,
            record_dispositions=(
                RecordDisposition("pro_1", "preserve", "human candidate"),
            ),
            authority="owner directive",
        )
