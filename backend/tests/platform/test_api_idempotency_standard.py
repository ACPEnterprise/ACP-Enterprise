from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from app.main import app
from app.platform.contracts.manifest import platform_contract_manifest
from app.platform.idempotency.contracts import (
    ContradictoryReplayError,
    IdempotencyIdentity,
    ReplayAuthorizationError,
    ReplayDecision,
    canonical_request_digest,
    decide_replay,
)
from app.platform.idempotency.coverage import (
    MutationClassification,
    MutationCoverageRegistry,
    mutation_coverage_registry,
)

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
IDEMPOTENCY_FIELDS = {
    "idempotency_key",
    "client_idempotency_key",
    "request_key",
    "request_id",
}
DOMAIN_REPLAY_EVIDENCE = {
    "accounting": "tests/accounting/posting/test_service.py",
    "accounts_payable": "tests/accounts_payable/test_invariants.py",
    "beacon": "tests/beacon/test_native_financial_signals.py",
    "communications": "tests/communications/test_communications_persistence.py",
    "dispatch": "tests/dispatch/test_dispatch_api.py",
    "engineering": "tests/engineering_control/repository_operation/test_repository_operation.py",
    "engineering_commands": "tests/engineering_control/test_mobile_engineering_api.py",
    "engineering_executions": "tests/engineering_execution/test_engineering_execution.py",
    "identity_onboarding": "tests/platform/test_identity_onboarding.py",
    "inventory": "tests/inventory/test_inventory_adjustments.py",
    "invoices": "tests/invoicing/test_invoice_ar.py",
    "operations": "tests/operations/test_operations_service.py",
    "payments": "tests/payments/test_provider_boundary.py",
    "price_book": "tests/price_book/test_price_book_service.py",
    "purchasing": "tests/purchasing/test_purchasing_foundation.py",
    "scheduling": "tests/scheduling/test_scheduling_api.py",
    "technician": "tests/field_service/test_contract_surface.py",
    "timekeeping": "tests/timekeeping/test_workday_authority.py",
    "worker_transport": "tests/worker_control/transport/test_worker_transport.py",
}


def _schema_properties(
    schema: dict[str, object],
    components: dict[str, dict[str, object]],
    seen: frozenset[str] = frozenset(),
) -> set[str]:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        name = reference.rsplit("/", 1)[-1]
        if name in seen:
            return set()
        return _schema_properties(components[name], components, seen | {name})
    properties = set(schema.get("properties", {}))
    for composition in ("allOf", "anyOf", "oneOf"):
        for child in schema.get(composition, []):
            properties.update(_schema_properties(child, components, seen))
    return properties


def _mutation_operations() -> dict[tuple[str, str], dict[str, object]]:
    schema = app.openapi()
    return {
        (method.upper(), path): operation
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method.upper() in MUTATION_METHODS
    }


def test_every_mutating_operation_has_exactly_one_current_classification() -> None:
    operations = _mutation_operations()
    coverage = mutation_coverage_registry.by_identity()
    assert operations.keys() == coverage.keys()
    assert len(operations) == len(coverage) == 251
    for identity, operation in operations.items():
        assert operation["operationId"] == coverage[identity].operation_id


