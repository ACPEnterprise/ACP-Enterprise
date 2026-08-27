import pytest
from app.operational_migration.hcp_owner_disposition import (
    DispositionAlternative,
    NonProductionTarget,
    OwnerDecisionGroup,
    seal_owner_packet,
)


def alternative(identifier: str) -> DispositionAlternative:
    return DispositionAlternative(identifier, "preserve_source", "reviewed effect", True)


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
