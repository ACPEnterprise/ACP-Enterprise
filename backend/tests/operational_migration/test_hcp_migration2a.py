from uuid import UUID

import pytest

from app.operational_migration.hcp_migration2a import (
    Migration2ReleaseGate,
    UnlinkedEstimateEvidenceCommand,
    initialize_rehearsal_actor,
)
from app.operational_migration.hcp_owner_disposition import NonProductionTarget


def command(**overrides: object) -> UnlinkedEstimateEvidenceCommand:
    values: dict[str, object] = {
        "native_estimate_id": "csr_fixture",
        "source_digest": "a" * 64,
        "package_digest": "b" * 64,
        "owner_binding_digest": "c" * 64,
        "native_customer_id": "cus_fixture",
        "native_service_location_id": "adr_fixture",
        "source_status": "scheduled",
        "option_evidence": ({"id": "est_fixture", "status": "approved"},),
        "source_timestamps": {"created_at": "2026-08-27T00:00:00Z"},
        "source_context": {"fixture": True},
    }
    values.update(overrides)
    return UnlinkedEstimateEvidenceCommand(**values)  # type: ignore[arg-type]


def test_unlinked_evidence_identity_and_digest_are_deterministic() -> None:
    first = command()
    second = command()
    first.validate()
    assert first.evidence_digest == second.evidence_digest
    assert first.disposition == "UNLINKED_NON_OPERATIONAL_ESTIMATE"


def test_release_gate_fails_closed_on_real_business_rows() -> None:
    ready = Migration2ReleaseGate(True, True, True, True, True, False)
    blocked = Migration2ReleaseGate(True, True, True, True, True, True)
    assert ready.ready
    assert len(ready.digest) == 64
    assert not blocked.ready


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("native_estimate_id", "estimate-without-native-prefix"),
        ("source_digest", "short"),
        ("native_customer_id", "name-only-match"),
        ("native_service_location_id", "fuzzy-location"),
        ("disposition", "OPERATIONAL_ESTIMATE"),
    ),
)
def test_unlinked_evidence_rejects_unsafe_identity_or_disposition(
    field: str, value: str
) -> None:
    with pytest.raises(ValueError):
        command(**{field: value}).validate()


@pytest.mark.asyncio
async def test_actor_initializer_rejects_non_rehearsal_target_before_database_use() -> None:
    target = NonProductionTarget(
        "production",
        "postgresql+asyncpg://user:secret@production/acp_hcp_rehearsal_import",
        "acp_hcp_rehearsal_import",
        True,
        False,
        True,
    )
    with pytest.raises(ValueError, match="migration_rehearsal"):
        await initialize_rehearsal_actor(
            None,  # type: ignore[arg-type]
            target=target,
            company_id=UUID(int=1),
            branch_id=UUID(int=2),
        )
