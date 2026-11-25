from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from development_factory.assignment_bridge import prepare_claim_envelope
from development_factory.automation import TaskRunner
from development_factory.coordination import (
    CoordinationError,
    build_daily_report,
    dependency_layers,
    eligible_after_activation,
    load_queue_file,
    write_daily_report,
)
from development_factory.engine import DevelopmentFactory
from development_factory.lia import LiaSupervisor
from development_factory.lia_contract import LiaContractError
from development_factory.lia_roles import AgentRoleError
from development_factory.manifest import ManifestError
from development_factory.owner_review import OwnerReviewError, OwnerReviewManager
from development_factory.reports import render_markdown
from development_factory.review_records import ReviewRecordError
from development_factory.task_contract import TaskContractError
from development_factory.worker_execution import WorkerExecutionError, WorkerExecutor
from development_factory.workflow import Action, WorkflowError, WorkflowState
from development_factory.workspaces import WorkspaceError, WorkspaceManager


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
    coordination = subparsers.add_parser("coordination")
    coordination_commands = coordination.add_subparsers(
        dest="coordination_command", required=True
    )
    for command in ("validate", "summary"):
        coordination_command = coordination_commands.add_parser(command)
        coordination_command.add_argument(
            "queue",
            type=Path,
            default=Path("development-factory/continuous-engineering-queue.v1.json"),
            nargs="?",
        )
    inventory_check = coordination_commands.add_parser("inventory-check")
    inventory_check.add_argument("receipt", type=Path)
    inventory_check.add_argument("--require-clean", action="store_true")
    activation_check = coordination_commands.add_parser("activation-check")
    activation_check.add_argument("inventory", type=Path)
    activation_check.add_argument("activation", type=Path)
    claim_envelope = coordination_commands.add_parser("prepare-claim")
    claim_envelope.add_argument(
        "--queue",
        type=Path,
        default=Path("development-factory/continuous-engineering-queue.v1.json"),
    )
    claim_envelope.add_argument("assignment_id")
    claim_envelope.add_argument("receipt", type=Path)
    claim_envelope.add_argument(
        "--completed-assignment",
        action="append",
        default=[],
        dest="completed_assignments",
    )
    claim_envelope.add_argument(
        "--output", type=Path, required=True, dest="claim_output"
    )
    coordination_summary = coordination_commands.choices["summary"]
    coordination_summary.add_argument(
        "--active-lane", action="append", default=[], dest="active_lanes"
    )
    coordination_summary.add_argument(
        "--completed-assignment",
        action="append",
        default=[],
        dest="completed_assignments",
    )
    daily_report = coordination_commands.add_parser("daily-report")
    daily_report.add_argument(
        "--inventory", action="append", default=[], dest="inventory_paths", type=Path
    )
    daily_report.add_argument(
        "--activation",
        action="append",
        default=[],
        dest="activation_paths",
        type=Path,
    )
    daily_report.add_argument(
        "--active-lane", action="append", default=[], dest="active_lanes"
    )
    daily_report.add_argument(
        "--completed-assignment",
        action="append",
        default=[],
        dest="completed_assignments",
    )
    daily_report.add_argument(
        "--latest-report", type=Path, default=None, dest="latest_report_path"
    )
    daily_report.add_argument(
        "--output",
        type=Path,
        default=Path(".development-factory/daily-report.json"),
    )
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
    workspace = lia_commands.add_parser("workspace")
    workspace_commands = workspace.add_subparsers(
        dest="workspace_command", required=True
    )
    for command in ("inspect", "prepare", "show"):
        workspace_command = workspace_commands.add_parser(command)
        workspace_command.add_argument("contract", type=Path)
        workspace_command.add_argument("workspace_id")
    workspace_list = workspace_commands.add_parser("list")
    workspace_list.add_argument("contract", type=Path)
    worker = lia_commands.add_parser("worker")
    worker_commands = worker.add_subparsers(dest="worker_command", required=True)
    worker_inspect = worker_commands.add_parser("inspect")
    worker_inspect.add_argument("contract", type=Path)
    worker_inspect.add_argument("task_id")
    worker_execute = worker_commands.add_parser("execute")
    worker_execute.add_argument("contract", type=Path)
    worker_execute.add_argument("task_id")
    worker_execute.add_argument("operations", type=Path)
    for command in ("validate", "show", "diff", "record", "cancel"):
        worker_command = worker_commands.add_parser(command)
        worker_command.add_argument("contract", type=Path)
        worker_command.add_argument("task_id")
    review = lia_commands.add_parser("review")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    review_inspect = review_commands.add_parser("inspect")
    review_inspect.add_argument("contract", type=Path)
    review_inspect.add_argument("input", type=Path, nargs="?")
    review_consolidate = review_commands.add_parser("consolidate")
    review_consolidate.add_argument("contract", type=Path)
    review_consolidate.add_argument("input", type=Path)
    review_list = review_commands.add_parser("list")
    review_list.add_argument("contract", type=Path)
    for command in ("show", "workers", "conflicts", "validations", "decisions"):
        review_command = review_commands.add_parser(command)
        review_command.add_argument("contract", type=Path)
        review_command.add_argument("review_id")
    review_decision = review_commands.add_parser("record-decision")
    review_decision.add_argument("contract", type=Path)
    review_decision.add_argument("review_id")
    review_decision.add_argument("decision", type=Path)
    review_cancel = review_commands.add_parser("cancel")
    review_cancel.add_argument("contract", type=Path)
    review_cancel.add_argument("review_id")
    args = parser.parse_args()

    try:
        if args.command == "coordination":
            if args.coordination_command == "inventory-check":
                from development_factory.coordination import load_inventory_file

                receipt = load_inventory_file(args.receipt)
                repository = receipt["repository"]
                assert isinstance(repository, dict)
                clean = repository.get("status_clean") is True
                print(
                    f"Machine inventory valid: {receipt['role_claimed']} "
                    f"{repository['branch']} {repository['head']}"
                )
                print(f"Repository clean: {'YES' if clean else 'NO'}")
                if args.require_clean and not clean:
                    print("BLOCKED: repository has uncommitted changes")
                    return 1
                return 0
            if args.coordination_command == "activation-check":
                from development_factory.coordination import (
                    load_inventory_file,
                    validate_activation,
                )

                inventory_path = args.inventory
                activation_path = args.activation
                if not inventory_path.is_absolute():
                    inventory_path = args.repo_root / inventory_path
                if not activation_path.is_absolute():
                    activation_path = args.repo_root / activation_path
                inventory = load_inventory_file(inventory_path)
                try:
                    activation = json.loads(activation_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise CoordinationError(
                        f"cannot load machine activation: {error}"
                    ) from error
                validate_activation(activation, inventory=inventory)
                print(f"Machine activation valid: {inventory['role_claimed']}")
                print("Worker identity, connected session, and healthy heartbeat: YES")
                print("Claim or lease issued: NO")
                return 0
            if args.coordination_command == "prepare-claim":
                from development_factory.coordination import load_inventory_file

                receipt_path = args.receipt
                if not receipt_path.is_absolute():
                    receipt_path = args.repo_root / receipt_path
                output = args.claim_output
                if not output.is_absolute():
                    output = args.repo_root / output
                queue = load_queue_file(args.repo_root / args.queue)
                inventory = load_inventory_file(receipt_path)
                envelope = prepare_claim_envelope(
                    queue,
                    assignment_id=args.assignment_id,
                    inventory=inventory,
                    completed_assignments=tuple(args.completed_assignments),
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(envelope, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                print(f"Claim envelope prepared: {output}")
                print("Claim state: PREPARED_NOT_CLAIMED")
                return 0
            if args.coordination_command == "daily-report":
                inventory_paths = [
                    path if path.is_absolute() else args.repo_root / path
                    for path in args.inventory_paths
                ]
                activation_paths = [
                    path if path.is_absolute() else args.repo_root / path
                    for path in args.activation_paths
                ]
                latest_report_path = args.latest_report_path
                if (
                    latest_report_path is not None
                    and not latest_report_path.is_absolute()
                ):
                    latest_report_path = args.repo_root / latest_report_path
                output = (
                    args.output
                    if args.output.is_absolute()
                    else args.repo_root / args.output
                )
                report = build_daily_report(
                    args.repo_root,
                    inventory_paths=inventory_paths,
                    activation_paths=activation_paths,
                    active_lanes=args.active_lanes,
                    completed_assignments=args.completed_assignments,
                    latest_report_path=latest_report_path,
                )
                json_path, markdown_path = write_daily_report(report, output)
                print(f"Daily report JSON: {json_path}")
                print(f"Daily report Markdown: {markdown_path}")
                return 0
            queue_path = args.queue
            if not queue_path.is_absolute():
                queue_path = args.repo_root / queue_path
            queue = load_queue_file(queue_path)
            if args.coordination_command == "validate":
                print(
                    f"Coordination queue valid: {len(queue.assignments)} assignments; "
                    f"{len(dependency_layers(queue))} dependency layers."
                )
                return 0
            eligible = eligible_after_activation(
                queue, args.active_lanes, args.completed_assignments
            )
            print(f"Coordination queue status: {queue.status}")
            print(f"Assignments: {len(queue.assignments)}")
            print(
                f"Eligible after supplied activation: {', '.join(eligible) or 'NONE'}"
            )
            return 0
        if args.command == "lia":
            supervisor = LiaSupervisor(args.repo_root)
            if args.lia_command == "review":
                manager = OwnerReviewManager(args.repo_root)
                if args.review_command == "inspect":
                    issues = manager.inspect(args.contract, args.input)
                    for issue in issues:
                        print(f"BLOCKED: {issue}")
                    if not issues:
                        print("Consolidation inputs are ready for owner review.")
                    return int(bool(issues))
                if args.review_command == "consolidate":
                    owner_review, json_path, markdown_path = manager.consolidate(
                        args.contract, args.input
                    )
                    print(f"Owner review state: {owner_review.state_history[-1]}")
                    print(f"JSON owner review: {json_path}")
                    print(f"Markdown owner review: {markdown_path}")
                    return int(bool(owner_review.blockers))
                if args.review_command == "list":
                    for review_id in manager.list(args.contract):
                        print(review_id)
                    return 0
                if args.review_command == "show":
                    print(
                        json.dumps(
                            manager.show(args.contract, args.review_id),
                            indent=2,
                            sort_keys=True,
                        )
                    )
                    return 0
                if args.review_command in {
                    "workers",
                    "conflicts",
                    "validations",
                    "decisions",
                }:
                    print(
                        json.dumps(
                            manager.view_section(
                                args.contract,
                                args.review_id,
                                args.review_command,
                            ),
                            indent=2,
                            sort_keys=True,
                        )
                    )
                    return 0
                if args.review_command == "record-decision":
                    path = manager.record_decision(
                        args.contract, args.review_id, args.decision
                    )
                    print(f"Owner decision recorded: {path}")
                    return 0
                path = manager.cancel(args.contract, args.review_id)
                print(f"Owner review cancellation recorded: {path}")
                return 0
            if args.lia_command == "worker":
                executor = WorkerExecutor(args.repo_root)
                if args.worker_command == "inspect":
                    classification, issues = executor.inspect(
                        args.contract, args.task_id
                    )
                    print(f"Worker workspace: {classification}")
                    for issue in issues:
                        print(f"BLOCKED: {issue}")
                    return int(bool(issues))
                if args.worker_command == "execute":
                    worker_record, json_path, markdown_path = executor.execute(
                        args.contract, args.task_id, args.operations
                    )
                    print(f"Worker state: {worker_record.recommended_worker_state}")
                    print(f"JSON worker record: {json_path}")
                    print(f"Markdown worker record: {markdown_path}")
                    return int(bool(worker_record.blockers))
                if args.worker_command == "validate":
                    results = executor.validate(args.contract, args.task_id)
                    for result in results:
                        print(
                            f"{result.selection}: {result.exit_classification} "
                            f"({result.result})"
                        )
                    return int(any(item.blocks_completion for item in results))
                if args.worker_command in {"show", "record"}:
                    path = executor.show(args.contract, args.task_id)
                    print(path.read_text(encoding="utf-8"))
                    return 0
                if args.worker_command == "diff":
                    print(executor.diff(args.contract, args.task_id), end="")
                    return 0
                path = executor.cancel(args.contract, args.task_id)
                print(f"Worker cancellation recorded: {path}")
                return 0
            if args.lia_command == "workspace":
                workspace_manager = WorkspaceManager(args.repo_root)
                if args.workspace_command == "list":
                    inspections = workspace_manager.list(args.contract)
                    for inspection in inspections:
                        print(
                            f"{inspection.identity.workspace_id}: "
                            f"{inspection.classification} "
                            f"({inspection.identity.workspace_path})"
                        )
                    return int(any(item.requires_owner_review for item in inspections))
                if args.workspace_command == "prepare":
                    metadata, reused = workspace_manager.prepare(
                        args.contract, args.workspace_id
                    )
                    print(
                        f"Workspace {'reused' if reused else 'prepared'}: "
                        f"{metadata.identity.workspace_id}"
                    )
                    print(f"Path: {metadata.identity.workspace_path}")
                    print(f"Branch: {metadata.identity.workspace_branch}")
                    return 0
                if args.workspace_command == "show":
                    metadata = workspace_manager.show(args.contract, args.workspace_id)
                    print(json.dumps(metadata.to_dict(), indent=2, sort_keys=True))
                    return 0
                inspection = workspace_manager.inspect(args.contract, args.workspace_id)
                print(
                    f"Workspace {inspection.identity.workspace_id}: "
                    f"{inspection.classification}"
                )
                print(f"Path: {inspection.identity.workspace_path}")
                print(f"Branch: {inspection.identity.workspace_branch}")
                for issue in inspection.issues:
                    print(f"OWNER REVIEW: {issue}")
                return int(inspection.requires_owner_review)
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
        CoordinationError,
        ManifestError,
        OwnerReviewError,
        ReviewRecordError,
        AgentRoleError,
        LiaContractError,
        TaskContractError,
        WorkflowError,
        WorkspaceError,
        WorkerExecutionError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"Development Factory configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
