import hashlib
import inspect
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.customer_migration.adapter_import import (
    CustomerAdapterImportReport,
    review_adapter_output,
)
from app.customer_migration.pilot_command import _load_reviewed, verify_backup
from app.customer_migration.pilot_execution import (
    PILOT_APPROVAL_VERSION,
    STAGE_APPROVAL_VERSION,
    CustomerMigrationStageApproval,
    CustomerPilotApproval,
    CustomerPilotExecutionService,
    OperationalCounts,
    PilotExecutionError,
    PreviewBackupEvidence,
    PreviewExecutionRuntime,
)
from app.customer_migration.pilot_selection import CustomerPilotSelectionService
from app.customers.schemas import CustomerCreate, CustomerStatus, CustomerType


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Record:
    row_number: int
    source_id: str
    schema_version: str
    source_row_sha256: str
    customer: CustomerCreate
    contact: None = None
    service_locations: tuple = ()
    billing_address: None = None


@dataclass(frozen=True)
class AdapterOutput:
    source_sha256: str
    schema_version: str
    transformation_sha256: str
    source: int
    accepted: int
    rejected: int
    duplicate: int
    records: tuple[Record, ...]
    rejections: tuple = ()
    child_exceptions: tuple = ()


class CountRepository:
    def __init__(
        self,
        counts: OperationalCounts,
        head: str = "phase-head",
        post_counts: OperationalCounts | None = None,
    ) -> None:
        self.counts = counts
        self.post_counts = post_counts or counts
        self.head = head
        self.read_count = 0

    async def read(self, factory) -> OperationalCounts:
        del factory
        self.read_count += 1
        return self.counts if self.read_count == 1 else self.post_counts

    async def alembic_head(self, factory) -> str:
        del factory
        return self.head

    async def imported_source_identities(self, factory, **kwargs) -> frozenset[str]:
        del factory
        return frozenset(kwargs["source_identities"])


class Facade:
    def __init__(self, report: CustomerAdapterImportReport | None = None) -> None:
        self.import_reviewed = AsyncMock(
            return_value=report
            or CustomerAdapterImportReport(
                run_id="00000000-0000-0000-0000-000000000001",
                attempted=1,
                accepted=1,
                duplicate=0,
                rejected=0,
            )
        )


def reviewed_output():
    output = AdapterOutput(
        source_sha256=digest("source"),
        schema_version="registered-schema-v1",
        transformation_sha256=digest("transformation"),
        source=1,
        accepted=1,
        rejected=0,
        duplicate=0,
        records=(
            Record(
                row_number=2,
                source_id="synthetic-source",
                schema_version="registered-schema-v1",
                source_row_sha256=digest("row"),
                customer=CustomerCreate(
                    customer_type=CustomerType.RESIDENTIAL,
                    display_name="Synthetic Customer",
                    status=CustomerStatus.ACTIVE,
                ),
            ),
        ),
    )
    return review_adapter_output(output, source_system="synthetic")


def test_duplicate_policy_matches_operational_name_gate() -> None:
    reviewed = reviewed_output()
    first = reviewed.aggregates[0]
    second = replace(
        first,
        source_identity="second-source",
        source_identity_sha256=digest("second-source"),
    )
    members = CustomerPilotSelectionService().policy.duplicate_members((first, second))
    assert members == {
        first.source_identity_sha256,
        second.source_identity_sha256,
    }


def counts(**changes: int) -> OperationalCounts:
    values = {
        "customers": 0,
        "customer_contacts": 0,
        "service_locations": 0,
        "customer_billing_addresses": 0,
        "customer_notes": 0,
        "appointments": 0,
        "jobs": 0,
        "estimates": 0,
        "invoices": 0,
        "payments": 0,
        "business_events": 0,
    }
    values.update(changes)
    return OperationalCounts(**values)


