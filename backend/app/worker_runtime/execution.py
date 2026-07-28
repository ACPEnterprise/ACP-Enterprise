import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


class IsolatedWorkspaceExecutionError(Exception):
    pass


SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,99}$")
MAX_MANIFEST_BYTES = 32_000
MAX_BOUNDARY = 500


@dataclass(frozen=True)
class AcquiredControlledOffer:
    offer_id: UUID
    lease_id: UUID
    lease_version: int
    workspace_id: str
    command_type: str
    payload: Mapping[str, object]


class IsolatedWorkspaceExecutor:
    """Execute one typed read-only inspection over a confined workspace manifest."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve(strict=True)

    def execute(self, offer: AcquiredControlledOffer) -> dict[str, object]:
        if (
            offer.command_type != "inspect_workspace"
            or SAFE_ID.fullmatch(offer.workspace_id) is None
        ):
            raise IsolatedWorkspaceExecutionError(
                "Controlled command is not allowlisted."
            )
        workspace = self.workspace_root / offer.workspace_id
        if workspace.is_symlink():
            raise IsolatedWorkspaceExecutionError("Workspace symlinks are denied.")
        resolved = workspace.resolve(strict=True)
        if self.workspace_root not in resolved.parents:
            raise IsolatedWorkspaceExecutionError("Workspace escapes its root.")
        manifest_name = offer.payload.get("manifest_name")
        if manifest_name != "workspace-manifest.json":
            raise IsolatedWorkspaceExecutionError("Workspace manifest is invalid.")
        manifest = resolved / manifest_name
        if manifest.is_symlink() or not manifest.is_file():
            raise IsolatedWorkspaceExecutionError("Workspace manifest is unavailable.")
        if manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise IsolatedWorkspaceExecutionError("Workspace manifest is too large.")
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise IsolatedWorkspaceExecutionError(
                "Workspace manifest is malformed."
            ) from error
        if not isinstance(data, dict) or set(data) != {
            "schema_version",
            "workspace_id",
            "repository_key",
            "branch",
            "head",
            "clean",
            "file_boundary",
        }:
            raise IsolatedWorkspaceExecutionError(
                "Workspace manifest shape is invalid."
            )
        boundary = data["file_boundary"]
        if (
            data["schema_version"] != "1"
            or data["workspace_id"] != offer.workspace_id
            or data["repository_key"] != offer.payload.get("repository_key")
            or data["branch"] != offer.payload.get("expected_branch")
            or data["head"] != offer.payload.get("expected_head")
            or not SHA.fullmatch(str(data["head"]))
            or data["clean"] is not True
            or not isinstance(boundary, list)
            or len(boundary) > MAX_BOUNDARY
            or any(
                not isinstance(path, str) or not _safe_relative_path(path)
                for path in boundary
            )
            or boundary != sorted(set(boundary))
        ):
            raise IsolatedWorkspaceExecutionError(
                "Workspace evidence does not match the approved offer."
            )
        return {
            "workspace_id": offer.workspace_id,
            "repository_key": data["repository_key"],
            "branch": data["branch"],
            "head": data["head"],
            "clean": True,
            "file_count": len(boundary),
            "file_boundary": tuple(sorted(boundary)),
            "repository_mutated": False,
        }


def _safe_relative_path(value: str) -> bool:
    parts = value.split("/")
    return (
        bool(value)
        and not value.startswith("/")
        and all(part not in {"", ".", "..", ".git"} for part in parts)
    )
