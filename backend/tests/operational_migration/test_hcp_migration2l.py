from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Self
from uuid import UUID

import pytest

from app.financials.service import FinancialService, FinancialValidationError
from app.operational_migration.financial import (
    FinancialLineItemRecord,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2Application,
    HcpMigration2ExecutionPlanBuilder,
    HcpMigration2FinancialSupersedingAuthority,
    HcpMigration2SupersedingRepairAuthority,
)
from app.operational_migration.hcp_migration2i import (
    ChildRepairPlan,
    FinancialEligibility,
    OperationalEligibility,
)
from app.operational_migration.hcp_migration2l import (
    INVOICE_EVIDENCE_REASON,
    PAYMENT_EVIDENCE_REASON,
    build_financial_superseding_plan,
    evidence_relationship_counts,
    superseding_completion_counts,
)

MASTER_ID = UUID("63273602-8619-5c0b-8b49-8537338b04b5")
FINANCIAL_REPAIR_ID = UUID("f37c8f8a-e6a9-56d2-a84b-cea11c5f52ca")
FINANCIAL_CHILD_ID = UUID("ee397b19-61f2-42b6-9bce-d9c68bdef8c1")
SEALED_SUCCESSOR_ID = UUID("8d3a78a3-c62d-55f8-8de3-f63286f099ad")
SEALED_SUCCESSOR_DIGEST = (
    "77863d0a1c9d86178ab2f81ce2858c935829bab473dc49219633aa54d4f4e123"
)


def invoice(source_id: str, *, line_items: bool) -> InvoiceMigrationRecord:
    lines = (
        (
            FinancialLineItemRecord(
                source_id=f"line-{source_id}",
                description="synthetic qualification",
                quantity=Decimal(1),
                unit_price=Decimal(10),
                total_amount=Decimal(10),
            ),
        )
        if line_items
        else ()
    )
    return InvoiceMigrationRecord(
        source_id=source_id,
        source_job_id="job-safe",
        status="issued",
        currency="USD",
        subtotal_amount=Decimal(10),
        tax_amount=Decimal(0),
        total_amount=Decimal(10),
        line_items=lines,
    )


def payment(source_id: str, invoice_id: str) -> PaymentMigrationRecord:
    return PaymentMigrationRecord(
        source_id=source_id,
        source_invoice_id=invoice_id,
        status="succeeded",
        currency="USD",
        amount=Decimal(10),
    )


def repair() -> ChildRepairPlan:
    financial = FinancialEligibility(
        estimates=(),
        invoices=(
            invoice("invoice-native", line_items=True),
            invoice("invoice-evidence", line_items=False),
        ),
        payments=(
            payment("payment-native", "invoice-native"),
            payment("payment-evidence", "invoice-evidence"),
        ),
        estimate_exceptions=0,
        invoice_exceptions=0,
        payment_exceptions=0,
        estimate_outcomes=(),
        invoice_outcomes=(),
        payment_outcomes=(),
        digest="a" * 64,
    )
    return ChildRepairPlan(
        original_plan_id=UUID(int=1),
        original_plan_digest="b" * 64,
        operational=OperationalEligibility((), (), {}, {}, (), (), "c" * 64),
        financial=financial,
        persisted_counts={"invoice": 2, "payment": 2},
        exception_counts={"invoice": 0, "payment": 0},
        additional_plan_outcomes=(),
        repair_plan_digest="d" * 64,
    )


def test_empty_invoice_is_evidence_only_without_synthetic_line_item() -> None:
    plan = build_financial_superseding_plan(
        master_id=MASTER_ID,
        original_repair_id=FINANCIAL_REPAIR_ID,
        nonconforming_child_id=FINANCIAL_CHILD_ID,
        repair=repair(),
    )
    assert len(plan.retained_invoice_identity_digests) == 1
    assert len(plan.invoice_evidence) == 1
    assert plan.invoice_evidence[0].reason_code == INVOICE_EVIDENCE_REASON
    assert plan.persisted_counts["invoice"] == 1
    assert plan.exception_counts["invoice"] == 1
    assert all(not item.line_items for item in repair().financial.invoices[1:])


