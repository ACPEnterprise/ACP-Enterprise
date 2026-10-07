from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.accounting.banking import MatchState, deterministic_match
from app.accounting.banking_candidates import (
    BankMatchCandidateAdapterService,
    accounting_movement_candidate,
    customer_payment_candidate,
    grouped_deposit_projection,
    merchant_refund_candidate,
    merchant_settlement_candidates,
    payroll_payment_candidate,
    vendor_payment_candidate,
)

from tests.accounting.test_banking_authority import evidence

DAY = date(2026, 10, 1)
NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)
DIGEST = "c" * 64


def row(**values: object) -> SimpleNamespace:
    return SimpleNamespace(**values)


def test_single_customer_payment_uses_canonical_provider_lineage() -> None:
    candidate = customer_payment_candidate(
        row(
            id=uuid4(),
            captured_amount=Decimal("125.00"),
            currency="USD",
            captured_at=NOW,
            evidence_digest=DIGEST,
        ),  # type: ignore[arg-type]
        row(provider_operation_id="bank-tx-1", provider="fixture-payments"),  # type: ignore[arg-type]
        ("invoice_application:invoice-1:125.00",),
    )
    decision = deterministic_match(
        evidence(related_identity=candidate.target_identity), (candidate,)
    )
    assert decision.state is MatchState.MATCHED
    assert candidate.source_digest == DIGEST
    assert candidate.component_identities == (
        "invoice_application:invoice-1:125.00",
    )
    assert candidate.evidence_strength == "exact_source_lineage"


def test_grouped_customer_deposit_preserves_undeposited_components() -> None:
    candidate = grouped_deposit_projection(
        row(
            id=uuid4(),
            gross_amount=Decimal("125.00"),
            currency="USD",
            created_at=NOW,
            destination_reference="bank-tx-1",
            evidence_digest=DIGEST,
        ),  # type: ignore[arg-type]
        ("payment_receipt:one", "payment_receipt:two"),
    )
    assert candidate.component_identities == (
        "payment_receipt:one",
        "payment_receipt:two",
    )
    assert (
        deterministic_match(
            evidence(related_identity=candidate.target_identity), (candidate,)
        ).state
        is MatchState.MATCHED
    )


def test_merchant_net_settlement_and_fee_are_separate_exact_candidates() -> None:
    candidates = merchant_settlement_candidates(
        row(
            id=uuid4(),
            gross_amount=Decimal("1000.00"),
            refund_amount=Decimal("0.00"),
            dispute_amount=Decimal("0.00"),
            fee_amount=Decimal("25.00"),
            adjustment_amount=Decimal("0.00"),
            net_amount=Decimal("975.00"),
            currency="USD",
            settlement_date=DAY,
            provider_payout_id="payout-1",
            provider="fixture-payments",
            evidence_digest=DIGEST,
        )  # type: ignore[arg-type]
    )
    net = deterministic_match(
        evidence(group_key="payout-1", amount=Decimal("975.00")),
        candidates,
    )
    fee = deterministic_match(
        evidence(
            group_key="payout-1",
            amount=Decimal("25.00"),
            direction="outflow",
            kind="fee",
        ),
        candidates,
    )
    assert net.target_type == "merchant_settlement"
    assert fee.target_type == "merchant_fee"
    assert Decimal("1000.00") - Decimal("25.00") == Decimal("975.00")


def test_authoritative_merchant_refund_projects_an_outflow_candidate() -> None:
    candidate = merchant_refund_candidate(
        row(
            id=uuid4(),
            receipt_id=uuid4(),
            amount=Decimal("125.00"),
            currency="USD",
            created_at=NOW,
            provider_operation_id="bank-tx-1",
            evidence_digest=DIGEST,
            request_digest="e" * 64,
            status="succeeded",
        ),  # type: ignore[arg-type]
        row(provider="fixture-payments"),  # type: ignore[arg-type]
    )
    result = deterministic_match(
        evidence(
            direction="outflow",
            kind="refund",
            related_identity=candidate.target_identity,
        ),
        (candidate,),
    )
    assert result.state is MatchState.MATCHED
    assert result.target_type == "merchant_refund"


@pytest.mark.parametrize(
    ("method", "expected_type"),
    (("check", "vendor_check"), ("ach", "vendor_payment")),
)
def test_vendor_check_and_ach_use_verified_disbursement(
    method: str, expected_type: str
) -> None:
    candidate = vendor_payment_candidate(
        row(
            id=uuid4(),
            method_category=method,
            amount=Decimal("125.00"),
            currency="USD",
            effective_date=DAY,
            source_identity="bank-tx-1",
            source_system="fixture-ap",
            evidence_digest=DIGEST,
            external_reference="safe-reference",
        )  # type: ignore[arg-type]
    )
    assert candidate.target_type == expected_type
    assert (
        deterministic_match(
            evidence(
                direction="outflow", related_identity=candidate.target_identity
            ),
            (candidate,),
        ).state
        is MatchState.MATCHED
    )


