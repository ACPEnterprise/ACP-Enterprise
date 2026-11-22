from __future__ import annotations

import hashlib
import json
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from app.customer_migration.acceptance_cohort import (
    ACCEPTANCE_COHORT_CONTRACT,
    ADAPTER_NAME,
    AcceptanceCohortIdentity,
    CustomerAcceptanceCohort,
)
from app.customer_migration.live_acceptance_cohort import (
    READ_ONLY_TRANSACTION,
    load_private_acceptance_cohort,
    verify_live_acceptance_cohort,
)
from app.customer_migration.models import CustomerSourceIdentity
from app.customer_migration.pilot_selection import SELECTION_VERSION
from app.customers.models import Customer
from app.events.models import BusinessEvent
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from scripts.verify_customer_acceptance_cohort import _write_restricted
from sqlalchemy.ext.asyncio import AsyncSession

RELEASE_SHA = "a" * 40
SOURCE_SHA = "b" * 64
COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
BRANCH_ID = UUID("22222222-2222-4222-8222-222222222222")
BOUND_AT = datetime(2026, 11, 19, tzinfo=timezone.utc)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _member(source_id: str) -> AcceptanceCohortIdentity:
    return AcceptanceCohortIdentity(
        source_identity=source_id,
        source_identity_sha256=hashlib.sha256(source_id.encode()).hexdigest(),
        source_row_sha256=hashlib.sha256(f"row:{source_id}".encode()).hexdigest(),
    )


def _artifact(
    selected_ids: tuple[str, ...] = ("provider-selected",),
    anchor_ids: tuple[str, ...] = ("provider-anchor",),
) -> CustomerAcceptanceCohort:
    values: dict[str, object] = {
        "contract": ACCEPTANCE_COHORT_CONTRACT,
        "adapter": ADAPTER_NAME,
        "source_system": "housecall_pro",
        "source_sha256": SOURCE_SHA,
        "schema_version": "test/v1",
        "transformation_sha256": "c" * 64,
        "review_version": "test-review/v1",
        "reviewed_output_sha256": "d" * 64,
        "selection_version": SELECTION_VERSION,
        "eligibility_manifest_sha256": "e" * 64,
        "migration_release_sha": RELEASE_SHA,
        "limit": len(selected_ids),
        "eligible_count": len(selected_ids) + len(anchor_ids),
        "selected": tuple(_member(value) for value in selected_ids),
        "mandatory_anchors": tuple(_member(value) for value in anchor_ids),
    }
    provisional = CustomerAcceptanceCohort.model_construct(
        **values,  # type: ignore[arg-type]
        artifact_sha256="",
    )
    digest = hashlib.sha256(
        _canonical_json(provisional.integrity_payload()).encode()
    ).hexdigest()
    return CustomerAcceptanceCohort.model_validate(
        {**values, "artifact_sha256": digest}
    )


def _company() -> Company:
    return Company(
        id=COMPANY_ID,
        name="Acceptance Tenant",
        code="ACCEPTANCE",
        status="active",
        timezone="America/New_York",
        archived_at=None,
    )


def _branch() -> Branch:
    return Branch(
        id=BRANCH_ID,
        company_id=COMPANY_ID,
        name="Main",
        code="MAIN",
        status="active",
        timezone="America/New_York",
        archived_at=None,
    )


def _binding(
    source_id: str,
    *,
    company_id: UUID = COMPANY_ID,
    branch_id: UUID = BRANCH_ID,
    customer: Customer | None | object = ...,
    created_at: datetime = BOUND_AT,
) -> tuple[CustomerSourceIdentity, Customer | None]:
    customer_id = uuid4()
    if customer is ...:
        customer = Customer(
            id=customer_id,
            company_id=company_id,
            customer_number=f"CUS-{uuid4().int % 900000 + 100000}",
            status="active",
            customer_type="residential",
            display_name="Private Test Customer",
            normalized_name="private test customer",
            preferred_contact_method="phone",
        )
    assert customer is None or isinstance(customer, Customer)
    if customer is not None:
        customer_id = customer.id
    identity = CustomerSourceIdentity(
        id=uuid4(),
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer_id,
        source_system="housecall_pro",
        source_customer_id=source_id,
        first_run_id=uuid4(),
        created_at=created_at,
    )
    return identity, customer