def approval(reviewed, *, mode: str = "validate") -> CustomerPilotApproval:
    identities = tuple(
        aggregate.source_identity_sha256 for aggregate in reviewed.aggregates
    )
    return CustomerPilotApproval(
        approval_version=PILOT_APPROVAL_VERSION,
        target_environment="preview",
        mode=mode,
        source_sha256=reviewed.source_sha256,
        schema_version=reviewed.schema_version,
        reviewed_output_sha256=reviewed.review_sha256,
        pilot_manifest_sha256=digest("manifest"),
        pilot_boundary_sha256=digest(json.dumps(identities, separators=(",", ":"))),
        ordered_source_identity_allowlist=identities,
        expected={
            "customers": 1,
            "contacts": 0,
            "service_locations": 0,
            "billing_addresses": 0,
            "business_events": 1,
        },
        expected_blocking_dispositions=0,
        expected_deployed_git_sha="a" * 40,
        expected_alembic_head="phase-head",
        expected_pre_import_counts=counts(),
    )


def stage_approval(reviewed) -> CustomerMigrationStageApproval:
    first = reviewed.aggregates[0].source_identity_sha256
    second = digest("second-source-identity")
    return CustomerMigrationStageApproval(
        approval_version=STAGE_APPROVAL_VERSION,
        target_environment="preview",
        mode="import",
        source_sha256=reviewed.source_sha256,
        schema_version=reviewed.schema_version,
        reviewed_output_sha256=reviewed.review_sha256,
        pilot_manifest_sha256=digest("stage-manifest"),
        pilot_boundary_sha256=digest(
            json.dumps((first, second), separators=(",", ":"))
        ),
        ordered_source_identity_allowlist=(first, second),
        expected={
            "customers": 2,
            "contacts": 0,
            "service_locations": 0,
            "billing_addresses": 0,
            "business_events": 2,
        },
        expected_already_imported={
            "customers": 1,
            "contacts": 0,
            "service_locations": 0,
            "billing_addresses": 0,
            "business_events": 1,
        },
        expected_blocking_dispositions=0,
        expected_deployed_git_sha="a" * 40,
        expected_alembic_head="phase-head",
        expected_pre_import_counts=counts(customers=1, business_events=1),
    )


def runtime(*, environment: str = "preview", backup: bool = True):
    return PreviewExecutionRuntime(
        environment=environment,
        deployed_git_sha="a" * 40,
        alembic_head="phase-head",
        backup=(
            PreviewBackupEvidence(
                path_sha256=digest("path"),
                backup_sha256=digest("backup"),
                byte_size=5,
                custom_format_verified=True,
            )
            if backup
            else None
        ),
    )


def context():
    return SimpleNamespace(
        active_branch=SimpleNamespace(id="branch"),
        has_permission=lambda code: code == "COMPANY_CUSTOMER_MANAGE",
    )


@pytest.mark.asyncio
async def test_validation_mode_is_write_free_and_pii_safe() -> None:
    reviewed = reviewed_output()
    facade = Facade()
    repository = CountRepository(counts())
    report = await CustomerPilotExecutionService(
        facade=facade, repository=repository
    ).run(
        object(),
        context=context(),
        reviewed=reviewed,
        approval=approval(reviewed),
        runtime=runtime(backup=False),
    )
    facade.import_reviewed.assert_not_awaited()
    assert repository.read_count == 2
    assert report.status == "validated"
    serialized = report.model_dump_json()
    assert "Synthetic Customer" not in serialized
    assert "synthetic-source" not in serialized


@pytest.mark.asyncio
async def test_import_invokes_only_authoritative_facade() -> None:
    reviewed = reviewed_output()
    facade = Facade()
    repository = CountRepository(
        counts(), post_counts=counts(customers=1, business_events=1)
    )
    await CustomerPilotExecutionService(facade=facade, repository=repository).run(
        object(),
        context=context(),
        reviewed=reviewed,
        approval=approval(reviewed, mode="import"),
        runtime=runtime(backup=True),
    )
    facade.import_reviewed.assert_awaited_once()


