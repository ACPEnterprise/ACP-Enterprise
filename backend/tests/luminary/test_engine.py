from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from uuid import UUID

import pytest

from app.luminary.contracts import (
    BeaconConditionReference,
    EvidenceReference,
    FindingClass,
    FindingType,
    LuminaryEvidencePackage,
)
from app.luminary.engine import LuminaryEngine, LuminaryIntegrityError, canonical_digest

COMPANY_ID = UUID("10000000-0000-0000-0000-000000000001")


def package(
    *, quality: str = "complete", allocation: str = "ready"
) -> LuminaryEvidencePackage:
    economics: dict[str, object] = {
        "quality_state": quality,
        "currency": "USD",
        "totals": {
            "revenue": 300_000,
            "labor": 90_000,
            "materials": 80_000,
            "gross_profit": 130_000,
            "net_profit": None,
        },
        "jobs": [
            {
                "result_id": "job-a",
                "job_number": "SYN-101",
                "contribution_minor": 150_000,
                "currency": "USD",
                "confidence_percent": 100,
                "quality_state": quality,
            },
            {
                "result_id": "job-b",
                "job_number": "SYN-102",
                "contribution_minor": -20_000,
                "currency": "USD",
                "confidence_percent": 90,
                "quality_state": quality,
            },
        ],
        "branches": [
            {
                "label": "Synthetic North",
                "contribution_minor": 150_000,
                "quality_state": "complete",
            },
            {
                "label": "Synthetic South",
                "contribution_minor": -20_000,
                "quality_state": "complete",
            },
        ],
        "comparison": {
            "state": "available",
            "revenue_change_minor": 20_000,
            "contribution_change_minor": -10_000,
            "labor_change_minor": 8_000,
            "materials_change_minor": 2_000,
            "explanation": "Equal complete synthetic periods.",
        },
        "readiness": {"allocation_policy": allocation},
    }
    references = (
        EvidenceReference(
            "business_economics", "profitability_result", "job-a", "a" * 64
        ),
    )
    beacon = (
        BeaconConditionReference(
            "signal-a",
            "margin-attention",
            "economics.margin",
            "warning",
            "open",
            "b" * 64,
            "Measured margin needs attention",
        ),
    )
    payload = {
        "company_id": str(COMPANY_ID),
        "branch_id": None,
        "period": ["2026-08-01", "2026-08-31"],
        "economics": economics,
        "economics_results": [
            {
                "source_domain": "business_economics",
                "record_type": "profitability_result",
                "record_id": "job-a",
                "digest": "a" * 64,
            }
        ],
        "beacon_conditions": [
            {
                "signal_id": "signal-a",
                "condition_key": "margin-attention",
                "definition_id": "economics.margin",
                "severity": "warning",
                "lifecycle": "open",
                "evidence_digest": "b" * 64,
                "title": "Measured margin needs attention",
            }
        ],
    }
    return LuminaryEvidencePackage(
        COMPANY_ID,
        None,
        date(2026, 8, 1),
        date(2026, 8, 31),
        economics,
        references,
        beacon,
        canonical_digest(payload),
        datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_complete_evidence_produces_owner_findings_without_claiming_causality() -> None:
    findings = LuminaryEngine().analyze(package())
    types = {item.finding_type for item in findings}
    assert {
        FindingType.PROFITABLE_JOB,
        FindingType.UNPROFITABLE_JOB,
        FindingType.PERIOD_CHANGE,
        FindingType.BRANCH_COMPARISON,
        FindingType.BEACON_ATTENTION,
    } <= types
    associations = [
        item
        for item in findings
        if item.finding_class is FindingClass.SUPPORTED_ASSOCIATION
    ]
    assert associations
    assert all("not a claim" in item.explanation for item in associations)
    assert all("cause" not in item.summary.lower() for item in findings)


@pytest.mark.parametrize(
    "quality, expected",
    [
        ("unavailable", FindingClass.INSUFFICIENT_EVIDENCE),
        ("conflicting", FindingClass.CONFLICTING_EVIDENCE),
    ],
)
def test_blocked_evidence_withholds_economic_conclusions(
    quality: str, expected: FindingClass
) -> None:
    findings = LuminaryEngine().analyze(package(quality=quality))
    assert any(item.finding_class is expected for item in findings)
    assert not any(item.finding_type is FindingType.PROFITABLE_JOB for item in findings)


def test_missing_allocation_policy_is_explicit_and_does_not_invent_policy() -> None:
    findings = LuminaryEngine().analyze(package(allocation="not_configured"))
    finding = next(
        item for item in findings if item.finding_class is FindingClass.POLICY_REQUIRED
    )
    assert "does not choose" in finding.limitations[0]


def test_replay_is_deterministic_and_generated_time_is_not_economic_identity() -> None:
    first = package()
    second = replace(first, generated_at=datetime(2026, 9, 2, tzinfo=timezone.utc))
    assert [item.finding_digest for item in LuminaryEngine().analyze(first)] == [
        item.finding_digest for item in LuminaryEngine().analyze(second)
    ]


def test_tampered_package_fails_closed() -> None:
    original = package()
    tampered = replace(
        original, economics={**original.economics, "totals": {"revenue": 999_999}}
    )
    with pytest.raises(LuminaryIntegrityError):
        LuminaryEngine().analyze(tampered)


def test_beacon_composition_is_reference_only() -> None:
    finding = next(
        item
        for item in LuminaryEngine().analyze(package())
        if item.finding_type is FindingType.BEACON_ATTENTION
    )
    assert any(item.source_domain == "beacon" for item in finding.evidence)
    assert "retains lifecycle authority" in finding.explanation