class _Rows:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def all(self) -> list[Any]:
        return self.values


class _Session:
    def __init__(
        self,
        rows: list[tuple[CustomerSourceIdentity, Customer | None]],
        *,
        events: list[BusinessEvent] | None = None,
        company: Company | None = None,
        branch: Branch | None = None,
    ) -> None:
        self.rows = rows
        self.events = events or []
        self.company = _company() if company is None else company
        self.branch = _branch() if branch is None else branch
        self.statements: list[object] = []
        self.rolled_back = False

    async def execute(self, statement: object) -> _Rows:
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _Rows([])
        return _Rows(self.rows)

    async def get(self, model: type[object], identity: UUID) -> object | None:
        if model is Company and identity == COMPANY_ID:
            return self.company
        if model is Branch and identity == BRANCH_ID:
            return self.branch
        return None

    async def scalars(self, statement: object) -> _Rows:
        self.statements.append(statement)
        return _Rows(self.events)

    async def rollback(self) -> None:
        self.rolled_back = True


def _write_artifact(path: Path, artifact: CustomerAcceptanceCohort) -> None:
    path.write_text(artifact.model_dump_json(), encoding="utf-8")
    path.chmod(0o600)


def test_private_artifact_requires_mode_integrity_and_exact_bindings(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cohort.json"
    artifact = _artifact()
    _write_artifact(path, artifact)

    assert (
        load_private_acceptance_cohort(
            path,
            expected_source_sha256=SOURCE_SHA,
            expected_migration_release_sha=RELEASE_SHA,
        )
        == artifact
    )
    with pytest.raises(ValueError, match="source binding mismatch"):
        load_private_acceptance_cohort(
            path,
            expected_source_sha256="0" * 64,
            expected_migration_release_sha=RELEASE_SHA,
        )
    with pytest.raises(ValueError, match="release binding mismatch"):
        load_private_acceptance_cohort(
            path,
            expected_source_sha256=SOURCE_SHA,
            expected_migration_release_sha="0" * 40,
        )

    path.chmod(0o640)
    with pytest.raises(ValueError, match="mode 0600"):
        load_private_acceptance_cohort(
            path,
            expected_source_sha256=SOURCE_SHA,
            expected_migration_release_sha=RELEASE_SHA,
        )


def test_private_artifact_rejects_tampering_and_symlinks(tmp_path: Path) -> None:
    path = tmp_path / "cohort.json"
    payload = _artifact().model_dump(mode="json")
    payload["source_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        load_private_acceptance_cohort(
            path,
            expected_source_sha256="0" * 64,
            expected_migration_release_sha=RELEASE_SHA,
        )

    target = tmp_path / "target.json"
    _write_artifact(target, _artifact())
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="regular file"):
        load_private_acceptance_cohort(
            link,
            expected_source_sha256=SOURCE_SHA,
            expected_migration_release_sha=RELEASE_SHA,
        )


@pytest.mark.asyncio
async def test_live_verifier_is_read_only_exact_non_pii_and_reports_holds() -> None:
    selected = _binding("provider-selected")
    anchor = _binding("provider-anchor")
    anchor_customer = anchor[1]
    assert anchor_customer is not None
    event = BusinessEvent(
        id=uuid4(),
        event_type="customer.updated",
        entity_type="customer",
        entity_id=anchor_customer.id,
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        user_id=uuid4(),
        payload={},
        correlation_id=uuid4(),
        occurred_at=BOUND_AT + timedelta(minutes=1),
        created_at=BOUND_AT + timedelta(minutes=1),
    )
    session = _Session([selected, anchor], events=[event])

    report = await verify_live_acceptance_cohort(
        cast(AsyncSession, session),
        artifact=_artifact(),
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
    )

    assert str(session.statements[0]) == READ_ONLY_TRANSACTION
    exact_query = str(session.statements[1])
    assert "customer_source_identities.source_system" in exact_query
    assert "customer_source_identities.source_customer_id IN" in exact_query
    assert session.rolled_back is True
    assert report["result"] == "PASS"
    assert report["selected"]["verified"] == 1  # type: ignore[index]
    assert report["mandatory_anchors"]["verified"] == 1  # type: ignore[index]
    assert report["mandatory_anchors"]["native_change_holds"] == 1  # type: ignore[index]
    assert report["reported_exceptions"] == {"native_change_holds": 1}
    serialized = json.dumps(report)
    assert "provider-selected" not in serialized
    assert "provider-anchor" not in serialized
    assert selected[1] is not None and str(selected[1].id) in serialized


