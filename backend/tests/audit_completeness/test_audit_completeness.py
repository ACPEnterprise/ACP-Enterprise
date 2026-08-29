from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from .contracts import (
    AuditClass,
    AuditEvidence,
    OperationContract,
    verify,
    verify_scope_binding,
)

ROOT = Path(__file__).resolve().parents[2]
COVERAGE = Path(__file__).with_name("coverage.v1.json")
EXPECTED_DOMAINS = {
    "customers_contacts_locations",
    "jobs",
    "scheduling_appointments",
    "dispatch",
    "workforce_employees",
    "workday_time",
    "inventory",
    "purchasing",
    "price_book",
    "estimates",
    "invoices_ar",
    "payments",
    "accounts_payable",
    "accounting",
    "business_events",
    "beacon",
    "business_economics_policy",
    "platform_authorization",
    "platform_audit_read",
    "communications",
    "analytics_read_models",
    "hcp_migration_runtime",
    "engineering_control_worker_factory",
}
EXPECTED_COVERAGE_FINGERPRINT = (
    "49e35f171ac657be66727fa24f5311806fb27203dff8e4709181f62e12b85b43"
)


def contract(**overrides: object) -> OperationContract:
    values: dict[str, object] = {
        "domain": "inventory",
        "operation": "inventory.adjust",
        "audit_class": AuditClass.IMMUTABLE_DOMAIN_RECORD,
        "company_scoped": True,
        "branch_scoped": True,
        "actor_required": True,
        "lineage_required": True,
        "event_required": True,
    }
    values.update(overrides)
    return OperationContract(**values)  # type: ignore[arg-type]


def evidence(**overrides: object) -> AuditEvidence:
    values: dict[str, object] = {
        "evidence_id": "audit-1",
        "operation": "inventory.adjust",
        "company_id": "company-a",
        "branch_id": "branch-a",
        "actor_id": "user-a",
        "actor_kind": "human",
        "subject_id": "item-a",
        "action": "adjust",
        "occurred_at": "2026-08-28T12:00:00Z",
        "lineage_id": "command-a",
        "immutable": True,
        "kind": "domain_audit",
        "event_id": "event-a",
    }
    values.update(overrides)
    return AuditEvidence(**values)  # type: ignore[arg-type]


def test_coverage_ledger_is_complete_classified_and_evidence_bound() -> None:
    payload = json.loads(COVERAGE.read_text())
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_COVERAGE_FINGERPRINT
    entries = payload["domains"]
    assert {entry["domain"] for entry in entries} == EXPECTED_DOMAINS
    assert len(entries) == len({entry["domain"] for entry in entries})
    assert all(
        entry["class"] in {item.value for item in AuditClass} for entry in entries
    )
    for entry in entries:
        path = ROOT / entry["evidence"].removeprefix("backend/")
        assert path.is_file(), f"stale audit evidence reference: {entry['evidence']}"
        if entry["class"] == AuditClass.EXCLUDED:
            assert entry.get("reason")


def test_valid_complete_evidence_is_deterministic_and_non_mutating() -> None:
    item = evidence()
    first = verify([contract()], [item])
    second = verify(reversed([contract()]), reversed([item]))
    assert not first.findings
    assert first == second
    with pytest.raises(FrozenInstanceError):
        item.action = "rewrite"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"actor_id": None}, "missing_actor"),
        ({"company_id": None}, "missing_company_scope"),
        ({"branch_id": None}, "missing_branch_scope"),
        ({"subject_id": None}, "missing_subject"),
        ({"action": None}, "missing_action"),
        ({"occurred_at": None}, "missing_timestamp"),
        ({"lineage_id": None}, "missing_lineage"),
        ({"immutable": False}, "mutable_audit_evidence"),
        ({"event_id": None}, "missing_business_event"),
    ],
)
def test_incomplete_evidence_fails_closed(change: dict[str, object], code: str) -> None:
    assert code in {
        item.code for item in verify([contract()], [evidence(**change)]).findings
    }


def test_missing_contradictory_and_event_only_evidence_fail_closed() -> None:
    assert verify([contract()], []).findings[0].code == "missing_audit_evidence"
    findings = verify([contract()], [evidence(), evidence(action="other")]).findings
    assert "contradictory_audit_identity" in {item.code for item in findings}
    findings = verify([contract()], [evidence(kind="business_event")]).findings
    assert "business_event_not_complete_audit" in {item.code for item in findings}


def test_company_and_branch_binding_reject_cross_scope_evidence() -> None:
    assert not verify_scope_binding(
        contract(), evidence(), company_id="company-a", branch_id="branch-a"
    )
    codes = {
        item.code
        for item in verify_scope_binding(
            contract(), evidence(), company_id="company-b", branch_id="branch-b"
        )
    }
    assert codes == {"cross_company_audit_binding", "cross_branch_audit_binding"}


def test_read_and_excluded_operations_require_no_mutation_audit() -> None:
    contracts = [
        contract(operation="analytics.read", audit_class=AuditClass.READ_ONLY),
        contract(operation="migration.run", audit_class=AuditClass.EXCLUDED),
    ]
    assert not verify(contracts, []).findings
