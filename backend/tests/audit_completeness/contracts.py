from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum


class AuditClass(StrEnum):
    IMMUTABLE_DOMAIN_RECORD = "A"
    EVENT_AND_DOMAIN_STATE = "B"
    APPEND_ONLY_HISTORY = "C"
    SECURITY_AUDIT = "D"
    READ_ONLY = "E"
    EXCLUDED = "F"


@dataclass(frozen=True, order=True)
class OperationContract:
    domain: str
    operation: str
    audit_class: AuditClass
    company_scoped: bool = True
    branch_scoped: bool = False
    actor_required: bool = True
    lineage_required: bool = True
    event_required: bool = False


@dataclass(frozen=True, order=True)
class AuditEvidence:
    evidence_id: str
    operation: str
    company_id: str | None
    branch_id: str | None
    actor_id: str | None
    actor_kind: str | None
    subject_id: str | None
    action: str | None
    occurred_at: str | None
    lineage_id: str | None
    immutable: bool
    kind: str = "domain_audit"
    event_id: str | None = None


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    operation: str
    evidence_id: str = ""


@dataclass(frozen=True)
class VerificationResult:
    findings: tuple[Finding, ...]
    fingerprint: str


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def verify(
    contracts: Iterable[OperationContract], evidence: Iterable[AuditEvidence]
) -> VerificationResult:
    contracts_tuple = tuple(sorted(contracts))
    evidence_tuple = tuple(sorted(evidence))
    findings: list[Finding] = []
    seen: dict[str, AuditEvidence] = {}
    for item in evidence_tuple:
        prior = seen.get(item.evidence_id)
        if prior is not None:
            code = (
                "contradictory_audit_identity"
                if prior != item
                else "duplicate_audit_identity"
            )
            findings.append(Finding(code, item.operation, item.evidence_id))
        else:
            seen[item.evidence_id] = item

    for contract in contracts_tuple:
        if contract.audit_class in {AuditClass.READ_ONLY, AuditClass.EXCLUDED}:
            continue
        matches = [
            item for item in evidence_tuple if item.operation == contract.operation
        ]
        if not matches:
            findings.append(Finding("missing_audit_evidence", contract.operation))
            continue
        for item in matches:
            missing = {
                "missing_actor": contract.actor_required
                and not (item.actor_id and item.actor_kind),
                "missing_company_scope": contract.company_scoped
                and not item.company_id,
                "missing_branch_scope": contract.branch_scoped and not item.branch_id,
                "missing_subject": not item.subject_id,
                "missing_action": not item.action,
                "missing_timestamp": not item.occurred_at,
                "missing_lineage": contract.lineage_required and not item.lineage_id,
                "mutable_audit_evidence": not item.immutable,
                "missing_business_event": contract.event_required and not item.event_id,
                "business_event_not_complete_audit": (
                    contract.audit_class == AuditClass.IMMUTABLE_DOMAIN_RECORD
                    and item.kind == "business_event"
                ),
            }
            findings.extend(
                Finding(code, contract.operation, item.evidence_id)
                for code, failed in missing.items()
                if failed
            )

    canonical = {
        "contracts": [asdict(item) for item in contracts_tuple],
        "evidence": [asdict(item) for item in evidence_tuple],
        "findings": [asdict(item) for item in sorted(findings)],
    }
    return VerificationResult(
        findings=tuple(sorted(findings)),
        fingerprint=hashlib.sha256(_canonical(canonical)).hexdigest(),
    )


def verify_scope_binding(
    contract: OperationContract,
    evidence: AuditEvidence,
    *,
    company_id: str,
    branch_id: str | None,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if contract.company_scoped and evidence.company_id != company_id:
        findings.append(
            Finding(
                "cross_company_audit_binding", contract.operation, evidence.evidence_id
            )
        )
    if contract.branch_scoped and evidence.branch_id != branch_id:
        findings.append(
            Finding(
                "cross_branch_audit_binding", contract.operation, evidence.evidence_id
            )
        )
    return tuple(findings)
