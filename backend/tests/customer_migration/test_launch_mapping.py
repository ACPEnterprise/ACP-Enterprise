from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest
from app.customer_migration.launch_mapping import (
    AUTHORITATIVE_ENTERPRISE_ALEMBIC_HEAD,
    AUTHORITATIVE_ENTERPRISE_COMMIT,
    V1_MAPPING_REGISTRY,
    V1_MAPPINGS,
    EntityDisposition,
    LaunchMappingReconciler,
    ReconciliationOutcome,
    SyntheticMappingObservation,
    build_v1_registry,
    preserve_exact_money,
)

COMPANY = UUID(int=1)
BRANCH = UUID(int=2)


def observation(entity: str, fields: dict[str, object]) -> SyntheticMappingObservation:
    return SyntheticMappingObservation(
        COMPANY,
        BRANCH,
        entity,
        "synthetic-provider",
        f"synthetic-{entity}",
        tuple(fields.items()),
        parent_identity="synthetic-parent",
    )


def reconcile(value: SyntheticMappingObservation):
    return LaunchMappingReconciler(V1_MAPPING_REGISTRY).reconcile(
        value, expected_company_id=COMPANY, expected_branch_id=BRANCH
    )


def test_registry_freezes_all_ten_entities_and_owner_dispositions() -> None:
    assert tuple(V1_MAPPINGS) == (
        "customer",
        "contact",
        "service_location",
        "job",
        "appointment",
        "estimate",
        "invoice",
        "payment",
        "note",
        "attachment",
    )
    assert build_v1_registry() == V1_MAPPING_REGISTRY
    assert AUTHORITATIVE_ENTERPRISE_COMMIT == "06ba0f39b85b0eeda7e5a4d1747bb326bd28668a"
    assert AUTHORITATIVE_ENTERPRISE_ALEMBIC_HEAD == "t5j7f9b1c386"
    assert {
        V1_MAPPINGS[name].disposition for name in ("estimate", "note", "attachment")
    } == {EntityDisposition.EXCLUDED_FROM_V1_BY_OWNER}
    assert {
        V1_MAPPINGS[name].disposition
        for name in ("customer", "contact", "service_location")
    } == {EntityDisposition.INCLUDED_UNMAPPED_OPTIONAL_FIELD}


@pytest.mark.parametrize(
    ("entity", "fields"),
    (
        ("customer", {"customer_type": "residential", "display_name": "Synthetic"}),
        ("contact", {"first_name": "Synthetic", "last_name": "Contact"}),
        (
            "service_location",
            {
                "source_customer_id": "c",
                "address": "1 Test",
                "city": "Test",
                "state": "NY",
                "postal_code": "10000",
            },
        ),
        (
            "job",
            {
                "source_customer_id": "c",
                "source_service_location_id": "l",
                "status": "completed",
            },
        ),
        (
            "appointment",
            {
                "source_job_id": "j",
                "source_customer_id": "c",
                "source_service_location_id": "l",
                "status": "completed",
            },
        ),
        (
            "invoice",
            {
                "source_job_id": "j",
                "status": "draft",
                "currency": "USD",
                "subtotal_amount": Decimal("10.00"),
                "tax_amount": Decimal("0.00"),
                "total_amount": Decimal("10.00"),
                "line_items": (),
            },
        ),
        (
            "payment",
            {
                "source_invoice_id": "i",
                "status": "succeeded",
                "currency": "USD",
                "amount": Decimal("10.00"),
            },
        ),
    ),
)
def test_all_included_mappings_accept_synthetic_contract_evidence(
    entity: str, fields: dict[str, object]
) -> None:
    result = reconcile(observation(entity, fields))
    assert result.outcome is ReconciliationOutcome.ACCEPTED
    assert dict(result.mapped_fields) == fields


@pytest.mark.parametrize("entity", ("estimate", "note", "attachment"))
def test_v1_exclusions_are_explicit_and_cannot_map(entity: str) -> None:
    result = reconcile(observation(entity, {}))
    assert result.outcome is ReconciliationOutcome.EXCLUDED
    assert result.reason_code == "excluded_by_owner"
    assert result.mapped_fields == ()


@pytest.mark.parametrize(
    ("entity", "field", "value"),
    (
        ("customer", "is_vip", False),
        ("contact", "can_approve_work", False),
        ("service_location", "is_primary", False),
    ),
)
def test_unmapped_optional_fields_remain_absent_and_are_never_defaulted(
    entity: str, field: str, value: object
) -> None:
    mapping = V1_MAPPINGS[entity]
    fields = {name: "synthetic" for name in mapping.required_fields}
    accepted = reconcile(observation(entity, fields))
    assert field not in dict(accepted.mapped_fields)
    conflict = reconcile(observation(entity, {**fields, field: value}))
    assert conflict.outcome is ReconciliationOutcome.CONFLICT
    assert conflict.reason_code == "unmapped_optional_field_present"


@pytest.mark.parametrize(
    ("change", "outcome", "reason"),
    (
        (
            {"source_identity": None},
            ReconciliationOutcome.REJECTED,
            "missing_source_identity",
        ),
        ({"parent_resolved": False}, ReconciliationOutcome.REJECTED, "missing_parent"),
        (
            {"duplicate_identity": True},
            ReconciliationOutcome.DUPLICATE,
            "duplicate_source_identity",
        ),
        (
            {"ambiguous_identity": True},
            ReconciliationOutcome.AMBIGUOUS,
            "ambiguous_identity",
        ),
        (
            {"conflicting_evidence": True},
            ReconciliationOutcome.CONFLICT,
            "conflicting_evidence",
        ),
        (
            {"company_id": UUID(int=9)},
            ReconciliationOutcome.CONFLICT,
            "company_scope_conflict",
        ),
        (
            {"branch_id": UUID(int=9)},
            ReconciliationOutcome.CONFLICT,
            "branch_scope_conflict",
        ),
    ),
)
def test_identity_parent_duplicate_ambiguity_conflict_and_scope_fail_closed(
    change: dict[str, object], outcome: ReconciliationOutcome, reason: str
) -> None:
    value = observation(
        "job",
        {
            "source_customer_id": "c",
            "source_service_location_id": "l",
            "status": "completed",
        },
    )
    result = reconcile(replace(value, **change))
    assert result.outcome is outcome
    assert result.reason_code == reason


def test_owner_disposition_and_replay_are_deterministic() -> None:
    value = replace(
        observation(
            "customer", {"customer_type": "commercial", "display_name": "Synthetic"}
        ),
        owner_disposition_required=True,
    )
    blocked = reconcile(value)
    assert blocked.outcome is ReconciliationOutcome.OWNER_DISPOSITION_REQUIRED
    approved = reconcile(replace(value, owner_disposition_evidence_sha256="a" * 64))
    assert approved.outcome is ReconciliationOutcome.ACCEPTED
    assert approved == reconcile(
        replace(value, owner_disposition_evidence_sha256="a" * 64)
    )
    assert approved.reconciliation_id.version == 5


def test_unsupported_lifecycle_fails_closed() -> None:
    result = reconcile(
        observation(
            "job",
            {
                "source_customer_id": "c",
                "source_service_location_id": "l",
                "status": "provider_unknown",
            },
        )
    )
    assert result.outcome is ReconciliationOutcome.REJECTED
    assert result.reason_code == "unsupported_lifecycle"


def test_money_is_preserved_exactly_without_quantization_or_inference() -> None:
    value = Decimal("10.0010")
    assert preserve_exact_money(value) is value
    with pytest.raises(ValueError, match="finite"):
        preserve_exact_money(Decimal("NaN"))
