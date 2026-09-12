#!/usr/bin/env python3
"""Build a deterministic, non-activating All County owner-review packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "pricebook-allcounty-review/v1"
ALLOWED_CONFLICT_DECISIONS = {"KEEP_BOTH", "SELECT_ROW", "RETURN_TO_SOURCE_OWNER"}


def canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def classify_service(
    candidate: dict[str, Any], decision: dict[str, Any] | None
) -> dict[str, Any]:
    missing: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    source = candidate.get("source") or {}
    identity = candidate.get("candidate_identity")
    if not identity or not source.get("source_key") or source.get("row") is None:
        missing.append(
            _reason(
                "MISSING_SOURCE_IDENTITY",
                "Authoritative source identity is incomplete.",
            )
        )
    if not (candidate.get("service_code") or "").strip():
        missing.append(_reason("MISSING_CODE", "Service code is required."))
    if not (candidate.get("name") or "").strip():
        missing.append(_reason("MISSING_NAME", "Service name is required."))
    if not (candidate.get("customer_description") or "").strip():
        missing.append(
            _reason(
                "MISSING_CUSTOMER_DESCRIPTION",
                "Customer-facing description is required.",
            )
        )
    if not candidate.get("category", {}).get("source_name"):
        missing.append(
            _reason(
                "INVALID_CATEGORY", "A valid native category assignment is required."
            )
        )
    standard_price = candidate.get("price_candidates", {}).get("standard")
    if standard_price in (None, ""):
        missing.append(
            _reason(
                "MISSING_PRICING_EVIDENCE",
                "Proposed sell-price evidence is required; zero was not inferred.",
            )
        )
    labor = candidate.get("labor", {})
    if labor.get("hours") in (None, ""):
        missing.append(
            _reason(
                "INVALID_LABOR_STRUCTURE",
                "Labor quantity evidence is required; zero was not inferred.",
            )
        )
    material = candidate.get("material_cost_evidence", {})
    if material.get("completeness") != "COMPLETE":
        missing.append(
            _reason(
                "MISSING_MATERIAL_EVIDENCE",
                "Material structure requires management review; missing value was not converted to zero.",
            )
        )
    if candidate.get("tax_review") != "RESOLVED":
        missing.append(
            _reason(
                "INVALID_TAX_CLASSIFICATION",
                "A native tax classification requires owner/accountant review.",
            )
        )
    if not candidate.get("effective_at"):
        missing.append(
            _reason("MISSING_EFFECTIVE_DATE", "A proposed effective date is required.")
        )
    if not candidate.get("branch_identity"):
        missing.append(
            _reason(
                "MISSING_BRANCH", "An authorized native Branch assignment is required."
            )
        )

    decision = decision or {}
    review_decision = decision.get("decision", "PENDING")
    if review_decision not in {"PENDING", "APPROVED", "RETURNED"}:
        conflicts.append(
            _reason("INVALID_REVIEW_DECISION", "Review decision is not recognized.")
        )
    if conflicts:
        candidate_state = "CONFLICTING"
    elif candidate.get("review_state") == "READY_FOR_OWNER_REVIEW":
        candidate_state = "READY_FOR_REVIEW"
    else:
        candidate_state = "INCOMPLETE"
    activation_readiness = (
        "READY_FOR_ACTIVATION"
        if not missing and not conflicts and review_decision == "APPROVED"
        else "READY_FOR_REVIEW"
        if not conflicts and candidate_state == "READY_FOR_REVIEW"
        else "NOT_READY"
    )
    return {
        "candidate_identity": identity,
        "source": source,
        "code": candidate.get("service_code"),
        "name": candidate.get("name"),
        "category": candidate.get("category", {}).get("source_name"),
        "proposed_standard_price": standard_price,
        "labor_hours": labor.get("hours"),
        "material_cost_evidence": material,
        "tax_review": candidate.get("tax_review"),
        "effective_at": candidate.get("effective_at"),
        "branch_identity": candidate.get("branch_identity"),
        "candidate_state": candidate_state,
        "activation_readiness": activation_readiness,
        "management_review": decision,
        "missing_evidence_reasons": missing,
        "conflict_reasons": conflicts,
        "activation_status": "NOT_ACTIVATED",
    }


def build_packet(
    configuration: dict[str, Any], decisions: dict[str, Any] | None = None
) -> dict[str, Any]:
    decisions = decisions or {}
    service_decisions = decisions.get("service_decisions", {})
    rows = [
        classify_service(
            candidate, service_decisions.get(candidate.get("candidate_identity"))
        )
        for candidate in configuration["service_candidates"]
    ]
    identities = [row["candidate_identity"] for row in rows]
    duplicate_service_identities = sorted(
        {
            identity
            for identity in identities
            if identity and identities.count(identity) > 1
        }
    )
    if duplicate_service_identities:
        for row in rows:
            if row["candidate_identity"] in duplicate_service_identities:
                row["candidate_state"] = "CONFLICTING"
                row["activation_readiness"] = "NOT_READY"
                row["conflict_reasons"].append(
                    _reason(
                        "DUPLICATE_SOURCE_IDENTITY",
                        "Source identity appears more than once.",
                    )
                )

    duplicate_materials = configuration["vendor_material_import"][
        "duplicate_candidate_identities"
    ]
    conflict_decisions = decisions.get("conflict_decisions", {})
    conflicts: list[dict[str, Any]] = []
    for identity, source_rows in sorted(duplicate_materials.items()):
        decision = conflict_decisions.get(identity)
        if (
            decision is not None
            and decision.get("decision") not in ALLOWED_CONFLICT_DECISIONS
        ):
            raise ValueError(f"Unsupported conflict decision for {identity}")
        conflicts.append(
            {
                "candidate_identity": identity,
                "source_rows": source_rows,
                "source_evidence_preserved": True,
                "decision": decision,
                "resolution_state": "RESOLVED_FOR_REVIEW"
                if decision
                else "CONFLICTING",
                "activation_status": "NOT_ACTIVATED",
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        key = row["activation_readiness"]
        counts[key] = counts.get(key, 0) + 1
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_configuration_version": configuration[
            "candidate_configuration_version"
        ],
        "source_configuration_digest": canonical_digest(configuration),
        "service_candidate_count": len(rows),
        "classification_counts": counts,
        "services": rows,
        "source_part_conflicts": conflicts,
        "controls": {
            "bulk_activation_supported": False,
            "automatic_activation_supported": False,
            "missing_values_default_to_zero": False,
            "human_activation_required": True,
        },
    }
    packet["packet_digest"] = canonical_digest(packet)
    return packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("configuration", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    configuration = json.loads(args.configuration.read_text())
    decisions = json.loads(args.decisions.read_text()) if args.decisions else None
    packet = build_packet(configuration, decisions)
    rendered = json.dumps(packet, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
