from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from development_factory.execution_adapters import (
    ExecutionAdapterError,
    LocalExecutionAdapter,
    WorkerOperation,
    parse_worker_operations,
)
from development_factory.lia_contract import ResourceClaim


def operations_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "execution_id": "EXEC-1",
        "task_id": "TASK-1",
        "workspace_id": "WORKSPACE-1",
        "allowed_action_classes": ["inspection", "mutation", "validation"],
        "operations": [
            {
                "operation_id": "write",
                "operation": "write_text_file",
                "path": "docs/result.md",
                "paths": [],
                "text": "safe\n",
                "expected_text": None,
                "replacement_text": None,
                "resource_type": "documentation",
                "resource_id": "result",
            }
        ],
        "validation_selections": ["architecture"],
        "termination_policy": {
            "maximum_operations": 2,
            "maximum_mutations": 1,
            "maximum_files_inspected": 2,
            "maximum_files_changed": 1,
            "maximum_output_record_bytes": 100000,
            "maximum_validation_selections": 1,
            "execution_timeout_seconds": 30,
        },
        "required_report_fields": ["blockers"],
    }


def operation(kind: str, path: str) -> WorkerOperation:
    return WorkerOperation(
        operation_id="operation",
        operation=kind,  # type: ignore[arg-type]
        path=path,
        paths=(),
        text="content\n",
        expected_text=None,
        replacement_text=None,
        resource_type=None,
        resource_id=None,
    )


def adapter(workspace: Path, *, mutation: bool = True) -> LocalExecutionAdapter:
    return LocalExecutionAdapter(
        workspace,
        approved_patterns=("docs/**",),
        resource_claims=(ResourceClaim("documentation", "result", "exclusive"),),
        mutation_allowed=mutation,
    )


def test_operations_contract_is_strict_and_immutable() -> None:
    parsed = parse_worker_operations(operations_payload())
    assert parsed.operations[0].mutates is True
    assert parsed.termination_policy.maximum_files_changed == 1
    with pytest.raises(AttributeError):
        parsed.execution_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unknown_field", "fields are invalid"),
        ("unsupported_operation", "unsupported operation"),
        ("too_many_operations", "maximum operation count exceeded"),
        ("too_many_mutations", "maximum mutation count exceeded"),
        ("too_many_validations", "maximum validation selection count exceeded"),
    ],
)
def test_invalid_operations_fail_closed(mutation: str, message: str) -> None:
    payload = copy.deepcopy(operations_payload())
    if mutation == "unknown_field":
        payload["unknown"] = True
    elif mutation == "unsupported_operation":
        payload["operations"][0]["operation"] = "shell"
    elif mutation == "too_many_operations":
        payload["operations"].append(copy.deepcopy(payload["operations"][0]))
        payload["operations"][1]["operation_id"] = "second"
        payload["termination_policy"]["maximum_operations"] = 1
    elif mutation == "too_many_mutations":
        payload["operations"].append(copy.deepcopy(payload["operations"][0]))
        payload["operations"][1]["operation_id"] = "second"
    else:
        payload["validation_selections"].append("backend")
    with pytest.raises(ExecutionAdapterError, match=message):
        parse_worker_operations(payload)


def test_inspection_only_adapter_is_structurally_immutable(tmp_path: Path) -> None:
    with pytest.raises(ExecutionAdapterError, match="inspection-only"):
        adapter(tmp_path, mutation=False).execute(
            operation("write_text_file", "docs/result.md")
        )
    assert not (tmp_path / "docs/result.md").exists()


def test_approved_write_inspect_append_and_exact_replace(tmp_path: Path) -> None:
    local = adapter(tmp_path)
    write = local.execute(operation("write_text_file", "docs/result.md"))
    assert write.changed_files == ("docs/result.md",)
    inspect = WorkerOperation(
        "inspect",
        "inspect_file",
        "docs/result.md",
        (),
        None,
        None,
        None,
        None,
        None,
    )
    assert local.execute(inspect).inspected_files == ("docs/result.md",)
    append = operation("append_text_file", "docs/result.md")
    local.execute(append)
    replace = WorkerOperation(
        "replace",
        "replace_exact_text",
        "docs/result.md",
        (),
        None,
        "content\ncontent\n",
        "replaced\n",
        None,
        None,
    )
    local.execute(replace)
    assert (tmp_path / "docs/result.md").read_text() == "replaced\n"


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/escape",
        "../escape",
        "docs/../../escape",
        ".git/config",
        ".development-factory/report.json",
        ".env",
        "secrets/id_rsa",
        "outside.txt",
    ],
)
def test_unsafe_or_out_of_boundary_paths_are_denied(tmp_path: Path, path: str) -> None:
    with pytest.raises(ExecutionAdapterError):
        adapter(tmp_path).execute(operation("write_text_file", path))


def test_symlink_escape_is_denied(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExecutionAdapterError, match="symlink"):
        adapter(tmp_path).execute(operation("write_text_file", "docs/result.md"))


def test_undeclared_resource_is_denied(tmp_path: Path) -> None:
    requested = WorkerOperation(
        "write",
        "write_text_file",
        "docs/result.md",
        (),
        "content",
        None,
        None,
        "documentation",
        "other",
    )
    with pytest.raises(ExecutionAdapterError, match="undeclared resource"):
        adapter(tmp_path).execute(requested)


def test_versioned_examples_match_operations_schema_contract() -> None:
    root = Path(__file__).parents[3]
    schema_path = root / "development-factory/worker-operations.schema.json"
    if not schema_path.exists():
        pytest.skip("repository-root schemas are not mounted in backend container")
    schema = json.loads(schema_path.read_text())
    required = set(schema["required"])
    for name in ("df4b-worker-execution.json", "df4b-worker-operations.json"):
        path = root / "development-factory/examples" / name
        payload = json.loads(path.read_text())
        assert set(payload) == required
        assert parse_worker_operations(payload).schema_version == "1.0"
