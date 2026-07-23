from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

from development_factory.lia_contract import ResourceClaim
from development_factory.reports import redact


OPERATIONS_VERSION = "1.0"
OperationKind = Literal[
    "inspect_file",
    "inspect_paths",
    "write_text_file",
    "append_text_file",
    "replace_exact_text",
    "create_demonstration_file",
]
MUTATION_OPERATIONS = frozenset(
    {
        "write_text_file",
        "append_text_file",
        "replace_exact_text",
        "create_demonstration_file",
    }
)


class ExecutionAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class TerminationPolicy:
    maximum_operations: int
    maximum_mutations: int
    maximum_files_inspected: int
    maximum_files_changed: int
    maximum_output_record_bytes: int
    maximum_validation_selections: int
    execution_timeout_seconds: int


@dataclass(frozen=True)
class WorkerOperation:
    operation_id: str
    operation: OperationKind
    path: str | None
    paths: tuple[str, ...]
    text: str | None
    expected_text: str | None
    replacement_text: str | None
    resource_type: str | None
    resource_id: str | None

    @property
    def mutates(self) -> bool:
        return self.operation in MUTATION_OPERATIONS


@dataclass(frozen=True)
class WorkerOperations:
    schema_version: str
    execution_id: str
    task_id: str
    workspace_id: str
    allowed_action_classes: tuple[str, ...]
    operations: tuple[WorkerOperation, ...]
    validation_selections: tuple[str, ...]
    termination_policy: TerminationPolicy
    required_report_fields: tuple[str, ...]


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    operation: OperationKind
    status: Literal["performed", "denied"]
    summary: str
    inspected_files: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()


class ExecutionAdapter(Protocol):
    def execute(self, operation: WorkerOperation) -> OperationResult: ...


def load_worker_operations(path: Path) -> WorkerOperations:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionAdapterError(f"unable to load worker operations: {exc}") from exc
    return parse_worker_operations(payload)


def parse_worker_operations(payload: object) -> WorkerOperations:
    value = _object(payload, "worker operations")
    expected = {
        "schema_version",
        "execution_id",
        "task_id",
        "workspace_id",
        "allowed_action_classes",
        "operations",
        "validation_selections",
        "termination_policy",
        "required_report_fields",
    }
    _exact(value, expected, "worker operations")
    if value["schema_version"] != OPERATIONS_VERSION:
        raise ExecutionAdapterError(
            f"worker operations schema_version must be {OPERATIONS_VERSION}"
        )
    raw_operations = value["operations"]
    if not isinstance(raw_operations, list):
        raise ExecutionAdapterError("operations must be an array")
    operations = tuple(_parse_operation(item) for item in raw_operations)
    operation_ids = [item.operation_id for item in operations]
    if len(operation_ids) != len(set(operation_ids)):
        raise ExecutionAdapterError("operation IDs must be unique")
    actions = _strings(value["allowed_action_classes"], "allowed_action_classes")
    if not set(actions) <= {"inspection", "mutation", "validation"}:
        raise ExecutionAdapterError("allowed_action_classes contains an unknown value")
    policy_value = _object(value["termination_policy"], "termination_policy")
    policy_fields = {
        "maximum_operations",
        "maximum_mutations",
        "maximum_files_inspected",
        "maximum_files_changed",
        "maximum_output_record_bytes",
        "maximum_validation_selections",
        "execution_timeout_seconds",
    }
    _exact(policy_value, policy_fields, "termination_policy")
    policy_numbers = {
        field: _positive_integer(policy_value[field], field) for field in policy_fields
    }
    policy = TerminationPolicy(**policy_numbers)
    if len(operations) > policy.maximum_operations:
        raise ExecutionAdapterError("maximum operation count exceeded")
    if sum(item.mutates for item in operations) > policy.maximum_mutations:
        raise ExecutionAdapterError("maximum mutation count exceeded")
    validation = _strings(
        value["validation_selections"],
        "validation_selections",
        allow_empty=True,
    )
    if len(validation) > policy.maximum_validation_selections:
        raise ExecutionAdapterError("maximum validation selection count exceeded")
    return WorkerOperations(
        schema_version=OPERATIONS_VERSION,
        execution_id=_nonblank(value["execution_id"], "execution_id"),
        task_id=_nonblank(value["task_id"], "task_id"),
        workspace_id=_nonblank(value["workspace_id"], "workspace_id"),
        allowed_action_classes=actions,
        operations=operations,
        validation_selections=validation,
        termination_policy=policy,
        required_report_fields=_strings(
            value["required_report_fields"], "required_report_fields"
        ),
    )


