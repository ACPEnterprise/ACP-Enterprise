from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.business_economics.cash_operational import (
    RecognitionEvidence,
    RecognitionKind,
    compose_cash_operational_economics,
    recognition_contract,
)
from app.business_economics.cash_operational_service import (
    CashOperationalEconomicsService,
)
from app.business_economics.integrity import EconomicMeaning, classify_source_semantics

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")


def item(
    identity: str,
    kind: RecognitionKind,
    amount: str,
    *,
    day: date = date(2026, 7, 31),
    branch_id: UUID | None = BRANCH,
    company_id: UUID = COMPANY,
    currency: str = "USD",
    complete: bool = True,
) -> RecognitionEvidence:
    return RecognitionEvidence(
        identity,
        (identity[-1] if identity else "a") * 64,
        f"synthetic.{kind.value}.v1",
        company_id,
        branch_id,
        kind,
        Decimal(amount),
        currency,
        day,
        work_period="2026-07" if day.month == 7 else None,
        cash_period="2026-08" if day.month == 8 else None,
        accounting_period="2026-08"
        if kind is RecognitionKind.ACCOUNTING_RECOGNITION
        else None,
        complete=complete,
    )


def test_net_terms_work_stays_economic_while_cash_is_separate() -> None:
    value = compose_cash_operational_economics(
        (
            item("earned-a", RecognitionKind.EARNED_ECONOMIC_EVIDENCE, "1200.00"),
            item("invoice-b", RecognitionKind.COMMERCIAL_INVOICE, "1200.00"),
            item("open-c", RecognitionKind.OPEN_RECEIVABLE, "700.00"),
            item(
                "settled-d", RecognitionKind.SETTLEMENT, "500.00", day=date(2026, 8, 8)
            ),
            item(
                "cash-e",
                RecognitionKind.ACCOUNTING_RECOGNITION,
                "500.00",
                day=date(2026, 8, 8),
            ),
        )
    )
    assert value.totals["earned_economic_evidence"] == Decimal("1200.00")
    assert value.totals["open_receivable"] == Decimal("700.00")
    assert value.totals["settlement"] == Decimal("500.00")
    assert value.totals["accounting_recognition"] == Decimal("500.00")
    assert (
        value.totals["earned_economic_evidence"]
        != value.totals["accounting_recognition"]
    )


def test_vendor_and_credit_card_timing_do_not_duplicate_job_cost() -> None:
    value = compose_cash_operational_economics(
        (
            item("consume-a", RecognitionKind.MATERIAL_CONSUMPTION, "300.00"),
            item("purchase-b", RecognitionKind.MATERIAL_PURCHASE, "300.00"),
            item("card-c", RecognitionKind.OPEN_CARD_LIABILITY, "300.00"),
            item(
                "cardpay-d",
                RecognitionKind.CARD_SETTLEMENT,
                "300.00",
                day=date(2026, 8, 20),
            ),
            item(
                "outflow-e",
                RecognitionKind.BANK_OUTFLOW,
                "300.00",
                day=date(2026, 8, 20),
            ),
        )
    )
    assert value.totals["material_consumption"] == Decimal("300.00")
    assert value.totals["card_settlement"] == Decimal("300.00")
    assert value.totals["bank_outflow"] == Decimal("300.00")
    # The lifecycle totals are intentionally not added into a second Job cost.
    assert value.totals["material_consumption"] == Decimal("300.00")


def test_paid_at_service_and_partial_payment_preserve_each_stage() -> None:
    value = compose_cash_operational_economics(
        (
            item("work-a", RecognitionKind.WORK_PERFORMED, "900.00"),
            item("earned-b", RecognitionKind.EARNED_ECONOMIC_EVIDENCE, "900.00"),
            item("invoice-c", RecognitionKind.COMMERCIAL_INVOICE, "900.00"),
            item("assert-d", RecognitionKind.PAYMENT_ASSERTION, "400.00"),
            item("receipt-e", RecognitionKind.CASH_RECEIPT, "400.00"),
            item("open-f", RecognitionKind.OPEN_RECEIVABLE, "500.00"),
        )
    )
    assert value.totals["work_performed"] == Decimal("900.00")
    assert value.totals["payment_assertion"] == Decimal("400.00")
    assert value.totals["cash_receipt"] == Decimal("400.00")
    assert value.totals["open_receivable"] == Decimal("500.00")
    assert value.totals["accounting_recognition"] == 0


def test_replay_is_deterministic_and_source_order_independent() -> None:
    evidence = (
        item("earned-a", RecognitionKind.EARNED_ECONOMIC_EVIDENCE, "10.00"),
        item("open-b", RecognitionKind.OPEN_RECEIVABLE, "10.00", complete=False),
    )
    first = compose_cash_operational_economics(evidence)
    second = compose_cash_operational_economics(tuple(reversed(evidence)))
    assert first.composition_digest == second.composition_digest
    assert first.incomplete_evidence_ids == ("open-b",)