def test_required_operations_expose_an_accepted_request_identity() -> None:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]
    operations = _mutation_operations()
    required = tuple(
        entry
        for entry in mutation_coverage_registry.entries
        if entry.classification is MutationClassification.REQUIRED
    )
    assert len(required) == 102
    for entry in required:
        operation = operations[entry.identity]
        schema = (
            operation.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        header_names = {
            parameter.get("name")
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "header"
        }
        assert (
            _schema_properties(schema, components) & IDEMPOTENCY_FIELDS
            or "Idempotency-Key" in header_names
        ), entry.identity


def test_required_domains_have_replay_and_conflict_evidence() -> None:
    required_domains = {
        entry.domain
        for entry in mutation_coverage_registry.entries
        if entry.classification is MutationClassification.REQUIRED
    }
    assert required_domains == DOMAIN_REPLAY_EVIDENCE.keys()
    for evidence_path in DOMAIN_REPLAY_EVIDENCE.values():
        evidence = Path(evidence_path).read_text(encoding="utf-8").lower()
        assert "idempot" in evidence or "replay" in evidence


def test_append_only_classification_requires_concrete_replay_evidence() -> None:
    append_only = tuple(
        entry
        for entry in mutation_coverage_registry.entries
        if entry.classification is MutationClassification.APPEND_ONLY
    )
    assert len(append_only) == 5
    assert all(entry.replay_evidence for entry in append_only)
    for entry in append_only:
        for evidence_path in entry.replay_evidence:
            evidence = Path(evidence_path).read_text(encoding="utf-8").lower()
            assert "replay" in evidence or "duplicate" in evidence

    unsupported = replace(append_only[0], replay_evidence=())
    entries = tuple(
        unsupported if entry.identity == unsupported.identity else entry
        for entry in mutation_coverage_registry.entries
    )
    with pytest.raises(ValueError, match="requires concrete replay evidence"):
        MutationCoverageRegistry(entries=entries, fingerprint="invalid")


def test_unproven_append_only_operations_are_explicit_exemptions() -> None:
    coverage = mutation_coverage_registry.by_identity()
    unproven = {
        ("POST", "/api/v1/customers/{customer_id}/consents"),
        ("POST", "/api/v1/customers/{customer_id}/notes"),
        ("POST", "/api/v1/events"),
    }
    assert all(
        coverage[identity].classification is MutationClassification.EXEMPT
        and not coverage[identity].replay_evidence
        for identity in unproven
    )


def test_replenishment_decision_has_concrete_company_scoped_replay_evidence() -> None:
    identity = ("POST", "/api/v1/purchasing/replenishment/decisions")
    entry = mutation_coverage_registry.by_identity()[identity]
    assert entry.classification is MutationClassification.REQUIRED
    assert entry.tenant_scope == "COMPANY_WITH_BRANCH_CONTEXT"

    evidence = Path("tests/purchasing/test_purchasing_foundation.py").read_text(
        encoding="utf-8"
    )
    runtime = Path("app/purchasing/service.py").read_text(encoding="utf-8")
    model = Path("app/purchasing/models.py").read_text(encoding="utf-8")
    router = Path("app/purchasing/router.py").read_text(encoding="utf-8")
    assert "test_replenishment_approval_is_stale_safe_idempotent" in evidence
    assert "Replenishment decision idempotency identity conflicts" in runtime
    assert "STALE_REPLENISHMENT_RECOMMENDATION" in runtime
    assert '"company_id", "idempotency_key"' in model
    assert '"company_id",\n            "recommendation_digest"' in model
    assert "context: ApproveContext" in router


def test_coverage_is_tenant_explicit_and_bound_into_platform_contract() -> None:
    assert len(mutation_coverage_registry.fingerprint) == 64
    assert all(entry.tenant_scope for entry in mutation_coverage_registry.entries)
    assert {entry.tenant_scope for entry in mutation_coverage_registry.entries} <= {
        "COMPANY_WITH_BRANCH_CONTEXT",
        "PLATFORM_GLOBAL",
    }
    assert all(
        entry.tenant_scope == "COMPANY_WITH_BRANCH_CONTEXT"
        for entry in mutation_coverage_registry.entries
        if entry.classification is MutationClassification.REQUIRED
        and not entry.path.startswith(
            ("/api/v1/engineering/", "/api/v1/worker-transport/")
        )
    )
    assert (
        platform_contract_manifest.api_idempotency_coverage_fingerprint
        == mutation_coverage_registry.fingerprint
    )
    assert platform_contract_manifest.shared_api_contract_version == "3"


def test_canonical_digest_ignores_mapping_order_but_preserves_meaning() -> None:
    company_id = uuid4()
    as_of = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
    first = {
        "company_id": company_id,
        "amount": Decimal("10.00"),
        "lines": [{"quantity": 2, "code": "A"}],
        "as_of": as_of,
    }
    reordered = {
        "as_of": as_of,
        "lines": [{"code": "A", "quantity": 2}],
        "amount": Decimal("10.00"),
        "company_id": company_id,
    }
    assert canonical_request_digest(first) == canonical_request_digest(reordered)
    assert canonical_request_digest(first) != canonical_request_digest(
        {**reordered, "amount": Decimal("10.01")}
    )
    with pytest.raises(ValueError):
        canonical_request_digest({"amount": 10.01})


def test_identity_is_company_scoped_and_branch_is_authorization_context() -> None:
    company_a, company_b, branch = uuid4(), uuid4(), uuid4()
    a = IdempotencyIdentity(company_a, "payments.collect", "same-key", branch)
    b = IdempotencyIdentity(company_b, "payments.collect", "same-key", branch)
    assert a.tenant_key != b.tenant_key
    assert a.branch_id == branch
    assert (
        a.tenant_key
        == IdempotencyIdentity(
            company_a, "payments.collect", "same-key", uuid4()
        ).tenant_key
    )


def test_exact_replay_conflict_and_current_authorization_are_deterministic() -> None:
    digest = canonical_request_digest({"resource_id": str(uuid4()), "action": "close"})
    assert (
        decide_replay(
            stored_request_digest=None,
            incoming_request_digest=digest,
            currently_authorized=True,
        )
        is ReplayDecision.EXECUTE
    )
    assert (
        decide_replay(
            stored_request_digest=digest,
            incoming_request_digest=digest,
            currently_authorized=True,
        )
        is ReplayDecision.REPLAY
    )
    with pytest.raises(ContradictoryReplayError):
        decide_replay(
            stored_request_digest=digest,
            incoming_request_digest="0" * 64,
            currently_authorized=True,
        )
    with pytest.raises(ReplayAuthorizationError):
        decide_replay(
            stored_request_digest=digest,
            incoming_request_digest=digest,
            currently_authorized=False,
        )
