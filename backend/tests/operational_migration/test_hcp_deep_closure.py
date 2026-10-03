import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.operational_migration.hcp_deep_closure import (
    REQUIRED_SOURCE_FAMILIES,
    EmployeeSourceEvidence,
    HistoricalDomainEvidence,
    MetadataEvidence,
    build_packet,
    metadata_from_source,
    persist_packet,
)
from app.platform.permissions.codes import MigrationPermission


def _domain(**changes) -> HistoricalDomainEvidence:
    values = {
        "source_family": "jobs",
        "source_population": 10,
        "acquired_population": 10,
        "admitted_bound": 7,
        "history_only": 1,
        "held": 1,
        "conflict": 0,
        "unknown": 1,
        "unexplained": 0,
        "as_of": datetime(2026, 10, 3, tzinfo=timezone.utc),
        "source_digest": "a" * 64,
        "replay_digest": "b" * 64,
    }
    values.update(changes)
    return HistoricalDomainEvidence(**values)


def _employee(**changes) -> EmployeeSourceEvidence:
    values = {
        "provider_employee_id": "pro_exact",
        "source_email_digest": "c" * 64,
        "source_version": 2,
        "source_status": "active",
        "user_id": uuid4(),
        "membership_id": uuid4(),
        "employee_id": uuid4(),
        "branch_id": uuid4(),
        "owner_certification": "CONFIRM",
        "duplicate_state": "NONE",
        "source_digest": "d" * 64,
    }
    values.update(changes)
    return EmployeeSourceEvidence(**values)


def _domains(**family_changes) -> tuple[HistoricalDomainEvidence, ...]:
    return tuple(
        _domain(
            source_family=family,
            **(family_changes if family == "jobs" else {}),
        )
        for family in sorted(REQUIRED_SOURCE_FAMILIES)
    )


def test_complete_packet_is_replay_stable_and_retirement_ready() -> None:
    values = {
        "as_of": datetime(2026, 10, 3, tzinfo=timezone.utc),
        "source_digest": "e" * 64,
        "domains": _domains(),
        "metadata": (
            MetadataEvidence(
                kind="job_type",
                source_parent_family="jobs",
                source_parent_id="job_1",
                provider_id="jty_1",
                source_label="Water Heater",
                state="HISTORICAL_ONLY",
                native_reference=None,
                source_digest="f" * 64,
            ),
        ),
        "employees": (_employee(),),
        "source_cutoff": datetime(2026, 10, 2, tzinfo=timezone.utc),
        "create_count": 8,
        "update_count": 2,
        "replay_count": 10,
        "final_replay_result": "IDENTICAL",
    }
    first = build_packet(**values)
    second = build_packet(**values)
    first.verify()
    assert first == second
    assert first.receipt.retirement_state == "RETIREMENT_READY"
    assert first.receipt.unexplained_gap_count == 0


def test_external_owner_unknown_conflict_and_replay_drift_block_retirement() -> None:
    packet = build_packet(
        as_of=datetime(2026, 10, 3, tzinfo=timezone.utc),
        source_digest="e" * 64,
        domains=_domains(conflict=1, unknown=0),
        metadata=(),
        employees=(_employee(duplicate_state="CONFLICT"),),
        source_cutoff=datetime(2026, 10, 2, tzinfo=timezone.utc),
        create_count=0,
        update_count=0,
        replay_count=0,
        quarantines=("invoice:bad-parent",),
        unresolved=("employee:pro_unknown",),
        owner_decisions=("employee:pro_exact",),
        external_gaps=("attachments:HCP_SUPPORT_EXPORT",),
        final_replay_result="DRIFT",
    )
    assert packet.receipt.retirement_state == "BLOCKED"
    assert packet.receipt.conflict_count == 2
    with pytest.raises(ValueError, match="digest mismatch"):
        replace(packet.receipt, replay_count=1).verify()