@pytest.mark.asyncio
async def test_live_verifier_classifies_identity_and_scope_defects() -> None:
    selected_ids = (
        "missing",
        "cross-tenant",
        "duplicate",
        "wrong-branch",
        "missing-native",
        "cross-native",
    )
    other_company_id = uuid4()
    duplicate = _binding("duplicate")
    cross_native_customer = Customer(
        id=uuid4(),
        company_id=other_company_id,
        customer_number="CUS-999999",
        status="active",
        customer_type="residential",
        display_name="Cross Tenant",
        normalized_name="cross tenant",
        preferred_contact_method="phone",
    )
    rows = [
        _binding("cross-tenant", company_id=other_company_id),
        duplicate,
        _binding("duplicate"),
        _binding("wrong-branch", branch_id=uuid4()),
        _binding("missing-native", customer=None),
        _binding("cross-native", customer=cross_native_customer),
        _binding("provider-anchor"),
    ]
    session = _Session(rows)

    report = await verify_live_acceptance_cohort(
        cast(AsyncSession, session),
        artifact=_artifact(selected_ids=selected_ids),
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
    )

    assert report["result"] == "FAIL"
    selected = report["selected"]
    assert selected["outcomes"] == {  # type: ignore[index]
        "branch_authority_mismatch": 1,
        "cross_tenant_identity": 1,
        "cross_tenant_native_customer": 1,
        "duplicate_identity": 1,
        "missing_identity": 1,
        "missing_native_customer": 1,
    }
    assert report["safe_counts"]["identity_defects"] == 6  # type: ignore[index]
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_holds_are_binding_exact_and_native_reuse_spans_both_sections() -> None:
    shared_customer = _binding("seed")[1]
    assert shared_customer is not None
    event_time = BOUND_AT + timedelta(hours=1)
    selected = _binding(
        "provider-selected",
        customer=shared_customer,
        created_at=BOUND_AT,
    )
    anchor = _binding(
        "provider-anchor",
        customer=shared_customer,
        created_at=BOUND_AT + timedelta(hours=2),
    )
    event = BusinessEvent(
        id=uuid4(),
        event_type="customer.updated",
        entity_type="customer",
        entity_id=shared_customer.id,
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        user_id=uuid4(),
        payload={},
        correlation_id=uuid4(),
        occurred_at=event_time,
        created_at=event_time,
    )
    session = _Session([selected, anchor], events=[event])

    report = await verify_live_acceptance_cohort(
        cast(AsyncSession, session),
        artifact=_artifact(),
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
    )

    selected_report = cast(dict[str, object], report["selected"])
    anchor_report = cast(dict[str, object], report["mandatory_anchors"])
    assert selected_report["outcomes"] == {"duplicate_native_customer": 1}
    assert anchor_report["outcomes"] == {"duplicate_native_customer": 1}
    assert selected_report["native_change_holds"] == 1
    assert anchor_report["native_change_holds"] == 0
    safe_counts = cast(dict[str, object], report["safe_counts"])
    assert safe_counts["native_change_holds"] == 1
    assert safe_counts["identity_defects"] == 2
    assert report["result"] == "FAIL"


@pytest.mark.asyncio
async def test_live_verifier_fails_closed_on_invalid_authority() -> None:
    inactive = _company()
    inactive.status = "inactive"
    session = _Session([], company=inactive)

    with pytest.raises(ValueError, match="Company authority"):
        await verify_live_acceptance_cohort(
            cast(AsyncSession, session),
            artifact=_artifact(),
            company_id=COMPANY_ID,
            branch_id=BRANCH_ID,
        )

    assert str(session.statements[0]) == READ_ONLY_TRANSACTION
    assert session.rolled_back is True


def test_report_writer_is_exclusive_and_mode_0600(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    _write_restricted(output, b"{}\n")

    assert output.read_bytes() == b"{}\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        _write_restricted(output, b'{"overwritten":true}\n')
    assert output.read_bytes() == b"{}\n"