@pytest.mark.asyncio
async def test_cumulative_stage_recognizes_prior_prefix_and_creates_delta() -> None:
    reviewed = reviewed_output()
    facade = Facade(
        CustomerAdapterImportReport(
            run_id="00000000-0000-0000-0000-000000000002",
            attempted=2,
            accepted=1,
            duplicate=1,
            rejected=0,
        )
    )
    repository = CountRepository(
        counts(customers=1, business_events=1),
        post_counts=counts(customers=2, business_events=2),
    )
    report = await CustomerPilotExecutionService(
        facade=facade, repository=repository
    ).run(
        object(),
        context=context(),
        reviewed=reviewed,
        approval=stage_approval(reviewed),
        runtime=runtime(),
    )
    assert report.status == "completed"
    assert report.accepted == 1
    assert report.duplicate == 1
    assert report.actual_count_delta.customers == 1


@pytest.mark.asyncio
async def test_import_requires_verified_preview_backup() -> None:
    reviewed = reviewed_output()
    facade = Facade()
    with pytest.raises(PilotExecutionError, match="backup"):
        await CustomerPilotExecutionService(
            facade=facade, repository=CountRepository(counts())
        ).run(
            object(),
            context=context(),
            reviewed=reviewed,
            approval=approval(reviewed, mode="import"),
            runtime=runtime(backup=False),
        )
    facade.import_reviewed.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    ["environment", "source", "schema", "review", "git", "head", "counts"],
)
async def test_all_runtime_and_owner_boundaries_fail_closed(mutation: str) -> None:
    reviewed = reviewed_output()
    approved = approval(reviewed)
    current_runtime = runtime()
    repository = CountRepository(counts())
    if mutation == "environment":
        current_runtime = runtime(environment="production")
    elif mutation == "source":
        approved = approved.model_copy(update={"source_sha256": digest("other")})
    elif mutation == "schema":
        approved = approved.model_copy(update={"schema_version": "other"})
    elif mutation == "review":
        approved = approved.model_copy(
            update={"reviewed_output_sha256": digest("other")}
        )
    elif mutation == "git":
        current_runtime = replace(current_runtime, deployed_git_sha="b" * 40)
    elif mutation == "head":
        repository.head = "other"
    else:
        repository.counts = counts(customers=1)
    facade = Facade()
    with pytest.raises(PilotExecutionError):
        await CustomerPilotExecutionService(facade=facade, repository=repository).run(
            object(),
            context=context(),
            reviewed=reviewed,
            approval=approved,
            runtime=current_runtime,
        )
    facade.import_reviewed.assert_not_awaited()


def test_ordered_allowlist_missing_extra_and_reordering_fail_closed() -> None:
    reviewed = reviewed_output()
    valid = approval(reviewed)
    with pytest.raises(ValidationError):
        CustomerPilotApproval.model_validate(
            {
                **valid.model_dump(),
                "ordered_source_identity_allowlist": (),
            }
        )
    with pytest.raises(ValidationError):
        CustomerPilotApproval.model_validate(
            {
                **valid.model_dump(),
                "ordered_source_identity_allowlist": (
                    *valid.ordered_source_identity_allowlist,
                    digest("extra"),
                ),
            }
        )
    identities = (digest("first"), digest("second"))
    two = valid.model_copy(
        update={
            "ordered_source_identity_allowlist": identities,
            "expected": valid.expected.model_copy(update={"customers": 2}),
            "pilot_boundary_sha256": digest(
                json.dumps(identities, separators=(",", ":"))
            ),
        }
    )
    reordered = two.model_copy(
        update={"ordered_source_identity_allowlist": tuple(reversed(identities))}
    )
    with pytest.raises(ValueError, match="boundary digest"):
        reordered.import_boundary().validate()