@pytest.mark.parametrize("mismatch", ["company", "branch", "currency"])
def test_scope_mismatch_fails_closed(mismatch: str) -> None:
    kwargs: dict[str, object] = {}
    if mismatch == "company":
        kwargs["company_id"] = UUID("10000000-0000-0000-0000-000000000002")
    elif mismatch == "branch":
        kwargs["branch_id"] = UUID("20000000-0000-0000-0000-000000000002")
    else:
        kwargs["currency"] = "CAD"
    with pytest.raises(
        ValueError,
        match=f"cross-{mismatch.capitalize() if mismatch != 'currency' else 'currency'}",
    ):
        compose_cash_operational_economics(
            (
                item("earned-a", RecognitionKind.EARNED_ECONOMIC_EVIDENCE, "10.00"),
                item("other-b", RecognitionKind.OPEN_RECEIVABLE, "10.00", **kwargs),
            )
        )


def test_duplicate_and_contradictory_sources_fail_closed() -> None:
    accepted = item("earned-a", RecognitionKind.EARNED_ECONOMIC_EVIDENCE, "10.00")
    with pytest.raises(ValueError, match="exactly once"):
        compose_cash_operational_economics((accepted, accepted))
    contradiction = replace(accepted, evidence_digest="f" * 64)
    with pytest.raises(ValueError, match="contradictory"):
        compose_cash_operational_economics((accepted, contradiction))


def test_contract_never_implies_cash_from_invoice_payment_or_deposit() -> None:
    contract = recognition_contract()
    rows = {row["kind"]: row for row in contract["stages"]}
    for source in ("commercial_invoice", "payment_assertion", "settlement", "deposit"):
        assert "accounting_recognition" in rows[source]["does_not_imply"]
    assert contract["migration_boundary"] == "readiness_metadata_only_no_protected_rows"


def test_owner_answers_keep_work_obligations_and_cash_separate() -> None:
    answers = CashOperationalEconomicsService._owner_answers(
        earned={
            "state": "COMPLETE",
            "earned_revenue_minor": 120_000,
        },
        operational={
            "state": "AVAILABLE",
            "completed_work_open_commercial_balance_minor": 70_000,
            "open_vendor_obligation_minor": 12_000,
        },
        accounting={
            "state": "EXTERNAL_GATE",
            "recognized_income_minor": None,
        },
    )
    by_question = {answer["question"]: answer for answer in answers}
    assert by_question["How much work did we perform?"]["answer_minor"] == 120_000
    assert by_question["How much cash did we collect?"]["answer_minor"] is None
    assert (
        by_question["How much completed work remains unpaid?"]["answer_minor"] == 70_000
    )
    assert (
        "admitted_cash_basis_accounting_report"
        in by_question["Which evidence is missing before this answer is complete?"][
            "items"
        ]
    )


@pytest.mark.parametrize(
    ("source", "meaning"),
    [
        ("payment_assertion", EconomicMeaning.OPERATIONAL_ONLY),
        ("deposit", EconomicMeaning.OPERATIONAL_ONLY),
        ("open_receivable", EconomicMeaning.OPERATIONAL_ONLY),
        ("open_vendor_obligation", EconomicMeaning.OPERATIONAL_ONLY),
        ("credit_card_settlement", EconomicMeaning.SETTLEMENT_EVIDENCE),
    ],
)
def test_integrity_semantics_prevent_cash_and_cost_double_counting(
    source: str, meaning: EconomicMeaning
) -> None:
    assert classify_source_semantics(source).meaning is meaning


@pytest.mark.asyncio
async def test_owner_projection_is_bounded_and_never_substitutes_accounting_cash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def economics(*_args, **_kwargs):
        return {
            "quality_state": "complete",
            "currency": "USD",
            "totals": {"revenue": 120_000, "gross_profit": 60_000},
            "job_count": 2,
            "complete_job_count": 2,
        }

    monkeypatch.setattr(
        "app.business_economics.cash_operational_service.EconomicsWorkspaceService.overview",
        economics,
    )

    class Result:
        def __init__(self, row):
            self.row = row

        def one(self):
            return self.row

    class Session:
        rows = iter(
            (
                (1, Decimal("700.00"), 1, "USD"),
                (1, Decimal("500.00"), 1, "USD"),
                (1, Decimal("500.00"), 1, "USD"),
                (2, Decimal("300.00"), 1, "USD"),
                (1, Decimal("100.00"), 1, "USD"),
            )
        )

        async def execute(self, _query):
            return Result(next(self.rows))

        async def scalar(self, _query):
            return SimpleNamespace(accounting_basis="cash", currency="USD")

    context = SimpleNamespace(
        company=SimpleNamespace(id=COMPANY),
        active_branch=SimpleNamespace(id=BRANCH),
    )
    value = await CashOperationalEconomicsService().overview(
        Session(),
        context=context,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
    )
    assert value["work_period"]["earned_revenue_minor"] == 120_000
    assert (
        value["operational_current_state"][
            "completed_work_open_commercial_balance_minor"
        ]
        == 70_000
    )
    assert value["cash_accounting_period"]["basis"] == "cash"
    assert value["cash_accounting_period"]["recognized_income_minor"] is None
    assert value["mutation_authority"] == "none"
