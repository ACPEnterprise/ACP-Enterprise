"""Deterministic readiness and receipt reconciliation for the HCP current overlay."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "hcp-current-overlay-post-admission-acceptance/v1"
EXPECTED_OVERLAY_COUNTS: Final = {
    "customer": {"create": 55, "update": 20, "remove": 1},
    "service_location": {"create": 63},
    "job": {"create": 49, "update": 254, "hold": 8},
    "appointment": {"create": 47, "update": 6},
}
EXPECTED_CURRENT_COUNTS: Final = {
    "customer": 11,
    "service_location": 11,
    "job": 15,
    "appointment": 18,
}
JOB_STATUS: Final = {
    "needs scheduling": "ready",
    "scheduled": "ready",
    "in progress": "in_progress",
    "complete rated": "completed",
    "complete unrated": "completed",
    "pro canceled": "cancelled",
    "user canceled": "cancelled",
}


class WriteClassification(StrEnum):
    CURRENT_OPERATIONAL = "CURRENT_OPERATIONAL"
    SAFE_HISTORICAL = "SAFE_HISTORICAL"
    SAFE_SUPPORTING_PARENT = "SAFE_SUPPORTING_PARENT"
    SAFE_UPDATE = "SAFE_UPDATE"
    HELD = "HELD"


@dataclass(frozen=True, slots=True)
class ClassifiedRecord:
    domain: str
    source_id: str
    assertion: str
    classification: WriteClassification
    reason: str
    source_digest: str
    parent_keys: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.domain}:{self.source_id}"


@dataclass(frozen=True, slots=True)
class AcceptancePlan:
    contract: str
    overlay_manifest_digest: str
    overlay_file_sha256: str
    acquired_at: str
    cutoff_date: str
    records: tuple[ClassifiedRecord, ...]
    classification_counts: dict[str, dict[str, int]]
    assertion_counts: dict[str, dict[str, int]]
    current_source_ids: dict[str, tuple[str, ...]]
    digest: str

    def verify(self) -> None:
        expected = _build_plan(
            overlay_manifest_digest=self.overlay_manifest_digest,
            overlay_file_sha256=self.overlay_file_sha256,
            acquired_at=self.acquired_at,
            cutoff_date=self.cutoff_date,
            records=self.records,
            current_source_ids=self.current_source_ids,
        )
        if self.contract != CONTRACT or self.digest != expected.digest:
            raise ValueError("post-admission acceptance plan digest mismatch")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pages(root: Path, stem: str, key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob(f"{stem}-page-*.json")):
        value = json.loads(path.read_bytes())
        rows.extend(value[key])
    return rows


def _current_scope(
    *, refresh_root: Path, schedule_root: Path, cutoff: date
) -> tuple[dict[str, set[str]], dict[str, dict[str, Any]]]:
    jobs = {row["id"]: row for row in _pages(refresh_root, "jobs", "jobs")}
    jobs_by_hash = {
        hashlib.sha256(source_id.encode()).hexdigest(): row
        for source_id, row in jobs.items()
    }
    scope: dict[str, set[str]] = {domain: set() for domain in EXPECTED_CURRENT_COUNTS}
    for path in sorted(schedule_root.glob("job-*-appointments-http-200.json")):
        job_hash = path.name.split("-")[1]
        job = jobs_by_hash.get(job_hash)
        if job is None:
            raise ValueError("schedule artifact has no current Job authority")
        for appointment in json.loads(path.read_bytes()).get("appointments", []):
            start = datetime.fromisoformat(
                str(appointment["start_time"]).replace("Z", "+00:00")
            )
            if start.date() < cutoff:
                continue
            location_id = (job.get("address") or {}).get("id")
            customer_id = (job.get("customer") or {}).get("id")
            if not location_id or not customer_id:
                raise ValueError("current Appointment lacks Customer/Location closure")
            scope["appointment"].add(appointment["id"])
            scope["job"].add(job["id"])
            scope["customer"].add(customer_id)
            scope["service_location"].add(location_id)
    observed = {domain: len(values) for domain, values in scope.items()}
    if observed != EXPECTED_CURRENT_COUNTS:
        raise ValueError(f"current calendar baseline mismatch: {observed}")
    return scope, jobs


def _hold_reason(record: dict[str, Any]) -> str | None:
    assertion, domain = record["assertion"], record["domain"]
    payload = record.get("payload") or {}
    if assertion == "hold":
        return record.get("reason") or "packet_hold"
    if assertion == "remove":
        return "non_destructive_removal_assertion"
    if domain == "service_location" and not all(
        payload.get(key) for key in ("street", "city", "state", "zip")
    ):
        return "incomplete_address"
    if domain == "job":
        work_status = payload.get("work_status")
        status = JOB_STATUS.get(work_status) if isinstance(work_status, str) else None
        timestamps = payload.get("work_timestamps") or {}
        if status == "cancelled":
            return "cancelled_lifecycle_unsupported"
        if assertion == "update" and status not in {"draft", "ready"}:
            return "historical_lifecycle_update_not_authoritative"
        if (
            assertion == "create"
            and status in {"in_progress", "completed"}
            and not timestamps.get("started_at")
        ):
            return "incomplete_lifecycle_timestamps"
    if domain == "appointment" and assertion == "update":
        return "historical_update_requires_native_lifecycle_hold"
    return None


def _classification(
    record: dict[str, Any], current: dict[str, set[str]]
) -> tuple[WriteClassification, str]:
    hold_reason = _hold_reason(record)
    if hold_reason:
        return WriteClassification.HELD, hold_reason
    domain, source_id, assertion = (
        record["domain"],
        record["source_id"],
        record["assertion"],
    )
    if source_id in current[domain]:
        if domain in {"customer", "service_location"}:
            return WriteClassification.SAFE_SUPPORTING_PARENT, "current_graph_parent"
        return WriteClassification.CURRENT_OPERATIONAL, "current_calendar_member"
    if assertion == "update":
        return WriteClassification.SAFE_UPDATE, "compare_before_write"
    return WriteClassification.SAFE_HISTORICAL, "bounded_non_current_operational_truth"


def build_acceptance_plan(
    *,
    overlay_path: Path,
    refresh_root: Path,
    schedule_root: Path,
    cutoff: date,
) -> AcceptancePlan:
    overlay = json.loads(overlay_path.read_bytes())
    current, _ = _current_scope(
        refresh_root=refresh_root, schedule_root=schedule_root, cutoff=cutoff
    )
    assertions: dict[str, Counter[str]] = {}
    records: list[ClassifiedRecord] = []
    for record in overlay["records"]:
        assertions.setdefault(record["domain"], Counter())[record["assertion"]] += 1
        classification, reason = _classification(record, current)
        records.append(
            ClassifiedRecord(
                domain=record["domain"],
                source_id=record["source_id"],
                assertion=record["assertion"],
                classification=classification,
                reason=reason,
                source_digest=record["source_digest"],
                parent_keys=tuple(
                    f"{parent['domain']}:{parent['source_id']}"
                    for parent in record.get("parent_keys", [])
                ),
            )
        )
    observed_assertions = {
        domain: dict(sorted(counts.items()))
        for domain, counts in sorted(assertions.items())
    }
    if observed_assertions != EXPECTED_OVERLAY_COUNTS:
        raise ValueError(
            f"overlay assertion accounting mismatch: {observed_assertions}"
        )
    return _build_plan(
        overlay_manifest_digest=overlay["digest"],
        overlay_file_sha256=_sha256(overlay_path),
        acquired_at=overlay["acquired_at"],
        cutoff_date=cutoff.isoformat(),
        records=tuple(sorted(records, key=lambda item: item.key)),
        current_source_ids={
            domain: tuple(sorted(values)) for domain, values in current.items()
        },
    )


def _build_plan(
    *,
    overlay_manifest_digest: str,
    overlay_file_sha256: str,
    acquired_at: str,
    cutoff_date: str,
    records: tuple[ClassifiedRecord, ...],
    current_source_ids: dict[str, tuple[str, ...]],
) -> AcceptancePlan:
    classifications: dict[str, Counter[str]] = {}
    assertions: dict[str, Counter[str]] = {}
    for record in records:
        classifications.setdefault(record.domain, Counter())[record.classification] += 1
        assertions.setdefault(record.domain, Counter())[record.assertion] += 1
    classification_counts = {
        domain: dict(sorted(counts.items()))
        for domain, counts in sorted(classifications.items())
    }
    assertion_counts = {
        domain: dict(sorted(counts.items()))
        for domain, counts in sorted(assertions.items())
    }
    payload = {
        "contract": CONTRACT,
        "overlay_manifest_digest": overlay_manifest_digest,
        "overlay_file_sha256": overlay_file_sha256,
        "acquired_at": acquired_at,
        "cutoff_date": cutoff_date,
        "records": [asdict(record) for record in records],
        "classification_counts": classification_counts,
        "assertion_counts": assertion_counts,
        "current_source_ids": current_source_ids,
    }
    return AcceptancePlan(
        CONTRACT,
        overlay_manifest_digest,
        overlay_file_sha256,
        acquired_at,
        cutoff_date,
        records,
        classification_counts,
        assertion_counts,
        current_source_ids,
        _digest(payload),
    )


def verify_execution(
    plan: AcceptancePlan,
    *,
    receipt: dict[str, Any],
    snapshot: dict[str, Any],
    replay_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail closed over Enterprise's read-only post-execution evidence snapshot."""
    plan.verify()
    if receipt.get("manifest_digest") != plan.overlay_manifest_digest:
        raise ValueError("execution receipt manifest mismatch")
    journal = receipt.get("journal") or []
    by_key = {
        f"{item['key']['domain']}:{item['key']['source_id']}": item for item in journal
    }
    if len(by_key) != len(journal) or set(by_key) != {
        record.key for record in plan.records
    }:
        raise ValueError("execution receipt source identity accounting mismatch")
    for record in plan.records:
        outcome = by_key[record.key]["outcome"]
        allowed = (
            {"held", "removal_recorded"}
            if record.classification is WriteClassification.HELD
            else {"created", "updated", "idempotent_replay"}
        )
        if outcome not in allowed:
            raise ValueError(f"unexpected execution outcome for {record.key}")
        if outcome in {"created", "updated", "idempotent_replay"} and not by_key[
            record.key
        ].get("native_id"):
            raise ValueError(f"admitted identity has no native binding: {record.key}")
    admitted = [
        (item["key"]["domain"], item.get("native_id"))
        for item in journal
        if item["outcome"] in {"created", "updated", "idempotent_replay"}
    ]
    if len(admitted) != len(set(admitted)):
        raise ValueError("multiple overlay identities bind one native record")
    if replay_receipt is not None and replay_receipt != receipt:
        raise ValueError("successful replay did not return the identical receipt")
    _verify_snapshot(plan, snapshot)
    return {
        "contract": CONTRACT,
        "status": "ACCEPTED",
        "receipt_digest": receipt.get("digest"),
        "counts": dict(Counter(item["outcome"] for item in journal)),
        "current_counts": EXPECTED_CURRENT_COUNTS,
        "digest": _digest(
            {
                "plan": plan.digest,
                "receipt": receipt.get("digest"),
                "snapshot": snapshot.get("digest"),
            }
        ),
    }


