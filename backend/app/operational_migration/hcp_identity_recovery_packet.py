"""Fail-closed recovery packaging for protected HCP successor evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

CONTRACT = "hcp-identity-recovery-package/v1"
INVENTORY_CONTRACT = "hcp-update-runtime-successor-inventory/v1"
EXPECTED_BINDINGS = 417

EXACT = "EXACT_EXISTING_NATIVE_SUCCESSOR"
MISSING = "PROVEN_MISSING_NATIVE_RECORD"
INCORRECT = "INCORRECT_UPDATE_DISPOSITION"
CONFLICT = "DUPLICATE_OR_CONFLICTING_IDENTITY"
HELD = "UNRESOLVED_AND_HELD"


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _key(record: dict[str, Any]) -> tuple[str, str]:
    return str(record.get("domain") or ""), str(record.get("source_id") or "")


def _base_classification(record: dict[str, Any]) -> tuple[str, str]:
    disposition = str(record.get("disposition") or "")
    reason = str(record.get("reason") or "")
    if disposition in {"BINDING_ALREADY_PRESENT", "PROVABLE_NATIVE_SUCCESSOR_BINDING"}:
        return EXACT, "exact provider identity, native target, and parent graph"
    if (
        disposition == "NATIVE_SUCCESSOR_MISSING"
        and record.get("legacy_identity_id")
        and record.get("native_id")
    ):
        return MISSING, "exact legacy identity exists but its native target is absent"
    if disposition == "UNSUPPORTED":
        return INCORRECT, "UPDATE domain is unsupported by the native binding contract"
    if disposition in {
        "AMBIGUOUS_NATIVE_SUCCESSOR",
        "CONFLICTING_SOURCE4_BINDING",
        "CONFLICTING_BINDING",
        "PARENT_GRAPH_MISMATCH",
        "CROSS_SCOPE",
    }:
        return CONFLICT, reason or "native identity evidence conflicts"
    return HELD, reason or "authoritative native successor evidence is incomplete"


def build_recovery_package(
    inventory: dict[str, Any],
    dependencies: dict[tuple[str, str], tuple[tuple[str, str], ...]],
    *,
    expected_bindings: int = EXPECTED_BINDINGS,
) -> dict[str, Any]:
    if inventory.get("contract") != INVENTORY_CONTRACT:
        raise ValueError("runtime inventory contract mismatch")
    records = inventory.get("records")
    if not isinstance(records, list) or len(records) != expected_bindings:
        raise ValueError(
            f"runtime inventory must contain exactly {expected_bindings} rows"
        )
    if inventory.get("mutation_authority") != "none":
        raise ValueError("runtime inventory must be read-only")

    seen: set[tuple[str, str]] = set()
    classified: dict[tuple[str, str], dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, dict):
            raise TypeError("runtime inventory row must be an object")
        key = _key(item)
        if not all(key) or key in seen:
            raise ValueError("runtime inventory keys must be complete and unique")
        seen.add(key)
        classification, explanation = _base_classification(item)
        classified[key] = {
            "classification": classification,
            "cohort": str(item.get("cohort") or ""),
            "domain": key[0],
            "evidence_digest": str(item.get("evidence_digest") or ""),
            "explanation": explanation,
            "legacy_identity_id": item.get("legacy_identity_id"),
            "native_id": item.get("native_id"),
            "source_id": key[1],
        }
        if len(classified[key]["evidence_digest"]) != 64:
            raise ValueError("runtime evidence digest is required for every binding")

    if set(dependencies) - seen:
        raise ValueError("dependency graph contains unknown records")
    for parents in dependencies.values():
        if any(parent not in seen for parent in parents):
            raise ValueError("dependency graph contains an unknown parent")

    changed = True
    while changed:
        changed = False
        for key, parents in dependencies.items():
            row = classified[key]
            if row["classification"] != EXACT:
                continue
            blockers = [
                parent
                for parent in parents
                if classified[parent]["classification"] != EXACT
            ]
            if blockers:
                row["classification"] = HELD
                row["explanation"] = (
                    "dependent native identity is not independently recoverable"
                )
                row["blocked_parent_count"] = len(blockers)
                changed = True

    ordered = [classified[key] for key in sorted(classified)]
    counts = Counter(row["classification"] for row in ordered)
    independent = [
        {"domain": row["domain"], "source_id": row["source_id"]}
        for row in ordered
        if row["classification"] == EXACT
    ]
    payload: dict[str, Any] = {
        "contract": CONTRACT,
        "source_inventory_digest": canonical_sha256(inventory),
        "protected_authority": inventory.get("protected_authority"),
        "schema_head": inventory.get("schema_head"),
        "mutation_authority": "none",
        "binding_count": len(ordered),
        "classification_counts": dict(sorted(counts.items())),
        "dependency_complete": True,
        "independent_recovery_count": len(independent),
        "independent_recovery_keys": independent,
        "records": ordered,
    }
    payload["digest"] = canonical_sha256(payload)
    return payload
