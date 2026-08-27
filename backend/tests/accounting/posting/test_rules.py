from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.posting.contracts import (
    PostingFact,
    PostingLeg,
    PostingRule,
    PostingSide,
)
from app.accounting.posting.rules import PostingRuleRegistry


def _rule(*, company_id=None, start=date(2026, 1, 1), end=None, enabled=True):
    return PostingRule(
        company_id=company_id or uuid4(),
        event_type="invoice.issued",
        version="invoice-issued-v1",
        effective_from=start,
        effective_to=end,
        approved_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
        approved_by_user_id=uuid4(),
        legs=(
            PostingLeg("gross", uuid4(), PostingSide.DEBIT, "Accounts receivable"),
            PostingLeg("gross", uuid4(), PostingSide.CREDIT, "Revenue"),
        ),
        enabled=enabled,
    )


def _fact(company_id):
    return PostingFact(
        schema_version="1.0",
        company_id=company_id,
        branch_id=uuid4(),
        source_event_id=uuid4(),
        source_type="invoice",
        source_id=uuid4(),
        event_type="invoice.issued",
        effective_date=date(2026, 8, 27),
        occurred_at=datetime(2026, 8, 27, 12, tzinfo=timezone.utc),
        currency="USD",
        components={"gross": Decimal("125.25")},
        evidence_digest="a" * 64,
    )


def test_rule_resolution_is_company_and_effective_date_scoped() -> None:
    company_id = uuid4()
    selected = _rule(company_id=company_id)
    other_company = _rule()
    assert PostingRuleRegistry((selected, other_company)).resolve(_fact(company_id)) is selected


def test_overlapping_enabled_rules_fail_closed() -> None:
    company_id = uuid4()
    with pytest.raises(AccountingConflict, match="overlap"):
        PostingRuleRegistry(
            (
                _rule(company_id=company_id, end=date(2026, 8, 31)),
                _rule(company_id=company_id, start=date(2026, 8, 1)),
            )
        )


def test_missing_or_disabled_mapping_requires_reconciliation() -> None:
    company_id = uuid4()
    registry = PostingRuleRegistry((_rule(company_id=company_id, enabled=False),))
    with pytest.raises(AccountingValidation, match="Exactly one"):
        registry.resolve(_fact(company_id))


def test_canonical_digest_is_order_independent_and_evidence_excluding() -> None:
    company_id = uuid4()
    fact = _fact(company_id)
    same = replace(
        fact,
        components={"gross": Decimal("125.250")},
        evidence_digest="b" * 64,
    )
    assert same.canonical_digest() == fact.canonical_digest()