def test_payment_relationship_to_evidence_invoice_remains_evidence_only() -> None:
    value = repair()
    plan = build_financial_superseding_plan(
        master_id=MASTER_ID,
        original_repair_id=FINANCIAL_REPAIR_ID,
        nonconforming_child_id=FINANCIAL_CHILD_ID,
        repair=value,
    )
    assert evidence_relationship_counts(
        invoices=value.financial.invoices, payments=value.financial.payments
    ) == (1, 1)
    assert len(plan.retained_payment_identity_digests) == 1
    assert len(plan.payment_evidence) == 1
    assert plan.payment_evidence[0].reason_code == PAYMENT_EVIDENCE_REASON


def test_financial_supersession_is_deterministic_and_conflicts_change_digest() -> None:
    value = repair()
    first = build_financial_superseding_plan(
        master_id=MASTER_ID,
        original_repair_id=FINANCIAL_REPAIR_ID,
        nonconforming_child_id=FINANCIAL_CHILD_ID,
        repair=value,
    )
    reordered = replace(
        value,
        financial=replace(
            value.financial,
            invoices=tuple(reversed(value.financial.invoices)),
            payments=tuple(reversed(value.financial.payments)),
        ),
    )
    second = build_financial_superseding_plan(
        master_id=MASTER_ID,
        original_repair_id=FINANCIAL_REPAIR_ID,
        nonconforming_child_id=FINANCIAL_CHILD_ID,
        repair=reordered,
    )
    changed_invoice = replace(value.financial.invoices[1], total_amount=Decimal(11))
    changed = build_financial_superseding_plan(
        master_id=MASTER_ID,
        original_repair_id=FINANCIAL_REPAIR_ID,
        nonconforming_child_id=FINANCIAL_CHILD_ID,
        repair=replace(
            value,
            financial=replace(
                value.financial,
                invoices=(value.financial.invoices[0], changed_invoice),
            ),
        ),
    )
    assert first == second
    assert changed.digest != first.digest


def test_native_invoice_line_item_invariant_is_unchanged() -> None:
    with pytest.raises(FinancialValidationError, match="At least one line item"):
        FinancialService._validate_items((), Decimal(10))


def operational_authority() -> HcpMigration2SupersedingRepairAuthority:
    return HcpMigration2SupersedingRepairAuthority(
        master_run_id=MASTER_ID,
        original_plan_id=UUID("8c717798-db5e-5c49-99be-ca3d250536e3"),
        original_plan_digest="6ac31cc70e269dfa123a73c8a896f7e957eff113c1873a6ee8c908a9f1256962",
        generation1_repair_id=UUID("5e17975d-0461-5187-b0ea-f1cbe7b58df1"),
        generation1_repair_plan_digest="64df671d21ab95818ae6035949202e6d61195733013ff63485471164e9b64d8a",
        failed_operational_child_run_id=UUID("a5896cb7-deea-477a-86e5-5d606ecf0582"),
        superseding_plan_id=UUID("a39f3927-0f7f-59a4-8056-97077012832f"),
        superseding_plan_digest="167f3e3729c78953de2e12382d2b64572b0a42082780d1bba4651be0063c5fb5",
        repair_generation=2,
        sequencing_contract_version="hcp-migration-2k1-appointment-sequence/v1",
        sequence_digest="9e77ed819ee488ac5114d6fda26d9ae422b081cdfa9785fb56bbf679d6fa7acb",
        checkpoint_digest="3646dc75db78ac72ae54b6fc1b3cdcd03920d0d54795ab265689a37afbaf906b",
        customer_child_run_id=UUID("4b99260f-43e7-4ae5-81c2-d0cc215b323f"),
        original_operational_child_run_id=UUID("4b8f089d-d47c-4757-a583-e8408f7c4ffd"),
        original_financial_child_run_id=UUID("b8315c42-9d24-4f48-a64f-8fdc05176cce"),
        history_child_run_id=UUID("b612df45-341a-44b7-b85d-964c356ffd17"),
        company_id=UUID("3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd"),
        branch_id=UUID("887f413a-70dc-4ab1-98aa-8e84f4e7efd0"),
        actor_id=UUID("c427ebd1-7583-4c0d-9c54-55a0c1214174"),
        package_digest="f77e3e09457efcbf6d42137be1af43be6ad0adbea8eab2c12ca320730fd96901",
        builder_version="hcp-migration-2g-plan-builder/v1",
    )


