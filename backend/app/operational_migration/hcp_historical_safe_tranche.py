"""Build a fail-closed historical tranche from an accepted overlay plan."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "hcp-historical-safe-tranche/v1"
ACCEPTANCE_CONTRACT: Final = "hcp-current-overlay-post-admission-acceptance/v1"
OVERLAY_CONTRACT: Final = "hcp-current-overlay/v1"
NATIVE_BINDING_CONTRACT: Final = "hcp-native-binding-snapshot/v1"
ALLOWED_CLASSIFICATIONS: Final = frozenset({"SAFE_HISTORICAL", "SAFE_UPDATE"})
EXPECTED_CLASSIFICATIONS: Final = {"SAFE_HISTORICAL": 149, "SAFE_UPDATE": 37}
DOMAIN_ORDER: Final = {"customer": 0, "service_location": 1, "job": 2, "appointment": 3}


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _key(value: dict[str, Any]) -> str:
    return f"{value['domain']}:{value['source_id']}"


@dataclass(frozen=True, slots=True)
class HistoricalTrancheRecord:
    domain: str
    source_id: str
    classification: str
    assertion: str
    company_id: str
    branch_id: str
    native_id: str | None
    source_digest: str
    prior_source_digest: str | None
    acquired_at: str
    lifecycle: str | None
    parent_keys: tuple[str, ...]
    parent_requirements: tuple[str, ...]
    readiness: str
    hold_reason: str | None
    provenance_digest: str
    payload: dict[str, Any]

    @property
    def key(self) -> str:
        return f"{self.domain}:{self.source_id}"


@dataclass(frozen=True, slots=True)
class HistoricalTranche:
    contract: str
    protected_authority: str
    overlay_manifest_digest: str
    overlay_file_sha256: str
    acceptance_plan_digest: str
    company_id: str
    branch_id: str
    counts: dict[str, dict[str, int]]
    dependency_counts: dict[str, int]
    readiness_counts: dict[str, int]
    records: tuple[HistoricalTrancheRecord, ...]
    execution_allowed: bool
    execution_blockers: tuple[str, ...]
    digest: str

    def verify(self) -> None:
        payload = asdict(self)
        digest = payload.pop("digest")
        if self.contract != CONTRACT or digest != _canonical_digest(payload):
            raise ValueError("historical tranche digest mismatch")
        if len({record.key for record in self.records}) != len(self.records):
            raise ValueError("historical tranche contains duplicate source identity")


def _verify_acceptance_plan(plan: dict[str, Any]) -> None:
    if plan.get("contract") != ACCEPTANCE_CONTRACT:
        raise ValueError("unsupported acceptance plan contract")
    payload = dict(plan)
    digest = payload.pop("digest", None)
    if digest != _canonical_digest(payload):
        raise ValueError("acceptance plan digest mismatch")
    observed = Counter(
        record["classification"]
        for record in plan["records"]
        if record["classification"] in ALLOWED_CLASSIFICATIONS
    )
    if dict(observed) != EXPECTED_CLASSIFICATIONS:
        raise ValueError(f"historical tranche classification drift: {dict(observed)}")


def _load_bindings(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    value = json.loads(path.read_bytes())
    payload = dict(value)
    digest = payload.pop("digest", None)
    if digest != _canonical_digest(payload):
        raise ValueError("native binding evidence digest mismatch")
    if (
        value.get("contract") != NATIVE_BINDING_CONTRACT
        or value.get("mutation_authority") != "none"
    ):
        raise ValueError("native binding evidence must be read-only")
    bindings = {_key(item): item for item in value.get("bindings", [])}
    if len(bindings) != len(value.get("bindings", [])):
        raise ValueError("duplicate native binding evidence")
    native_ids = [
        (item["domain"], item.get("native_id")) for item in value.get("bindings", [])
    ]
    if any(not native_id for _, native_id in native_ids) or len(native_ids) != len(
        set(native_ids)
    ):
        raise ValueError("missing or conflicting native identity evidence")
    return bindings


def _lifecycle(record: dict[str, Any]) -> str | None:
    payload = record.get("payload") or {}
    if record["domain"] == "job":
        value = payload.get("work_status")
        return str(value) if value is not None else None
    if record["domain"] == "appointment":
        start = payload.get("start_time")
        end = payload.get("end_time")
        return "scheduled" if start and end else "draft"
    return str(payload.get("status")) if payload.get("status") is not None else None


def _unsupported_lifecycle(record: dict[str, Any]) -> bool:
    if record["domain"] != "job":
        return False
    payload = record.get("payload") or {}
    status = str(payload.get("work_status") or "").lower()
    if "canceled" in status or "cancelled" in status:
        return True
    if record["assertion"] == "update":
        return status not in {"needs scheduling", "scheduled"}
    timestamps = payload.get("work_timestamps") or {}
    return status in {"in progress", "complete rated", "complete unrated"} and not (
        timestamps.get("started_at")
    )


def build_historical_tranche(
    *,
    overlay_path: Path,
    acceptance_plan_path: Path,
    protected_authority: str,
    native_bindings_path: Path | None = None,
) -> HistoricalTranche:
    if len(protected_authority) != 40:
        raise ValueError("protected authority must be a full Git SHA")
    overlay = json.loads(overlay_path.read_bytes())
    plan = json.loads(acceptance_plan_path.read_bytes())
    _verify_acceptance_plan(plan)
    if overlay.get("contract") != OVERLAY_CONTRACT:
        raise ValueError("unsupported overlay contract")
    if plan["overlay_manifest_digest"] != overlay.get("digest") or plan[
        "overlay_file_sha256"
    ] != _sha256(overlay_path):
        raise ValueError("overlay and acceptance authority mismatch")

    overlay_by_key = {_key(record): record for record in overlay["records"]}
    classifications = {_key(record): record for record in plan["records"]}
    bindings = _load_bindings(native_bindings_path)
    selected = {
        key: value
        for key, value in classifications.items()
        if value["classification"] in ALLOWED_CLASSIFICATIONS
    }
    blockers: set[str] = set()
    dependency_counts: Counter[str] = Counter()
    records: list[HistoricalTrancheRecord] = []

    ready_keys: set[str] = set()
    changed = True
    while changed:
        changed = False
        for key, classification in selected.items():
            source = overlay_by_key[key]
            if (
                classification["classification"] == "SAFE_UPDATE"
                and key not in bindings
            ):
                continue
            parents_ready = all(
                parent_key in bindings
                or (parent_key in selected and parent_key in ready_keys)
                for parent_key in classification.get("parent_keys", [])
            )
            if parents_ready and key not in ready_keys:
                ready_keys.add(key)
                changed = True

    for key, classification in selected.items():
        source = overlay_by_key.get(key)
        if source is None or source["source_digest"] != classification["source_digest"]:
            raise ValueError(f"missing or changed overlay source evidence: {key}")
        if source["assertion"] != classification["assertion"]:
            raise ValueError(f"overlay assertion drift: {key}")
        if _unsupported_lifecycle(source):
            raise ValueError(f"unsupported historical lifecycle: {key}")
        if classification["classification"] == "SAFE_UPDATE" and not source.get(
            "prior_source_digest"
        ):
            raise ValueError(f"safe update lacks prior source version: {key}")

        binding = bindings.get(key)
        if binding is not None and (
            binding.get("company_id") != overlay["company_id"]
            or binding.get("branch_id") not in {None, overlay["branch_id"]}
            or binding.get("source_digest")
            not in {source["source_digest"], source.get("prior_source_digest")}
        ):
            raise ValueError(f"conflicting native binding evidence: {key}")
        if classification["classification"] == "SAFE_UPDATE" and binding is None:
            blockers.add("SAFE_UPDATE_NATIVE_BINDINGS_REQUIRED")

        parent_requirements: list[str] = []
        for parent_key in classification.get("parent_keys", []):
            parent_classification = classifications.get(parent_key)
            if parent_key in selected:
                requirement = "TRANCHE_PARENT"
            elif parent_classification is None:
                requirement = "SEALED_BASE_NATIVE_BINDING_REQUIRED"
            elif parent_classification["classification"] == "HELD":
                requirement = "HELD_PARENT_NATIVE_BINDING_REQUIRED"
            else:
                requirement = "CURRENT_PACKET_NATIVE_BINDING_REQUIRED"
            dependency_counts[requirement] += 1
            parent_requirements.append(requirement)
            if requirement != "TRANCHE_PARENT" and parent_key not in bindings:
                blockers.add(requirement)

        provenance = {
            "overlay_manifest_digest": overlay["digest"],
            "acceptance_plan_digest": plan["digest"],
            "source_digest": source["source_digest"],
            "prior_source_digest": source.get("prior_source_digest"),
            "acquired_at": source["acquired_at"],
        }
        hold_reasons: list[str] = []
        if classification["classification"] == "SAFE_UPDATE" and binding is None:
            hold_reasons.append("native update binding not yet evidenced")
        for parent_key, requirement in zip(
            classification.get("parent_keys", []), parent_requirements, strict=True
        ):
            if parent_key not in bindings and parent_key not in ready_keys:
                hold_reasons.append(f"{requirement}:{parent_key}")
        records.append(
            HistoricalTrancheRecord(
                domain=source["domain"],
                source_id=source["source_id"],
                classification=classification["classification"],
                assertion=source["assertion"],
                company_id=overlay["company_id"],
                branch_id=overlay["branch_id"],
                native_id=binding.get("native_id") if binding else None,
                source_digest=source["source_digest"],
                prior_source_digest=source.get("prior_source_digest"),
                acquired_at=source["acquired_at"],
                lifecycle=_lifecycle(source),
                parent_keys=tuple(classification.get("parent_keys", [])),
                parent_requirements=tuple(parent_requirements),
                readiness="ADMIT" if key in ready_keys else "HOLD",
                hold_reason=";".join(hold_reasons) or None,
                provenance_digest=_canonical_digest(provenance),
                payload=source.get("payload") or {},
            )
        )

    records.sort(key=lambda item: (DOMAIN_ORDER[item.domain], item.source_id))
    counts: dict[str, Counter[str]] = {}
    readiness_counts: Counter[str] = Counter()
    for record in records:
        counts.setdefault(record.domain, Counter())[record.classification] += 1
        readiness_counts[f"{record.domain}:{record.readiness}"] += 1
    normalized_counts = {
        domain: dict(sorted(values.items()))
        for domain, values in sorted(counts.items())
    }
    body = {
        "contract": CONTRACT,
        "protected_authority": protected_authority,
        "overlay_manifest_digest": overlay["digest"],
        "overlay_file_sha256": _sha256(overlay_path),
        "acceptance_plan_digest": plan["digest"],
        "company_id": overlay["company_id"],
        "branch_id": overlay["branch_id"],
        "counts": normalized_counts,
        "dependency_counts": dict(sorted(dependency_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "records": [asdict(record) for record in records],
        "execution_allowed": not blockers,
        "execution_blockers": sorted(blockers),
    }
    return HistoricalTranche(
        contract=CONTRACT,
        protected_authority=protected_authority,
        overlay_manifest_digest=overlay["digest"],
        overlay_file_sha256=_sha256(overlay_path),
        acceptance_plan_digest=plan["digest"],
        company_id=overlay["company_id"],
        branch_id=overlay["branch_id"],
        counts=normalized_counts,
        dependency_counts=dict(sorted(dependency_counts.items())),
        readiness_counts=dict(sorted(readiness_counts.items())),
        records=tuple(records),
        execution_allowed=not blockers,
        execution_blockers=tuple(sorted(blockers)),
        digest=_canonical_digest(body),
    )