@pytest.mark.parametrize(
    ("method", "expected_type"),
    (("paper_check", "payroll_check"), ("ach", "payroll_withdrawal")),
)
def test_payroll_check_and_withdrawal_require_settlement_evidence(
    method: str, expected_type: str
) -> None:
    execution_id = uuid4()
    candidate = payroll_payment_candidate(
        row(
            id=uuid4(),
            amount=Decimal("125.00"),
            currency="USD",
            lifecycle="settled",
            provider_safe_reference="bank-tx-1",
            evidence_digest=DIGEST,
        ),  # type: ignore[arg-type]
        row(method_type=method),  # type: ignore[arg-type]
        row(
            id=execution_id,
            authorized_at=NOW,
            provider_identity="fixture-payroll",
            execution_digest="d" * 64,
        ),  # type: ignore[arg-type]
    )
    assert candidate.target_type == expected_type
    assert (
        deterministic_match(
            evidence(
                direction="outflow", related_identity=candidate.target_identity
            ),
            (candidate,),
        ).state
        is MatchState.MATCHED
    )


def test_unsettled_payroll_is_review_only() -> None:
    candidate = payroll_payment_candidate(
        row(
            id=uuid4(),
            amount=Decimal("125.00"),
            currency="USD",
            lifecycle="acknowledged",
            provider_safe_reference="bank-tx-1",
            evidence_digest=DIGEST,
        ),  # type: ignore[arg-type]
        row(method_type="ach"),  # type: ignore[arg-type]
        row(
            id=uuid4(),
            authorized_at=NOW,
            provider_identity="fixture-payroll",
            execution_digest="d" * 64,
        ),  # type: ignore[arg-type]
    )
    assert candidate.explicit_bank_source_identity is None
    assert (
        deterministic_match(evidence(direction="outflow"), (candidate,)).state
        is MatchState.REVIEW_REQUIRED
    )


def test_transfer_pair_is_neutral_candidate_and_one_sided_is_review_only() -> None:
    journal = row(
        id=uuid4(),
        source_type="bank_transfer",
        source_identity="bank-tx-1",
        source_system="accounting",
        source_digest=DIGEST,
        currency="USD",
        effective_date=DAY,
    )
    line = row(id=uuid4(), debit=Decimal("125.00"), credit=Decimal(0))
    paired = accounting_movement_candidate(journal, line, True)  # type: ignore[arg-type]
    one_sided = accounting_movement_candidate(journal, line, False)  # type: ignore[arg-type]
    assert (
        deterministic_match(
            evidence(related_identity=paired.target_identity), (paired,)
        ).state
        is MatchState.MATCHED
    )
    assert one_sided.explicit_bank_source_identity is None
    assert deterministic_match(evidence(), (one_sided,)).state is MatchState.REVIEW_REQUIRED


def test_owner_movement_requires_review_even_with_accounting_evidence() -> None:
    candidate = accounting_movement_candidate(
        row(
            id=uuid4(),
            source_type="owner_distribution",
            source_identity="bank-tx-1",
            source_system="accounting",
            source_digest=DIGEST,
            currency="USD",
            effective_date=DAY,
        ),  # type: ignore[arg-type]
        row(id=uuid4(), debit=Decimal(0), credit=Decimal("125.00")),  # type: ignore[arg-type]
    )
    assert candidate.explicit_bank_source_identity is None
    assert (
        deterministic_match(evidence(direction="outflow"), (candidate,)).state
        is MatchState.REVIEW_REQUIRED
    )


@pytest.mark.asyncio
async def test_adapter_query_is_company_scoped_and_period_bounded() -> None:
    company_id = uuid4()
    result = row(all=list)
    session = row(scalars=AsyncMock(return_value=result))
    await BankMatchCandidateAdapterService().vendor_payments(
        session,  # type: ignore[arg-type]
        company_id=company_id,
        currency="USD",
        period_start=date(2026, 9, 25),
        period_end=DAY,
    )
    statement = session.scalars.await_args.args[0]
    values = tuple(statement.compile().params.values())
    assert company_id in values
    assert date(2026, 9, 25) in values
    assert DAY in values


def test_ambiguous_same_amount_and_unmatched_never_auto_match() -> None:
    candidate = customer_payment_candidate(
        row(
            id=uuid4(),
            captured_amount=Decimal("125.00"),
            currency="USD",
            captured_at=NOW,
            evidence_digest=DIGEST,
        ),  # type: ignore[arg-type]
        row(provider_operation_id="bank-tx-1", provider="fixture"),  # type: ignore[arg-type]
    )
    assert (
        deterministic_match(
            evidence(related_identity=candidate.target_identity),
            (candidate, candidate),
        ).state
        is MatchState.AMBIGUOUS
    )
    assert deterministic_match(evidence(amount=Decimal("7.00")), (candidate,)).state is MatchState.UNMATCHED