def test_missing_approval_values_are_rejected() -> None:
    payload = approval(reviewed_output()).model_dump()
    for field in CustomerPilotApproval.model_fields:
        candidate = dict(payload)
        candidate.pop(field)
        with pytest.raises(ValidationError):
            CustomerPilotApproval.model_validate(candidate)


@pytest.mark.asyncio
async def test_retry_delegates_idempotently_to_facade() -> None:
    reviewed = reviewed_output()
    facade = Facade(
        CustomerAdapterImportReport(
            run_id="00000000-0000-0000-0000-000000000002",
            attempted=1,
            accepted=0,
            duplicate=1,
            rejected=0,
        )
    )
    post_import = counts(customers=1, business_events=1)
    report = await CustomerPilotExecutionService(
        facade=facade, repository=CountRepository(post_import)
    ).run(
        object(),
        context=context(),
        reviewed=reviewed,
        approval=approval(reviewed, mode="import"),
        runtime=runtime(backup=True),
    )
    assert report.duplicate == 1
    assert report.idempotent_replay is True
    facade.import_reviewed.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_fails_closed_when_counts_are_neither_initial_nor_expected() -> (
    None
):
    reviewed = reviewed_output()
    with pytest.raises(PilotExecutionError, match="operational counts changed"):
        await CustomerPilotExecutionService(
            facade=Facade(), repository=CountRepository(counts(customers=2))
        ).run(
            object(),
            context=context(),
            reviewed=reviewed,
            approval=approval(reviewed, mode="import"),
            runtime=runtime(backup=True),
        )


@pytest.mark.asyncio
async def test_post_import_count_discrepancy_is_reported_without_pii() -> None:
    reviewed = reviewed_output()
    report = await CustomerPilotExecutionService(
        facade=Facade(), repository=CountRepository(counts())
    ).run(
        object(),
        context=context(),
        reviewed=reviewed,
        approval=approval(reviewed, mode="import"),
        runtime=runtime(backup=True),
    )
    assert report.status == "completed_with_discrepancy"
    assert report.post_import_counts_match is False
    assert "Synthetic Customer" not in report.model_dump_json()


def test_legacy_importer_is_structurally_unreachable() -> None:
    source = inspect.getsource(CustomerPilotExecutionService)
    assert "HousecallProCustomerMigration" not in source
    assert "customer_import_facade" in inspect.getsource(
        __import__(
            "app.customer_migration.pilot_execution",
            fromlist=["CustomerPilotExecutionService"],
        )
    )


def test_reviewed_contract_loader_and_backup_verification(tmp_path: Path) -> None:
    reviewed = reviewed_output()
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text(
        json.dumps(
            {
                **reviewed.__dict__,
                "aggregates": [item.__dict__ for item in reviewed.aggregates],
            }
        ),
        encoding="utf-8",
    )
    os.chmod(reviewed_path, 0o600)
    assert _load_reviewed(reviewed_path).review_sha256 == reviewed.review_sha256

    backup_path = tmp_path / "preview.dump"
    backup_path.write_bytes(b"PGDMPsynthetic-backup-metadata")
    os.chmod(backup_path, 0o600)
    backup_sha256 = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    evidence = verify_backup(backup_path, backup_sha256)
    assert evidence.backup_sha256 == backup_sha256
    assert evidence.custom_format_verified is True


def test_pilot_manifest_selection_is_deterministic_and_replayable() -> None:
    reviewed = reviewed_output()
    service = CustomerPilotSelectionService()
    generated = service.select(
        reviewed,
        migration_version="synthetic-migration-v1",
        limit=1,
    )
    replay = service.select(
        reviewed,
        migration_version="synthetic-migration-v1",
        limit=1,
        generated_at=generated.generated_at,
    )
    assert replay == generated
    assert generated.expected_customers == 1
    assert generated.ordered_customer_identity_sha256 == (
        reviewed.aggregates[0].source_identity_sha256,
    )
    assert generated.replay_key == approval(reviewed).pilot_boundary_sha256