def test_population_partition_must_be_complete() -> None:
    with pytest.raises(ValueError, match="fully classified"):
        _domain(acquired_population=9).validate()
    with pytest.raises(ValueError, match="cardinality drift"):
        _domain(source_population=11).validate()


def test_packet_rejects_incomplete_source_family_coverage() -> None:
    with pytest.raises(ValueError, match="family coverage"):
        build_packet(
            as_of=datetime(2026, 10, 3, tzinfo=timezone.utc),
            source_digest="e" * 64,
            domains=(_domain(),),
            metadata=(),
            employees=(),
            source_cutoff=datetime(2026, 10, 2, tzinfo=timezone.utc),
            create_count=0,
            update_count=0,
            replay_count=0,
        )


def test_terminated_employee_cannot_imply_login_access() -> None:
    with pytest.raises(ValueError, match="cannot imply login"):
        _employee(source_status="terminated").validate()


def test_metadata_extraction_preserves_provider_ids_labels_and_history(
    tmp_path,
) -> None:
    root = tmp_path / "raw"
    jobs = root / "jobs"
    invoices = root / "invoices"
    jobs.mkdir(parents=True)
    invoices.mkdir(parents=True)
    (jobs / "page-0001.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "job_1",
                        "tags": [{"id": "tag_1", "name": "VIP"}],
                        "lead_source": {"id": "lead_1", "name": "Referral"},
                        "job_fields": {
                            "business_unit": {"id": "buu_1", "name": "Plumbing"},
                            "job_type": {"id": "jty_1", "name": "Water Heater"},
                        },
                    }
                ]
            }
        )
    )
    (invoices / "page-0001.json").write_text(
        json.dumps(
            {
                "invoices": [
                    {
                        "id": "invoice_1",
                        "items": [{"id": "invitm_1", "name": "Install water heater"}],
                    }
                ]
            }
        )
    )
    first = metadata_from_source(tmp_path)
    second = metadata_from_source(tmp_path)
    assert first == second
    assert {item.kind for item in first} == {
        "tag",
        "lead_source",
        "business_unit",
        "job_type",
        "service_reference",
    }
    assert all(item.state == "HISTORICAL_ONLY" for item in first)
    assert {item.provider_id for item in first} >= {
        "tag_1",
        "lead_1",
        "buu_1",
        "jty_1",
        "invitm_1",
    }


@pytest.mark.asyncio
async def test_persistence_is_master_scoped_and_exact_replay_is_idempotent() -> None:
    company_id, branch_id, master_id = uuid4(), uuid4(), uuid4()
    packet = build_packet(
        as_of=datetime(2026, 10, 3, tzinfo=timezone.utc),
        source_digest="e" * 64,
        domains=_domains(),
        metadata=(),
        employees=(_employee(branch_id=branch_id),),
        source_cutoff=datetime(2026, 10, 2, tzinfo=timezone.utc),
        create_count=1,
        update_count=0,
        replay_count=1,
        external_gaps=("attachments:HCP_SUPPORT_EXPORT",),
        final_replay_result="IDENTICAL",
    )
    master = SimpleNamespace(id=master_id)
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[master, None]),
        add=Mock(),
        flush=AsyncMock(),
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=branch_id),
        has_permission=lambda code: code == MigrationPermission.EXECUTE_REHEARSAL,
    )
    created = await persist_packet(
        session, context=context, master_run_id=master_id, packet=packet
    )
    assert created.company_id == company_id
    assert created.branch_id == branch_id
    assert created.status == "BLOCKED"
    assert created.packet["receipt"]["external_gaps"] == [
        "attachments:HCP_SUPPORT_EXPORT"
    ]
    session.add.assert_called_once_with(created)
    session.flush.assert_awaited_once()

    replay_session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[master, created]), add=Mock(), flush=AsyncMock()
    )
    replay = await persist_packet(
        replay_session, context=context, master_run_id=master_id, packet=packet
    )
    assert replay is created
    replay_session.add.assert_not_called()
    replay_session.flush.assert_not_awaited()
