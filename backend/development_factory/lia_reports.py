from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from development_factory.lia_planner import ExecutionPlan, IntegrationPlan
from development_factory.reports import redact
from development_factory.run_records import RunActionAudit


LIA_REPORT_VERSION = "1.0"


@dataclass(frozen=True)
class SupervisoryWorkerReport:
    task_id: str
    agent_id: str
    role_id: str
    workflow_state: str
    eligibility: str
    dependencies: tuple[str, ...]
    validation_status: str
    changed_file_boundary: tuple[str, ...]
    escalation_flags: tuple[str, ...]


@dataclass(frozen=True)
class LiaSupervisoryReport:
    schema_version: str
    supervisory_run_id: str
    parent_milestone: str
    generated_at: str
    branch: str
    starting_head: str
    ending_head: str
    workflow_state: str
    workers: tuple[SupervisoryWorkerReport, ...]
    execution_waves: tuple[tuple[str, ...], ...]
    dependency_status: tuple[tuple[str, tuple[str, ...]], ...]
    validation_summary: str
    conflicts: tuple[str, ...]
    blockers: tuple[str, ...]
    architecture_escalations: tuple[str, ...]
    security_escalations: tuple[str, ...]
    integration_recommendation: IntegrationPlan
    owner_decisions_required: tuple[str, ...]
    actions: RunActionAudit
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return _sanitize(asdict(self))


def write_supervisory_report(
    report: LiaSupervisoryReport, output_directory: Path
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / f"{report.supervisory_run_id}.json"
    markdown_path = output_directory / f"{report.supervisory_run_id}.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_supervisory_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_supervisory_markdown(report: LiaSupervisoryReport) -> str:
    lines = [
        "# LIA Supervisory Report",
        "",
        f"- Supervisory run: `{report.supervisory_run_id}`",
        f"- Parent milestone: {redact(report.parent_milestone)}",
        f"- Workflow state: `{report.workflow_state}`",
        f"- Dry run: {report.dry_run}",
        f"- Starting HEAD: `{report.starting_head}`",
        f"- Ending HEAD: `{report.ending_head}`",
        "",
        "## Worker assignments",
        "",
    ]
    lines.extend(
        f"- `{worker.task_id}` → {worker.agent_id} ({worker.role_id}); "
        f"{worker.eligibility}; validation {worker.validation_status}"
        for worker in report.workers
    )
    lines.extend(["", "## Execution waves", ""])
    lines.extend(
        f"- Wave {index}: {', '.join(f'`{task}`' for task in wave)}"
        for index, wave in enumerate(report.execution_waves, start=1)
    )
    lines.extend(["", "## Conflicts and blockers", ""])
    values = (*report.conflicts, *report.blockers)
    lines.extend(f"- {redact(item)}" for item in values)
    if not values:
        lines.append("- None.")
    lines.extend(["", "## Integration recommendation", ""])
    lines.extend(
        [
            f"- Conflict risk: {report.integration_recommendation.conflict_risk}",
            "- Review order: "
            + ", ".join(report.integration_recommendation.recommended_review_order),
            "- Integration order: "
            + ", ".join(
                report.integration_recommendation.recommended_integration_order
            ),
            "- Required revalidation: "
            + ", ".join(report.integration_recommendation.required_revalidation),
            "",
            "## Owner decisions required",
            "",
            *[f"- [ ] {redact(item)}" for item in report.owner_decisions_required],
            "",
            "## Privileged-action audit",
            "",
            f"- Commit occurred: {report.actions.committed}",
            f"- Push occurred: {report.actions.pushed}",
            f"- Merge occurred: {report.actions.merged}",
            f"- Deployment occurred: {report.actions.deployed}",
            "",
            "LIA coordinates and recommends. The owner remains the approval authority.",
            "",
        ]
    )
    return "\n".join(lines)


def planned_integration(
    execution: ExecutionPlan, validation: tuple[str, ...]
) -> IntegrationPlan:
    order = tuple(task for wave in execution.waves for task in wave.task_ids)
    return IntegrationPlan(
        completion_status=tuple((task_id, "not_started") for task_id in order),
        validation_status=tuple((task_id, "not_run_dry_run") for task_id in order),
        changed_file_summaries=tuple((task_id, ()) for task_id in order),
        dependency_order=order,
        conflict_risk="owner_review_required",
        recommended_review_order=order,
        recommended_integration_order=order,
        required_revalidation=validation,
        blocking_findings=(),
        owner_decisions_required=(
            "Approve or reject worker execution after reviewing this dry run.",
            "Review completed worker outputs before any integration.",
            "Approve each privileged action separately if later requested.",
        ),
    )


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value
