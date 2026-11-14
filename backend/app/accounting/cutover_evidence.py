"""Append-only evidence packaging for Accounting cutover and case-study proof.

This module never posts journals, writes QBO, changes accounting authority, or
interprets missing evidence as zero.  It captures source digests and seals
analysis/register documents around the existing Accounting control packets.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.simulation.phase1 import run_accounting_regression_scenarios


VALUE_STATES = frozenset({"OBSERVED", "DERIVED", "RECONSTRUCTED", "APPROVED", "SUSPECTED", "UNKNOWN"})
APPROVER_ROLES = frozenset({"OWNER", "ACCOUNTANT", "PAYROLL_AUTHORITY", "TAX_PROFESSIONAL"})
MILESTONES = (
    "SOURCE_BASELINE",
    "DISCOVERY",
    "RECONSTRUCTION",
    "DECISIONS",
    "CORRECTION",
    "VALIDATION",
    "CUTOVER",
    "FIRST_NATIVE_CLOSE",
)
SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|credential|api[_-]?key|access[_-]?key|tax[_-]?id|bank[_-]?(account|routing)|card[_-]?(number|cvv)|ssn|social[_-]?security)",
    re.I,
)
PII_KEY_RE = re.compile(
    r"(^|_)(first|last|full)?_?(name|email|phone|mobile|address|street|city|zip|employee|customer|vendor|counterparty)(_|$)",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _protected_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(path, 0o700)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    body = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(body)
    os.chmod(path, 0o600)


def _require_text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def _sensitive_name(name: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(name))


def capture_source_baseline(
    *, source_root: Path, output_root: Path, authority_id: str, cutoff: str
) -> dict[str, Any]:
    """Copy immutable source evidence and emit a digest-only baseline manifest."""
    if not source_root.is_dir() or source_root.is_symlink():
        raise ValueError("source evidence root is missing or unsafe")
    if output_root.exists():
        raise FileExistsError(f"baseline output already exists: {output_root}")
    _protected_dir(output_root)
    private_root = output_root / "source"
    private_root.mkdir(mode=0o700)
    files: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for path in sorted(source_root.rglob("*")):
        relative = path.relative_to(source_root)
        if path.is_dir():
            continue
        if path.is_symlink():
            excluded.append({"path": str(relative), "reason": "symlink_not_copied"})
            continue
        if _sensitive_name(path.name):
            excluded.append({"path": str(relative), "reason": "secret_like_filename_not_copied"})
            continue
        target = private_root / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        os.chmod(target, 0o600)
        files.append(
            {
                "path": str(relative),
                "size_bytes": path.stat().st_size,
                "sha256": file_digest(path),
                "source_mode": stat.S_IMODE(path.stat().st_mode),
            }
        )
    manifest: dict[str, Any] = {
        "contract": "twelvehats-accounting-source-baseline/v1",
        "captured_at": _now(),
        "authority_id": authority_id,
        "cutoff": cutoff,
        "source_root_label": str(source_root),
        "files": files,
        "excluded": excluded,
        "source_mutation": "PROHIBITED_AND_NOT_PERFORMED",
    }
    manifest["baseline_digest"] = digest({key: value for key, value in manifest.items() if key != "baseline_digest"})
    _write_json(output_root / "source-baseline.json", manifest)
    return manifest


def _validate_issue(issue: Mapping[str, Any]) -> None:
    _require_text(issue, "issue_id")
    _require_text(issue, "category")
    _require_text(issue, "description")
    for key in ("business_impact", "accounting_impact"):
        _require_text(issue, key)
    if not isinstance(issue.get("affected_accounts_or_entities"), list):
        raise ValueError("issue affected_accounts_or_entities is required")
    if not isinstance(issue.get("materiality"), (str, int, float)):
        raise ValueError("issue materiality is required")
    if issue.get("value_status") not in VALUE_STATES:
        raise ValueError("issue value_status is invalid")
    if not isinstance(issue.get("source_provenance"), list):
        raise ValueError("issue source_provenance is required")


def _validate_provenance(row: Mapping[str, Any]) -> None:
    _require_text(row, "provenance_id")
    _require_text(row, "conclusion_id")
    for key in ("source_evidence", "conflicting_evidence", "source_dates", "unresolved_contradictions", "accepted_evidence"):
        if not isinstance(row.get(key, []), list):
            raise ValueError(f"provenance {key} must be a list")
    _require_text(row, "source_system_authority")
    _require_text(row, "confidence")
    _require_text(row, "decision_authority")
    if row.get("value_class") not in {"SOURCE VALUE", "OBSERVED VALUE", "RECONSTRUCTED VALUE", "APPROVED VALUE"}:
        raise ValueError("provenance value_class is invalid")


def _validate_decision(row: Mapping[str, Any]) -> None:
    _require_text(row, "decision_id")
    _require_text(row, "request")
    if row.get("approver_role") not in APPROVER_ROLES:
        raise ValueError("decision approver_role is invalid")


def _validate_correction(row: Mapping[str, Any], issue_ids: set[str]) -> None:
    _require_text(row, "correction_id")
    issue_id = _require_text(row, "issue_id")
    if issue_id not in issue_ids:
        raise ValueError("correction references unknown issue")
    for key in ("evidence_used", "accounts_affected", "validation"):
        if not isinstance(row.get(key), list):
            raise ValueError(f"correction {key} must be a list")
    _require_text(row, "detected_by")
    _require_text(row, "analyzed_by")
    _require_text(row, "occurred_at")
    _require_text(row, "native_action")


def _unique(rows: list[Mapping[str, Any]], key: str) -> None:
    values = [_require_text(row, key) for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {key}")


def _sanitize(value: Any, *, key: str = "") -> Any:
    if SENSITIVE_KEY_RE.search(key):
        return "[REDACTED]"
    if PII_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _sanitize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, key=key) for item in value]
    return value


def _scorecard_report(scorecard: Mapping[str, Any]) -> dict[str, Any]:
    before = scorecard.get("before", {})
    after = scorecard.get("after", {})
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise ValueError("scorecard requires before and after mappings")
    return {
        "contract": "twelvehats-accounting-before-after-scorecard/v1",
        "before": dict(before),
        "after": dict(after),
        "target": "$0.00 unexplained variance where mathematically/reconcilably expected",
        "uncertainty_policy": "unknown or unresolved evidence remains explicitly labeled; it is not forced to zero",
        "scorecard_digest": digest({"before": before, "after": after}),
    }


def seal_cutover_package(
    *, workbook: Mapping[str, Any], output_root: Path, sanitized_root: Path
) -> dict[str, Any]:
    """Validate and seal all registers plus private and sanitized derivatives."""
    if output_root.exists() or sanitized_root.exists():
        raise FileExistsError("cutover package output already exists")
    issues = [dict(row) for row in workbook.get("issues", [])]
    provenance = [dict(row) for row in workbook.get("provenance", [])]
    reconciliations = [dict(row) for row in workbook.get("reconciliations", [])]
    decisions = [dict(row) for row in workbook.get("decisions", [])]
    corrections = [dict(row) for row in workbook.get("corrections", [])]
    for row in issues:
        _validate_issue(row)
    for row in provenance:
        _validate_provenance(row)
    for row in decisions:
        _validate_decision(row)
    issue_ids = {_require_text(row, "issue_id") for row in issues}
    _unique(issues, "issue_id")
    _unique(provenance, "provenance_id")
    _unique(decisions, "decision_id")
    _unique(corrections, "correction_id")
    for row in corrections:
        _validate_correction(row, issue_ids)
    for row in decisions:
        if row.get("issue_id") is not None and str(row["issue_id"]) not in issue_ids:
            raise ValueError("decision references unknown issue")
    provenance_conclusions = {str(row["conclusion_id"]) for row in provenance}
    for issue in issues:
        if issue["issue_id"] not in provenance_conclusions:
            raise ValueError(f"issue lacks provenance: {issue['issue_id']}")

    reports: dict[str, Any] = {
        "issue-register.json": {
            "contract": "twelvehats-accounting-discrepancy-register/v1",
            "issues": issues,
        },
        "beacon-provenance-ledger.json": {
            "contract": "beacon-accounting-provenance/v1",
            "entries": provenance,
        },
        "luminary-reconciliation-findings.json": {
            "contract": "luminary-accounting-reconciliation/v1",
            "findings": reconciliations,
        },
        "lia-decision-packet-history.json": {
            "contract": "lia-accounting-decision-packet/v1",
            "decisions": decisions,
        },
        "correction-journal.json": {
            "contract": "twelvehats-accounting-correction-journal/v1",
            "corrections": corrections,
        },
        "before-after-scorecard.json": _scorecard_report(workbook.get("scorecard", {})),
    }
    milestones = workbook.get("milestones", {})
    if not isinstance(milestones, Mapping):
        raise ValueError("milestones must be a mapping")
    for name in MILESTONES:
        reports[f"milestones/{name.lower()}.json"] = {
            "contract": "twelvehats-accounting-cutover-milestone/v1",
            "milestone": name,
            "status": str(milestones.get(name, {}).get("status", "NOT_STARTED"))
            if isinstance(milestones.get(name, {}), Mapping)
            else "NOT_STARTED",
            "content": milestones.get(name, {}),
        }
    scorecard = reports["before-after-scorecard.json"]
    reports["final-reconciliation-report.json"] = {
        "contract": "twelvehats-accounting-final-reconciliation/v1",
        "status": "PASS" if not workbook.get("unresolved_external_evidence") else "PENDING_EXTERNAL_EVIDENCE",
        "scorecard_digest": scorecard["scorecard_digest"],
        "unresolved_external_evidence": list(workbook.get("unresolved_external_evidence", [])),
        "source_mutation": "PROHIBITED_AND_NOT_PERFORMED",
    }
    reports["first-native-close-report.json"] = {
        "contract": "twelvehats-first-native-accounting-close/v1",
        "status": "PENDING",
        "requires": ["approved_common_cutoff", "balanced_opening_controls", "finance_acceptance", "close_receipt"],
    }
    reports["simulation-regression-scenarios.json"] = run_accounting_regression_scenarios()

    _protected_dir(output_root)
    _protected_dir(sanitized_root)
    manifest_files: list[dict[str, Any]] = []
    for relative, value in sorted(reports.items()):
        target = output_root / relative
        _write_json(target, value)
        manifest_files.append({"path": relative, "sha256": file_digest(target), "size_bytes": target.stat().st_size})
        sanitized_target = sanitized_root / relative
        _write_json(sanitized_target, _sanitize(value))
    package_manifest = {
        "contract": "twelvehats-accounting-cutover-evidence-package/v1",
        "created_at": _now(),
        "file_count": len(manifest_files),
        "files": manifest_files,
        "source_mutation": "PROHIBITED_AND_NOT_PERFORMED",
        "sanitized_derivative": "NO_PII_OR_SECRET_VALUES",
    }
    package_manifest["package_digest"] = digest(package_manifest)
    _write_json(output_root / "package-manifest.json", package_manifest)
    _write_json(sanitized_root / "package-manifest.json", _sanitize(package_manifest))
    return package_manifest