def _verify_snapshot(plan: AcceptancePlan, snapshot: dict[str, Any]) -> None:
    if snapshot.get("mutation_authority") != "none":
        raise ValueError("acceptance snapshot must be read-only")
    records = snapshot.get("current_records") or []
    by_domain: dict[str, dict[str, dict[str, Any]]] = {
        domain: {} for domain in EXPECTED_CURRENT_COUNTS
    }
    for record in records:
        values = by_domain.get(record.get("domain"))
        if values is None or record["source_id"] in values:
            raise ValueError("duplicate or unsupported current snapshot identity")
        values[record["source_id"]] = record
    for domain, expected_ids in plan.current_source_ids.items():
        if set(by_domain[domain]) != set(expected_ids):
            raise ValueError(f"current {domain} population mismatch")
    native_ids = [(record["domain"], record["native_id"]) for record in records]
    if any(not value for _, value in native_ids) or len(native_ids) != len(
        set(native_ids)
    ):
        raise ValueError("current snapshot has missing/duplicate native identity")
    for record in records:
        if not record.get("source_digest") or not record.get("native_evidence_digest"):
            raise ValueError("current source/native evidence digest is missing")
        if not record.get("company_scope_matches") or not record.get(
            "branch_scope_matches"
        ):
            raise ValueError("current snapshot leaks Company/Branch scope")
        if record["domain"] == "appointment":
            required = {
                "local_date_matches",
                "arrival_window_matches",
                "duration_matches",
                "status_matches",
                "technician_truth_matches",
                "cancellation_completion_matches",
                "customer_parent_matches",
                "location_parent_matches",
                "job_parent_matches",
            }
            if not all(record.get(key) is True for key in required):
                raise ValueError("current Appointment projection mismatch")
            lanes = record.get("lane_membership") or {}
            if not all(
                lanes.get(key) is True
                for key in ("day", "week", "work_week", "month", "dispatch")
            ):
                raise ValueError("current Appointment calendar fan-out mismatch")
    if snapshot.get("active_held_source_ids"):
        raise ValueError("held source identity appeared in active native truth")
    if (
        snapshot.get("orphan_count") != 0
        or snapshot.get("lifecycle_regression_count") != 0
    ):
        raise ValueError("orphan or lifecycle regression detected")
    if snapshot.get("replay_business_event_delta") != 0:
        raise ValueError("idempotent replay duplicated Business Events")
    if (
        snapshot.get("technician_hold_count") != 0
        or snapshot.get("current_location_gap_count") != 0
    ):
        raise ValueError("current calendar technician/Location expectation failed")


def verify_failed_execution(evidence: dict[str, Any]) -> dict[str, Any]:
    """Verify externally captured failure evidence after the DB transaction rolled back."""
    required = (
        evidence.get("state") == "failure",
        evidence.get("transaction_rolled_back") is True,
        evidence.get("before_native_digest") == evidence.get("after_native_digest"),
        evidence.get("before_event_digest") == evidence.get("after_event_digest"),
        evidence.get("success_receipt_persisted") is False,
        evidence.get("restore_receipt_digest") is not None,
    )
    if not all(required):
        raise ValueError("failed overlay execution did not prove atomic rollback")
    return {
        "contract": CONTRACT,
        "status": "FAILED_EXECUTION_SAFELY_RECONCILED",
        "digest": _digest(evidence),
    }
