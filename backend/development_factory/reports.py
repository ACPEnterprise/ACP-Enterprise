from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from development_factory import SCHEMA_VERSION
from development_factory.models import CheckResult, RepositoryState
from development_factory.repository import (
    classification_summary,
    sensitive_change_flags,
)


SECRET_PATTERN = re.compile(
    r"(?i)(password|token|secret|api[_-]?key|database_url)"
    r"(\s*[:=]\s*)([\"']?)([^\s,\"'}]+)([\"']?)"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*")
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def redact(value: str) -> str:
    redacted = SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value
    )
    redacted = BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    return PRIVATE_KEY_PATTERN.sub("[REDACTED PRIVATE KEY]", redacted)


def build_report(
    *,
    state: RepositoryState,
    scope: tuple[str, ...],
    results: tuple[CheckResult, ...],
    environment: dict[str, str],
) -> dict[str, Any]:
    blocking_failures = [
        result.id
        for result in results
        if result.required and result.status in {"failed", "unavailable", "blocked"}
    ]
    if not state.files and all(result.status == "skipped" for result in results):
        readiness = "No changes detected"
    elif any(result.status == "failed" and result.required for result in results):
        readiness = "Blocked by validation failures"
    elif any(result.status == "unavailable" and result.required for result in results):
        readiness = "Blocked by unavailable required checks"
    elif blocking_failures:
        readiness = "Validation incomplete"
    else:
        readiness = "Ready for owner review"

    findings = [
        asdict(finding)
        for result in results
        for finding in result.findings
        if not finding.suppressed
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": {
            "branch": state.branch,
            "head": state.head,
            "working_tree_clean": state.working_tree_clean,
            "index_clean": state.index_clean,
            "conflicts": state.conflicts,
        },
        "selected_scope": list(scope),
        "environment": environment,
        "checks": [result.to_dict() for result in results],
        "exit_status": 0 if not blocking_failures else 1,
        "readiness": readiness,
        "changed_files": [asdict(item) for item in state.files],
        "classification_totals": classification_summary(state),
        "change_flags": sensitive_change_flags(state),
        "architecture_findings": [
            item
            for item in findings
            if str(item["rule_id"]).startswith("architecture.")
        ],
        "security_findings": [
            item
            for item in findings
            if str(item["rule_id"]).startswith(("security.", "tenant."))
        ],
        "migration_findings": [
            result.to_dict() for result in results if result.category == "migrations"
        ],
        "test_summaries": [
            result.to_dict()
            for result in results
            if result.failure_classification == "test"
        ],
        "warnings": [
            item for item in findings if item["severity"] in {"warning", "info"}
        ],
        "blocking_failures": blocking_failures,
        "owner_review_items": _owner_review_items(state, results, findings),
    }


def write_reports(report: dict[str, Any], output_directory: Path) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "latest.json"
    markdown_path = output_directory / "latest.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_markdown(report: dict[str, Any]) -> str:
    repository = report["repository"]
    checks = report["checks"]
    lines = [
        "# ACP Development Factory Report",
        "",
        f"**Classification:** {report['readiness']}",
        "",
        "## 1. Repository state",
        "",
        f"- Branch: `{repository['branch']}`",
        f"- HEAD: `{repository['head']}`",
        f"- Working tree clean: {repository['working_tree_clean']}",
        f"- Index clean: {repository['index_clean']}",
        "",
        "## 2. Changed-file boundary",
        "",
    ]
    files = report["changed_files"]
    if files:
        lines.extend(
            f"- `{item['path']}` — {item['category']} ({item['state']})"
            for item in files
        )
    else:
        lines.append("- No changes detected.")
    lines.extend(["", "## 3. Validation summary", ""])
    lines.extend(
        f"- **{item['status'].upper()}** `{item['id']}` — {item['summary']}"
        for item in checks
    )
    for heading, key in (
        ("4. Architecture findings", "architecture_findings"),
        ("5. Security and tenant-isolation findings", "security_findings"),
    ):
        lines.extend(["", f"## {heading}", ""])
        values = report[key]
        if values:
            lines.extend(
                f"- {item['severity'].upper()} `{item['rule_id']}` "
                f"`{item['path']}:{item.get('line') or '-'}` — {item['message']}"
                for item in values
            )
        else:
            lines.append("- No unsuppressed findings.")
    lines.extend(
        [
            "",
            "## 6. Migration status",
            "",
            *_result_lines(checks, "migrations"),
            "",
            "## 7. Test results",
            "",
            *[
                f"- `{item['id']}`: {item['status']} — {item['summary']}"
                for item in report["test_summaries"]
            ],
            "",
            "## 8. Warnings and unavailable checks",
            "",
        ]
    )
    unavailable = [
        item
        for item in checks
        if item["status"] in {"unavailable", "skipped", "blocked"}
    ]
    lines.extend(
        (
            f"- `{item['id']}`: {item['status']} — {item['summary']}"
            for item in unavailable
        ),
    )
    if not unavailable:
        lines.append("- None.")
    lines.extend(["", "## 9. Owner-review checklist", ""])
    lines.extend(f"- [ ] {item}" for item in report["owner_review_items"])
    lines.extend(
        [
            "",
            "## 10. Commit readiness",
            "",
            f"**{report['readiness']}**",
            "",
            "Automation does not approve, stage, commit, push, merge, or deploy.",
            "",
        ]
    )
    return "\n".join(lines)


def _result_lines(checks: list[dict[str, Any]], category: str) -> list[str]:
    values = [item for item in checks if item["category"] == category]
    return (
        [f"- `{item['id']}`: {item['status']} — {item['summary']}" for item in values]
        if values
        else ["- Not selected."]
    )


def _owner_review_items(
    state: RepositoryState,
    results: tuple[CheckResult, ...],
    findings: list[dict[str, Any]],
) -> list[str]:
    return [
        "Implementation stayed within the approved scope.",
        "Architecture findings are understood and acceptable.",
        "Security and tenant-isolation findings are understood and acceptable.",
        "Required tests passed; unavailable checks are explicitly reviewed.",
        "Migrations, if changed, were validated only on disposable PostgreSQL.",
        f"Changed-file boundary contains {len(state.files)} file(s) and no unrelated work.",
        "Proposed commit boundary is exact.",
        "No prohibited commit, push, merge, deployment, or shared-data action occurred.",
        f"Review {len(findings)} unsuppressed finding(s) and "
        f"{sum(result.status == 'unavailable' for result in results)} unavailable check(s).",
    ]
