"""Native parser and complete preflight for the sealed HCP v4 overlay."""

from __future__ import annotations

import hashlib
import json
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayKey,
    OverlayRecord,
)
from app.operational_migration.hcp_current_overlay_native import (
    HcpCurrentOverlayNativeServices,
)

V4_CONTRACT = "hcp-current-overlay-merge-packet/v4"
AUTHORITY_CONTRACT = "hcp-current-overlay-native-execution/v3"
EXPECTED_COUNTS = {
    "CREATE_NEW": 174,
    "REUSE_EXISTING": 4,
    "UPDATE_EXISTING": 5,
    "HOLD": 339,
}
EXPECTED_CURRENT_COUNTS = {
    ("customer", "CREATE_NEW"): 7,
    ("customer", "REUSE_EXISTING"): 1,
    ("customer", "UPDATE_EXISTING"): 3,
    ("service_location", "CREATE_NEW"): 8,
    ("service_location", "REUSE_EXISTING"): 3,
    ("job", "CREATE_NEW"): 15,
    ("appointment", "CREATE_NEW"): 18,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class V4ExecutableOverlay:
    semantic_digest: str
    file_digest: str
    complete_current_graph_digest: str
    base_source4_digest: str
    company_id: UUID
    branch_id: UUID
    manifest: CurrentOverlayManifest
    qualified_targets: dict[OverlayKey, UUID]
    successor_assertions: dict[OverlayKey, str]
    execution_evidence: tuple[dict[str, object], ...]
    current_keys: frozenset[OverlayKey]

    @classmethod
    def load(cls, path: Path) -> V4ExecutableOverlay:
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("v4 overlay permissions must be 0600")
        value = json.loads(path.read_bytes())
        if value.get("contract") != V4_CONTRACT or value.get("record_count") != 522:
            raise ValueError("v4 overlay contract/cardinality mismatch")
        unsigned = {key: item for key, item in value.items() if key != "digest"}
        semantic_digest = hashlib.sha256(
            (
                json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        ).hexdigest()
        if value.get("digest") != semantic_digest:
            raise ValueError("v4 overlay semantic digest mismatch")
        counts = Counter(row["successor_assertion"] for row in value["records"])
        if {key: counts[key] for key in EXPECTED_COUNTS} != EXPECTED_COUNTS:
            raise ValueError("v4 overlay disposition accounting mismatch")
        keys = {(row["domain"], row["source_id"]) for row in value["records"]}
        if len(keys) != 522:
            raise ValueError("v4 overlay source identity duplication")
        targets: dict[OverlayKey, UUID] = {}
        successors: dict[OverlayKey, str] = {}
        execution_evidence: list[dict[str, object]] = []
        records: list[OverlayRecord] = []
        for item in value["records"]:
            successor = item["successor_assertion"]
            key = OverlayKey(item["domain"], item["source_id"])
            successors[key] = successor
            execution_evidence.append(
                {
                    "domain": item["domain"],
                    "source_id": item["source_id"],
                    "original_assertion": item["original_assertion"],
                    "successor_assertion": successor,
                    "reason": item["reason"],
                    "runtime_result": item["runtime_result"],
                    "baseline_evidence": item["baseline_evidence"],
                    "parent_keys": item["parent_keys"],
                    "source_digest": item["source_digest"],
                }
            )
            target = (item.get("baseline_evidence") or {}).get("target_native_id")
            if successor in {"REUSE_EXISTING", "UPDATE_EXISTING"}:
                if not target:
                    raise ValueError("v4 qualified target is missing")
                targets[key] = UUID(target)
            elif target:
                raise ValueError("v4 target is present for a non-targeted assertion")
            assertion = {
                "CREATE_NEW": OverlayAssertion.CREATE,
                "REUSE_EXISTING": OverlayAssertion.CREATE,
                "UPDATE_EXISTING": OverlayAssertion.UPDATE,
                "HOLD": OverlayAssertion.HOLD,
            }[successor]
            records.append(
                OverlayRecord(
                    domain=item["domain"],
                    source_id=item["source_id"],
                    assertion=assertion,
                    source_digest=item["source_digest"],
                    acquired_at=item["acquired_at"],
                    payload={}
                    if assertion is OverlayAssertion.HOLD
                    else item["payload"],
                    prior_source_digest=(
                        (item.get("baseline_evidence") or {}).get(
                            "exact_legacy_successor_evidence_digest"
                        )
                        if successor == "UPDATE_EXISTING"
                        else item.get("prior_source_digest")
                    ),
                    parent_keys=tuple(
                        OverlayKey(**parent) for parent in item["parent_keys"]
                    ),
                    native_fingerprint=item["source_digest"],
                    reason=item["reason"],
                )
            )
        manifest = CurrentOverlayManifest.build(
            base_source4_digest=value["base_source4_digest"],
            delta_digest=value["digest"],
            company_id=value["company_id"],
            branch_id=value["branch_id"],
            acquired_at=value.get(
                "baseline_acquired_at", "2026-09-14T18:09:06.212615+00:00"
            ),
            records=tuple(records),
        )
        current = frozenset(
            OverlayKey(row["domain"], row["source_id"])
            for row in value["current_graph"]
        )
        if len(current) != 55 or any(
            row["successor_assertion"] == "HOLD" for row in value["current_graph"]
        ):
            raise ValueError("v4 current graph is incomplete")
        current_counts = Counter(
            (row["domain"], row["successor_assertion"])
            for row in value["current_graph"]
        )
        if dict(current_counts) != EXPECTED_CURRENT_COUNTS:
            raise ValueError("v4 current graph disposition accounting mismatch")
        by_key = {(row["domain"], row["source_id"]): row for row in value["records"]}
        if any(
            by_key.get((row["domain"], row["source_id"])) != row
            for row in value["current_graph"]
        ):
            raise ValueError("v4 current graph record differs from authority record")
        return cls(
            value["digest"],
            sha256(path),
            value["complete_current_graph_digest"],
            value["base_source4_digest"],
            UUID(value["company_id"]),
            UUID(value["branch_id"]),
            manifest,
            targets,
            successors,
            tuple(execution_evidence),
            current,
        )


async def preflight_v4(
    session: AsyncSession,
    *,
    overlay: V4ExecutableOverlay,
    services: HcpCurrentOverlayNativeServices,
) -> dict[str, object]:
    """Non-short-circuit, read-only validation over every v4 record."""
    failures: list[dict[str, str]] = []
    records = {record.key: record for record in overlay.manifest.records}
    held = {
        record.key
        for record in records.values()
        if record.assertion is OverlayAssertion.HOLD
    }
    for record in overlay.manifest.records:
        for parent in record.parent_keys:
            unresolved = record.key in overlay.current_keys and (
                parent not in records or parent in held
            )
            if (
                not unresolved
                and record.assertion is not OverlayAssertion.HOLD
                and parent not in records
            ):
                unresolved = not await services.source_exists(session, parent)
            if unresolved:
                failures.append(
                    {
                        "key": f"{record.domain}:{record.source_id}",
                        "reason": "parent_graph_unresolved",
                    }
                )
        target_id = overlay.qualified_targets.get(record.key)
        if target_id is not None:
            native = await services.qualified_native(session, record.domain, target_id)
            if native is None:
                failures.append(
                    {
                        "key": f"{record.domain}:{record.source_id}",
                        "reason": "qualified_target_missing_or_cross_scope",
                    }
                )
            bound_id = await services.source_native_id(session, record.key)
            if bound_id is not None and bound_id != target_id:
                failures.append(
                    {
                        "key": f"{record.domain}:{record.source_id}",
                        "reason": "conflicting_source4_target",
                    }
                )
        elif record.assertion in {OverlayAssertion.CREATE, OverlayAssertion.UPDATE}:
            if await services.source_exists(session, record.key):
                failures.append(
                    {
                        "key": f"{record.domain}:{record.source_id}",
                        "reason": "unexpected_source4_identity",
                    }
                )
            if record.native_fingerprint:
                owners = await services.fingerprint_owners(
                    session, record.domain, record.native_fingerprint
                )
                if owners:
                    failures.append(
                        {
                            "key": f"{record.domain}:{record.source_id}",
                            "reason": "duplicate_native_fingerprint",
                        }
                    )
    report: dict[str, object] = {
        "contract": "hcp-current-overlay-v4-preflight/v1",
        "record_count": 522,
        "current_record_count": 55,
        "failure_count": len(failures),
        "failures": failures,
        "ready": not failures,
    }
    if failures:
        raise ValueError(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return report