class LocalExecutionAdapter:
    def __init__(
        self,
        workspace: Path,
        *,
        approved_patterns: tuple[str, ...],
        resource_claims: tuple[ResourceClaim, ...],
        mutation_allowed: bool,
    ) -> None:
        self.workspace = workspace.resolve()
        self.approved_patterns = approved_patterns
        self.resource_claims = resource_claims
        self.mutation_allowed = mutation_allowed

    def execute(self, operation: WorkerOperation) -> OperationResult:
        if operation.mutates and not self.mutation_allowed:
            raise ExecutionAdapterError("inspection-only worker cannot mutate files")
        self._verify_resource(operation)
        if operation.operation == "inspect_paths":
            paths = tuple(self._normalize(path) for path in operation.paths)
            summaries = tuple(
                path.relative_to(self.workspace).as_posix() for path in paths
            )
            return OperationResult(
                operation.operation_id,
                operation.operation,
                "performed",
                f"inspected {len(paths)} approved paths",
                inspected_files=summaries,
            )
        if operation.path is None:
            raise ExecutionAdapterError(f"{operation.operation} requires path")
        target = self._normalize(operation.path)
        relative = target.relative_to(self.workspace).as_posix()
        if operation.operation == "inspect_file":
            if not target.is_file():
                raise ExecutionAdapterError(
                    f"inspection target is not a file: {relative}"
                )
            content = target.read_text(encoding="utf-8")
            return OperationResult(
                operation.operation_id,
                operation.operation,
                "performed",
                redact(f"inspected {relative} ({len(content)} characters)"),
                inspected_files=(relative,),
            )
        if operation.operation == "create_demonstration_file":
            if target.exists():
                raise ExecutionAdapterError(
                    f"demonstration target already exists: {relative}"
                )
            self._write(target, operation.text or "", append=False)
        elif operation.operation == "write_text_file":
            self._write(target, operation.text or "", append=False)
        elif operation.operation == "append_text_file":
            if not target.is_file():
                raise ExecutionAdapterError(f"append target is not a file: {relative}")
            self._write(target, operation.text or "", append=True)
        elif operation.operation == "replace_exact_text":
            if not target.is_file():
                raise ExecutionAdapterError(f"replace target is not a file: {relative}")
            current = target.read_text(encoding="utf-8")
            expected = operation.expected_text or ""
            if current.count(expected) != 1:
                raise ExecutionAdapterError(
                    "replace_exact_text requires exactly one expected-text match"
                )
            target.write_text(
                current.replace(expected, operation.replacement_text or "", 1),
                encoding="utf-8",
            )
        else:
            raise ExecutionAdapterError(f"unsupported operation: {operation.operation}")
        return OperationResult(
            operation.operation_id,
            operation.operation,
            "performed",
            f"changed approved file {relative}",
            changed_files=(relative,),
        )

    def _normalize(self, raw_path: str) -> Path:
        if not raw_path or "\\" in raw_path:
            raise ExecutionAdapterError("target path must use a relative POSIX path")
        pure = PurePosixPath(raw_path)
        if pure.is_absolute() or ".." in pure.parts:
            raise ExecutionAdapterError(
                "absolute paths and parent traversal are denied"
            )
        if not pure.parts or pure.parts[0] in {".git", ".development-factory"}:
            raise ExecutionAdapterError("Development Factory and Git paths are denied")
        if pure.name.startswith(".env") or pure.name in {
            "id_rsa",
            "id_ed25519",
            "credentials",
        }:
            raise ExecutionAdapterError("secret and environment paths are denied")
        candidate = self.workspace.joinpath(*pure.parts)
        parent = candidate.parent
        while parent != self.workspace:
            if parent.is_symlink():
                raise ExecutionAdapterError("symlink path components are denied")
            parent = parent.parent
        if candidate.is_symlink():
            raise ExecutionAdapterError("symlink targets are denied")
        resolved_parent = candidate.parent.resolve()
        if (
            self.workspace != resolved_parent
            and self.workspace not in resolved_parent.parents
        ):
            raise ExecutionAdapterError("target path escapes the workspace")
        relative = pure.as_posix()
        if not any(
            fnmatch.fnmatchcase(relative, pattern) for pattern in self.approved_patterns
        ):
            raise ExecutionAdapterError(
                f"target lies outside approved file boundaries: {relative}"
            )
        return candidate

    def _verify_resource(self, operation: WorkerOperation) -> None:
        if operation.resource_type is None and operation.resource_id is None:
            return
        if operation.resource_type is None or operation.resource_id is None:
            raise ExecutionAdapterError(
                "resource type and ID must be supplied together"
            )
        if not any(
            claim.resource_type == operation.resource_type
            and claim.resource_id == operation.resource_id
            for claim in self.resource_claims
        ):
            raise ExecutionAdapterError("operation requests an undeclared resource")

    @staticmethod
    def _write(path: Path, text: str, *, append: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(text)
        else:
            path.write_text(text, encoding="utf-8")


def _parse_operation(value: object) -> WorkerOperation:
    payload = _object(value, "operation")
    expected = {
        "operation_id",
        "operation",
        "path",
        "paths",
        "text",
        "expected_text",
        "replacement_text",
        "resource_type",
        "resource_id",
    }
    _exact(payload, expected, "operation")
    kind = payload["operation"]
    supported = {
        "inspect_file",
        "inspect_paths",
        "write_text_file",
        "append_text_file",
        "replace_exact_text",
        "create_demonstration_file",
    }
    if kind not in supported:
        raise ExecutionAdapterError(f"unsupported operation: {kind}")
    optional_strings = {}
    for field in (
        "path",
        "text",
        "expected_text",
        "replacement_text",
        "resource_type",
        "resource_id",
    ):
        item = payload[field]
        if item is not None and not isinstance(item, str):
            raise ExecutionAdapterError(f"{field} must be a string or null")
        optional_strings[field] = item
    paths = _strings(payload["paths"], "paths", allow_empty=True)
    if kind == "inspect_paths" and not paths:
        raise ExecutionAdapterError("inspect_paths requires at least one path")
    if kind != "inspect_paths" and optional_strings["path"] is None:
        raise ExecutionAdapterError(f"{kind} requires path")
    if kind in MUTATION_OPERATIONS and kind != "replace_exact_text":
        if optional_strings["text"] is None:
            raise ExecutionAdapterError(f"{kind} requires text")
    if kind == "replace_exact_text" and (
        optional_strings["expected_text"] is None
        or optional_strings["replacement_text"] is None
    ):
        raise ExecutionAdapterError(
            "replace_exact_text requires expected_text and replacement_text"
        )
    return WorkerOperation(
        operation_id=_nonblank(payload["operation_id"], "operation_id"),
        operation=kind,
        paths=paths,
        **optional_strings,
    )


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionAdapterError(f"{field} must be an object")
    return value


def _exact(value: dict[str, Any], expected: set[str], field: str) -> None:
    if value.keys() != expected:
        raise ExecutionAdapterError(f"{field} fields are invalid")


def _strings(
    value: object, field: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ExecutionAdapterError(f"{field} must be a string array")
    result = tuple(item.strip() for item in value)
    if not allow_empty and not result:
        raise ExecutionAdapterError(f"{field} cannot be empty")
    if len(result) != len(set(result)):
        raise ExecutionAdapterError(f"{field} cannot contain duplicates")
    return result


def _nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionAdapterError(f"{field} must be nonblank")
    return value.strip()


def _positive_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ExecutionAdapterError(f"{field} must be a positive integer")
    return value
