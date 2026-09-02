"""Derive activation readiness without changing the candidate configuration."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def audit_service(item: dict[str, Any]) -> dict[str, Any]:
    category = item["category"]["source_name"]
    price = item["price_candidates"].get("standard")
    commercial = all(
        (
            item.get("service_code"),
            item.get("name"),
            item.get("customer_description"),
            price,
        )
    )
    water_heater = category in {
        "Water Heater Install",
        "Tankless",
        "Water Heater Repair",
    }
    has_aggregate_material = item["material_cost_evidence"]["amount"] != "0.00"
    return {
        "candidate_identity": item["candidate_identity"],
        "service_code": item["service_code"],
        "category": category,
        "gates": {
            "COMMERCIAL_READY": commercial,
            "PRICE_READY": bool(price),
            "DESCRIPTION_READY": bool(item.get("customer_description")),
            "OPTION_READY": True,
            "TAX_READY": False,
            "MEMBERSHIP_READY": False,
            "MATERIAL_COST_READY": False,
            "LABOR_COST_READY": False,
            "ECONOMICS_READY": False,
            "SOURCE_CONFLICT": water_heater,
            "OWNER_REVIEW_REQUIRED": True,
            "ACCOUNTANT_REVIEW_REQUIRED": True,
        },
        "requirements": {
            "customer_browse": [
                "service_code",
                "name",
                "customer_description",
                "category",
            ],
            "estimate_selection": [
                "active_price_version",
                "currency",
                "effective_window",
            ],
            "estimate_snapshot": [
                "price_version",
                "tax_classification",
                "idempotency_key",
            ],
            "member_pricing": ["authoritative_service_agreement_entitlement"],
        },
        "cost_effects": {
            "customer_pricing_blocked": False,
            "estimate_use_blocked": False,
            "snapshot_blocked": False,
            "inventory_readiness": "MATERIAL_MAPPING_REQUIRED"
            if has_aggregate_material
            else "NO_SOURCE_COMPOSITION",
            "planned_cost_readiness": "INCOMPLETE",
            "economics_readiness": "INCOMPLETE",
            "price_review_intelligence": "LIMITED",
        },
        "price_source": {
            "standard_candidate": price,
            "source_artifact": item["source"]["source_key"],
            "source_sheet": item["source"]["sheet"],
            "source_row": item["source"]["row"],
            "derivation": item["price_derivation"],
            "formula_inputs": {
                "configured_hours": item["labor"]["hours"],
                "aggregate_material_cost": item["material_cost_evidence"]["amount"],
            },
        },
        "tax_decision_group": f"CATEGORY_{slug(category)}",
        "activation_cohort": (
            "SOURCE_CONFLICT"
            if water_heater
            else "READY_AFTER_OWNER_PRICE_AND_TAX_APPROVAL"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.configuration.read_text())
    audits = [audit_service(item) for item in source["service_candidates"]]
    tax_groups: dict[str, dict[str, Any]] = {}
    for audit in audits:
        group = tax_groups.setdefault(
            audit["tax_decision_group"],
            {
                "source_category": audit["category"],
                "service_codes": [],
                "decision": "ACCOUNTANT_REVIEW_REQUIRED",
                "tax_treatment": None,
            },
        )
        group["service_codes"].append(audit["service_code"])
    cohorts = Counter(item["activation_cohort"] for item in audits)
    vendor_candidates = source["vendor_material_import"]["candidates"]
    vendor_states = Counter(item["review_state"] for item in vendor_candidates)
    packet = {
        "schema_version": "1.0",
        "milestone": "PRICEBOOK.ALLCOUNTY.ACTIVATION.READINESS.1",
        "source_configuration_version": source["candidate_configuration_version"],
        "activation_status": "NOT_ACTIVATED",
        "service_audits": audits,
        "tax_decision_groups": tax_groups,
        "activation_cohorts": dict(sorted(cohorts.items())),
        "counts": {
            "services": len(audits),
            "commercially_ready_before_cost_completion": sum(
                item["gates"]["COMMERCIAL_READY"] for item in audits
            ),
            "blocked_solely_by_tax_after_owner_price_approval": sum(
                not item["gates"]["SOURCE_CONFLICT"] for item in audits
            ),
            "blocked_by_source_conflict": sum(
                item["gates"]["SOURCE_CONFLICT"] for item in audits
            ),
            "ready_after_minimum_approvals": len(audits),
            "ready_for_activation_now": 0,
            "owner_review_required": sum(
                item["gates"]["OWNER_REVIEW_REQUIRED"] for item in audits
            ),
            "accountant_review_required": sum(
                item["gates"]["ACCOUNTANT_REVIEW_REQUIRED"] for item in audits
            ),
        },
        "membership": {
            "non_member_activation_independent": True,
            "member_pricing_state": "OWNER_LEGAL_DECISION_REQUIRED",
            "owning_domain": "SERVICE_AGREEMENTS",
        },
        "commercial_activation_requirements": {
            "required": [
                "owner-approved customer description and category",
                "owner-approved source-linked candidate price",
                "effective immutable Price Book version",
                "accountant-approved reusable tax classification reference",
                "authorized membership entitlement when member pricing is used",
            ],
            "not_required": [
                "complete material mapping",
                "complete labor cost",
                "planned margin or profit",
                "measured break-even model",
                "vendor identity for every source part",
            ],
        },
        "material_mapping_impact": {
            "services_requiring_mapping": source["review_summary"][
                "MATERIAL_MAPPING_REQUIRED"
            ],
            "blocks_customer_price": False,
            "blocks_estimate_selection": False,
            "blocks_immutable_snapshot": False,
            "blocks_inventory_readiness": True,
            "blocks_complete_planned_cost_and_economics": True,
        },
        "vendor_reconciliation": {
            "candidate_count": len(vendor_candidates),
            "source_required": vendor_states["SOURCE_REQUIRED"],
            "duplicate_candidates": vendor_states["DUPLICATE_CANDIDATE"],
            "duplicate_part_828627_disposition": "POSSIBLE_MATCH_RETAIN_BOTH_SOURCE_ROWS",
            "vendor_identity_invented": False,
        },
        "price_source_review": {
            "formula_derived": sum(
                item["price_source"]["derivation"] == "WORKBOOK_FORMULA"
                for item in audits
            ),
            "owner_overrides": sum(
                item["price_source"]["derivation"] == "OWNER_OVERRIDE"
                for item in audits
            ),
            "per_service_provenance": True,
        },
        "water_heater_reconciliation": source["water_heater_reconciliation"],
        "future_recommendation_contract": {
            "inputs": [
                "source_price_book_version",
                "economics_evidence_version",
                "model_version",
                "recommendation_identity",
                "affected_service_set",
                "transformation",
                "before_after_prices",
                "owner_exclusions",
                "approval_identity",
                "effective_date",
            ],
            "activation_authority": "OWNER_ONLY_SEPARATE_COMMAND",
            "automatic_repricing": False,
            "profit_claim_when_cost_incomplete": False,
        },
        "activation_command_safety": {
            "bulk_review_is_activation": False,
            "optimistic_concurrency": True,
            "company_scope": True,
            "idempotent_exact_replay": True,
            "contradictory_replay_rejected": True,
            "business_event_and_audit": True,
            "historical_estimate_snapshot_immutable": True,
        },
        "bulk_review_groups": {
            "category": sorted({item["category"] for item in audits}),
            "formula_derived": [
                item["service_code"]
                for item in audits
                if item["price_source"]["derivation"] == "WORKBOOK_FORMULA"
            ],
            "owner_override": [
                item["service_code"]
                for item in audits
                if item["price_source"]["derivation"] == "OWNER_OVERRIDE"
            ],
            "water_heater": [
                item["service_code"]
                for item in audits
                if item["gates"]["SOURCE_CONFLICT"]
            ],
        },
        "hard_boundaries": {
            "real_price_activation": False,
            "automatic_repricing": False,
            "tax_policy_assignment": False,
            "accounting_posting": False,
            "employee_recommendation": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
