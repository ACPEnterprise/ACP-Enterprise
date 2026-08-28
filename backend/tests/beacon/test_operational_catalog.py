from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.beacon.catalog import (
    OPERATIONAL_SIGNAL_CATALOG,
    OperationalConflictPolicy,
    OperationalSignalAdmission,
    OperationalSignalCatalog,
    OperationalSignalFamily,
    OperationalSignalIdentityInput,
)
from app.beacon.router import operational_signal_catalog

COMPANY_ID = UUID("10000000-0000-0000-0000-000000000001")
OTHER_COMPANY_ID = UUID("10000000-0000-0000-0000-000000000002")
BRANCH_ID = UUID("20000000-0000-0000-0000-000000000001")
OTHER_BRANCH_ID = UUID("20000000-0000-0000-0000-000000000002")
SUBJECT_ID = UUID("30000000-0000-0000-0000-000000000001")
EVIDENCE_DIGEST = "a" * 64


def identity(
    *,
    company_id: UUID = COMPANY_ID,
    branch_id: UUID | None = BRANCH_ID,
    evidence_digest: str = EVIDENCE_DIGEST,
    evidence_ids: tuple[str, ...] = ("event:accepted-1", "appointment:source-1"),
) -> OperationalSignalIdentityInput:
    return OperationalSignalIdentityInput(
        company_id=company_id,
        branch_id=branch_id,
        subject_id=SUBJECT_ID,
        evidence_digest=evidence_digest,
        source_evidence_ids=evidence_ids,
    )


def test_catalog_is_stable_versioned_complete_and_immutable() -> None:
    catalog = OPERATIONAL_SIGNAL_CATALOG

    assert catalog.catalog_id == "BANK.BEA.001"
    assert catalog.version == 1
    assert len(catalog.definitions) == 21
    assert len(catalog.catalog_digest) == 64
    assert {item.family for item in catalog.definitions} == set(OperationalSignalFamily)
    assert all(item.version == 1 for item in catalog.definitions)
    assert all(len(item.definition_digest) == 64 for item in catalog.definitions)
    assert len({item.definition_digest for item in catalog.definitions}) == 21
    with pytest.raises(FrozenInstanceError):
        catalog.version = 2  # type: ignore[misc]


def test_only_rules_with_existing_accepted_adapters_are_evaluated() -> None:
    admitted = {
        item.definition_id: item.evaluator_rule_code
        for item in OPERATIONAL_SIGNAL_CATALOG.definitions
        if item.admission is OperationalSignalAdmission.EVALUATED
    }
    assert admitted == {
        "operational.scheduling.appointment_overdue": (
            "scheduling.overdue_committed_appointments"
        ),
        "operational.job.intermediate_state_stalled": "operations.paused_jobs",
    }
    assert all(
        item.evaluator_rule_code is None
        for item in OPERATIONAL_SIGNAL_CATALOG.definitions
        if item.admission is OperationalSignalAdmission.REQUIRES_AUTHORITATIVE_ADAPTER
    )


def test_identical_authoritative_inputs_have_identical_signal_identity() -> None:
    catalog = OPERATIONAL_SIGNAL_CATALOG
    definition_id = "operational.scheduling.appointment_overdue"

    first = catalog.signal_identity(definition_id, identity())
    second = catalog.signal_identity(
        definition_id,
        identity(evidence_ids=("appointment:source-1", "event:accepted-1")),
    )

    assert first == second


def test_company_and_branch_are_part_of_signal_identity() -> None:
    catalog = OPERATIONAL_SIGNAL_CATALOG
    definition_id = "operational.dispatch.state_stalled"
    baseline = catalog.signal_identity(definition_id, identity())

    assert baseline != catalog.signal_identity(
        definition_id, identity(company_id=OTHER_COMPANY_ID)
    )
    assert baseline != catalog.signal_identity(
        definition_id, identity(branch_id=OTHER_BRANCH_ID)
    )
    assert baseline != catalog.signal_identity(definition_id, identity(branch_id=None))


@pytest.mark.parametrize(
    ("evidence_digest", "evidence_ids"),
    [
        ("", ("event:1",)),
        ("g" * 64, ("event:1",)),
        (EVIDENCE_DIGEST, ()),
        (EVIDENCE_DIGEST, ("event:1", "event:1")),
        (EVIDENCE_DIGEST, (" ",)),
    ],
)
def test_missing_or_invalid_evidence_fails_closed(
    evidence_digest: str, evidence_ids: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError):
        OPERATIONAL_SIGNAL_CATALOG.signal_identity(
            "operational.dispatch.state_stalled",
            identity(evidence_digest=evidence_digest, evidence_ids=evidence_ids),
        )


def test_conflict_signals_report_existence_without_resolving_precedence() -> None:
    conflict_definitions = tuple(
        item
        for item in OPERATIONAL_SIGNAL_CATALOG.definitions
        if item.conflict_policy
        is OperationalConflictPolicy.SIGNAL_CONFLICT_EXISTENCE_ONLY
    )
    assert conflict_definitions
    assert all(
        "conflict" in item.condition.lower() or "inconsistent" in item.condition.lower()
        for item in conflict_definitions
    )
    assert all(
        "conflicting_fact_identities" in item.required_evidence_types
        or set(item.required_evidence_types) == {"arrival_event", "execution_event"}
        or set(item.required_evidence_types)
        == {"assignment_state", "availability_evidence"}
        for item in conflict_definitions
    )


def test_catalog_rejects_duplicate_or_unadmitted_evaluator_definitions() -> None:
    definition = OPERATIONAL_SIGNAL_CATALOG.definitions[0]
    with pytest.raises(ValueError, match="identity and version"):
        OperationalSignalCatalog("test", 1, (definition, definition))
    with pytest.raises(ValueError, match="Unadmitted"):
        OperationalSignalCatalog(
            "test",
            1,
            (replace(definition, evaluator_rule_code="not.accepted"),),
        )


def test_catalog_contains_no_economic_or_autonomous_policy() -> None:
    rendered = " ".join(
        str(value)
        for definition in OPERATIONAL_SIGNAL_CATALOG.definitions
        for value in definition.payload().values()
    ).lower()
    assert all(
        term not in rendered
        for term in (
            "profitability",
            "margin",
            "revenue recognition",
            "financial materiality",
            "overhead",
            "autonomous",
            "reschedule appointment",
            "dispatch worker",
        )
    )


@pytest.mark.asyncio
async def test_catalog_api_is_context_scoped_and_explanation_safe() -> None:
    context = SimpleNamespace(
        company=SimpleNamespace(id=COMPANY_ID),
        active_branch=SimpleNamespace(id=BRANCH_ID),
    )

    response = await operational_signal_catalog(context)  # type: ignore[arg-type]

    assert response.company_id == COMPANY_ID
    assert response.active_branch_id == BRANCH_ID
    assert response.catalog_digest == OPERATIONAL_SIGNAL_CATALOG.catalog_digest
    assert len(response.definitions) == 21
    assert all(item.definition_digest for item in response.definitions)
    assert not hasattr(response.definitions[0], "source_evidence")


def test_catalog_construction_and_identity_are_side_effect_free() -> None:
    before = OPERATIONAL_SIGNAL_CATALOG
    first = before.signal_identity(
        "operational.job.completion_evidence_inconsistent", identity()
    )
    second = before.signal_identity(
        "operational.job.completion_evidence_inconsistent", identity()
    )
    assert first == second
    assert OPERATIONAL_SIGNAL_CATALOG is before