def authority() -> HcpMigration2FinancialSupersedingAuthority:
    return HcpMigration2FinancialSupersedingAuthority(
        operational_authority=operational_authority(),
        financial_repair_id=FINANCIAL_REPAIR_ID,
        nonconforming_financial_child_run_id=FINANCIAL_CHILD_ID,
        successor_plan_id=SEALED_SUCCESSOR_ID,
        successor_plan_digest=SEALED_SUCCESSOR_DIGEST,
        empty_invoice_identity_digest="e972c0930b9232e365d008015e835ece303a34f1f7f223c56ec7baf114770b4e",
        invoice_evidence_count=117,
    )


class _Scalars:
    def __init__(self, values: tuple[SimpleNamespace, ...]) -> None:
        self.values = values

    def all(self) -> tuple[SimpleNamespace, ...]:
        return self.values


class _Session:
    def __init__(self, values: tuple[SimpleNamespace, ...]) -> None:
        self.values = values

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def scalars(self, _statement: object) -> _Scalars:
        return _Scalars(self.values)


class _Factory:
    def __init__(self, values: tuple[SimpleNamespace, ...]) -> None:
        self.values = values

    def __call__(self) -> _Session:
        return _Session(self.values)


class _Application(HcpMigration2Application):
    async def execute_financial_superseding_repair(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        return {"state": "FINANCIAL_SUPERSESSION_COMPLETED"}

    async def replay_completed_financial_superseding(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        return {"state": "COMPLETED_FINANCIAL_SUPERSESSION_REPLAY_VERIFIED"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    (
        ("running", "FINANCIAL_SUPERSESSION_COMPLETED"),
        ("completed", "COMPLETED_FINANCIAL_SUPERSESSION_REPLAY_VERIFIED"),
    ),
)
async def test_public_application_routes_financial_supersession(
    status: str, expected: str
) -> None:
    application = _Application(builder=SimpleNamespace())  # type: ignore[arg-type]
    result = await application.execute(
        _Factory((SimpleNamespace(status=status),)),  # type: ignore[arg-type]
        context=SimpleNamespace(),  # type: ignore[arg-type]
        target=SimpleNamespace(),  # type: ignore[arg-type]
        repair_authority=authority(),
    )
    assert result == {"state": expected}


@pytest.mark.skipif(
    not (
        Path.home()
        / ".acp-enterprise/migration/housecall-pro/hcp-source-4-20260827T223858Z"
    ).exists(),
    reason="protected SOURCE.4 qualification evidence is not installed",
)
def test_sealed_financial_supersession_is_exact() -> None:
    root = Path.home() / ".acp-enterprise/migration/housecall-pro"
    builder = HcpMigration2ExecutionPlanBuilder(
        package_root=root / "hcp-source-4-20260827T223858Z",
        control_csv=root
        / "hcp-source-3-controls/derived/AllCountyPlumbingandLeak_customer_export.csv",
        migration1a_root=root / "hcp-migration-1a-20260828T120000Z",
    )
    plan, _ = builder.build(baseline_counts={"business": 0, "masters": 1})
    customer_ids = frozenset(
        item.source_identity for item in plan.customers.reviewed.aggregates
    )
    location_ids = frozenset(
        identity
        for item in plan.customers.reviewed.aggregates
        for identity in item.service_location_source_identities
    )
    original = builder.build_child_repair_plan(
        original=plan,
        persisted_customer_ids=customer_ids,
        persisted_location_ids=location_ids,
    )
    superseding = build_financial_superseding_plan(
        master_id=MASTER_ID,
        original_repair_id=FINANCIAL_REPAIR_ID,
        nonconforming_child_id=FINANCIAL_CHILD_ID,
        repair=original,
    )
    assert superseding.id == SEALED_SUCCESSOR_ID
    assert superseding.digest == SEALED_SUCCESSOR_DIGEST
    assert len(superseding.retained_invoice_identity_digests) == 663
    assert len(superseding.invoice_evidence) == 117
    assert len(superseding.retained_payment_identity_digests) == 684
    assert not superseding.payment_evidence
    assert superseding.persisted_counts["invoice"] == 663
    assert superseding.exception_counts["invoice"] == 4704
    adjusted = superseding_completion_counts(original, superseding)
    requirements = replace(
        plan.completion,
        transformed_counts=adjusted.persisted_counts,
        persisted_counts=adjusted.persisted_counts,
        exception_counts=adjusted.exception_counts,
    )
    requirements.validate_reconciliation(plan.master.source_counts)
