from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from development_factory.automation import TaskRunner
from development_factory.engine import DevelopmentFactory
from development_factory.lia import LiaSupervisor
from development_factory.lia_contract import LiaContractError
from development_factory.lia_roles import AgentRoleError
from development_factory.manifest import ManifestError
from development_factory.reports import render_markdown
from development_factory.task_contract import TaskContractError
from development_factory.workflow import Action, WorkflowError, WorkflowState


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="development-factory",
        description="Validate and report on ACP Enterprise without mutating source or Git.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--backend", action="store_true")
    validate.add_argument("--frontend", action="store_true")
    validate.add_argument("--migrations", action="store_true")
    validate.add_argument("--architecture", action="store_true")
    validate.add_argument("--changed", action="store_true")
    subparsers.add_parser("report")
    task = subparsers.add_parser("task")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    task_inspect = task_commands.add_parser("inspect")
    task_inspect.add_argument("contract", type=Path)
    task_run = task_commands.add_parser("run")
    task_run.add_argument("contract", type=Path)
    task_run.add_argument("--dry-run", action="store_true")
    task_action = task_commands.add_parser("check-action")
    task_action.add_argument("contract", type=Path)
    task_action.add_argument("--action", choices=[item.value for item in Action])
    task_action.add_argument("--state", choices=[item.value for item in WorkflowState])
    lia = subparsers.add_parser("lia")
    lia_commands = lia.add_subparsers(dest="lia_command", required=True)
    lia_inspect = lia_commands.add_parser("inspect")
    lia_inspect.add_argument("contract", type=Path)
    lia_dry_run = lia_commands.add_parser("dry-run")
    lia_dry_run.add_argument("contract", type=Path)
    lia_action = lia_commands.add_parser("check-action")
    lia_action.add_argument("action", choices=[item.value for item in Action])
    args = parser.parse_args()

    try:
        if args.command == "lia":
            supervisor = LiaSupervisor(args.repo_root)
            if args.lia_command == "inspect":
                lia_contract, plan, issues = supervisor.inspect(args.contract)
                print(
                    f"LIA run: {lia_contract.supervisory_run_id} "
                    f"({lia_contract.parent_milestone})"
                )
                for wave in plan.waves:
                    print(f"Wave {wave.number}: {', '.join(wave.task_ids)}")
                if issues:
                    for issue in issues:
                        print(f"BLOCKED: {issue}")
                    return 1
                print("Supervisory contract and repository preconditions are valid.")
                return 0
            if args.lia_command == "check-action":
                supervisor.check_action(Action(args.action))
                print("LIA action is permitted.")
                return 0
            lia_report, json_path, markdown_path = supervisor.dry_run(args.contract)
            print(f"LIA supervisory state: {lia_report.workflow_state}")
            print(f"JSON supervisory report: {json_path}")
            print(f"Markdown supervisory report: {markdown_path}")
            if lia_report.blockers:
                for blocker in lia_report.blockers:
                    print(f"BLOCKED: {blocker}")
                return 1
            return 0

        if args.command == "task":
            runner = TaskRunner(args.repo_root)
            if args.task_command == "inspect":
                task_contract, issues = runner.inspect(args.contract)
                print(f"Task: {task_contract.task_id} ({task_contract.milestone})")
                print(f"Workflow state: {task_contract.workflow_state.value}")
                if issues:
                    for issue in issues:
                        print(f"BLOCKED: {issue}")
                    return 1
                print("Contract and repository preconditions are valid.")
                return 0
            if args.task_command == "check-action":
                runner.check_action(
                    args.contract,
                    Action(args.action),
                    WorkflowState(args.state),
                )
                print("Action is permitted by both contract and workflow state.")
                return 0
            record, json_path, markdown_path = runner.run(
                args.contract, dry_run=args.dry_run
            )
            print(f"Task run state: {record.workflow_state.value}")
            print(f"JSON run record: {json_path}")
            print(f"Markdown run record: {markdown_path}")
            if record.blockers:
                for blocker in record.blockers:
                    print(f"BLOCKED: {blocker}")
                return 1
            return 0

        factory = DevelopmentFactory(args.repo_root)
        if args.command == "report":
            latest = args.repo_root / ".development-factory" / "latest.json"
            if not latest.exists():
                print("No report exists. Run validation first.", file=sys.stderr)
                return 2
            report = json.loads(latest.read_text(encoding="utf-8"))
            print(render_markdown(report))
            return int(report.get("exit_status", 1))

        selected = tuple(
            name
            for name in ("backend", "frontend", "migrations", "architecture")
            if getattr(args, name)
        )
        if not selected and not args.changed:
            selected = ("all",)
        validation_report, json_path, markdown_path = factory.validate(
            selected, changed_only=args.changed
        )
        for result in validation_report["checks"]:
            print(
                f"[{str(result['status']).upper():13}] "
                f"{result['id']}: {result['summary']}"
            )
        print(f"JSON report: {json_path}")
        print(f"Markdown report: {markdown_path}")
        print(f"Classification: {validation_report['readiness']}")
        return int(validation_report["exit_status"])
    except (
        ManifestError,
        AgentRoleError,
        LiaContractError,
        TaskContractError,
        WorkflowError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"Development Factory configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
