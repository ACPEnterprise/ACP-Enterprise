from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.lia.contracts import (
    EvidenceReference,
    NavigationSuggestion,
    evidence_set_digest,
)


def evidence(**overrides: object) -> EvidenceReference:
    values: dict[str, object] = {
        "domain": "jobs",
        "label": "Job",
        "authority": "JOB.LIA_CONTEXT.v1",
        "observed_at": datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        "freshness": "CURRENT_QUERY",
        "entity_id": uuid4(),
        "evidence_digest": "a" * 64,
        "source_contract_version": "JOB.LIA_CONTEXT.v1",
        "company_id": uuid4(),
        "branch_ids": (uuid4(),),
        "authorization_version": 7,
        "period_start": date(2026, 9, 17),
        "period_end": date(2026, 9, 17),
        "timezone": "America/New_York",
    }
    values.update(overrides)
    return EvidenceReference.model_validate(values)


def test_digest_is_stable_across_order_and_observation_time() -> None:
    first = evidence()
    second = evidence(domain="scheduling", evidence_digest="b" * 64)
    later = first.model_copy(
        update={"observed_at": datetime(2026, 9, 17, 12, 5, tzinfo=UTC)}
    )

    assert evidence_set_digest((first, second)) == evidence_set_digest((second, later))


def test_digest_binds_domain_identity_scope_period_and_authority() -> None:
    original = evidence()
    original_digest = evidence_set_digest((original,))
    changes = (
        {"domain": "customers"},
        {"entity_id": uuid4()},
        {"company_id": uuid4()},
        {"branch_ids": (uuid4(),)},
        {"authorization_version": 8},
        {"period_start": date(2026, 9, 16)},
        {"authority": "SOURCE_BACKED"},
        {"source_contract_version": "JOB.LIA_CONTEXT.v2"},
        {"evidence_digest": "c" * 64},
    )

    assert all(
        evidence_set_digest((original.model_copy(update=change),)) != original_digest
        for change in changes
    )


def test_empty_evidence_digest_is_deterministic_but_not_a_source_digest() -> None:
    assert evidence_set_digest(()) == evidence_set_digest(())
    assert evidence_set_digest(()) != "a" * 64


@pytest.mark.parametrize(
    "path",
    (
        "https://outside.invalid/payroll",
        "//outside.invalid/payroll",
        "/jobs/../payroll",
        "/jobs\\outside",
        "/jobs/1\n/payroll",
    ),
)
def test_navigation_contract_rejects_unbounded_destinations(path: str) -> None:
    with pytest.raises(ValidationError, match="bounded internal path"):
        NavigationSuggestion(label="Unsafe", internal_path=path)


def test_navigation_contract_accepts_scoped_internal_path() -> None:
    suggestion = NavigationSuggestion(
        label="Open Invoice", internal_path="/invoices/123?returnTo=%2Fcustomers#detail"
    )
    assert suggestion.internal_path.startswith("/invoices/")
