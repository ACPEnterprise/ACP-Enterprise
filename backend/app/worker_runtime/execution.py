import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx


class IsolatedWorkspaceExecutionError(Exception):
    pass


class AmbiguousProviderExecutionError(Exception):
    """Provider outcome is unknown and must never be converted into a retry."""


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


class NodeExecutionProviderClient:
    """Forwards a leased immutable contract to the node-local provider only."""

    def __init__(
        self, base_url: str, token_file: Path, timeout_seconds: int = 7300
    ) -> None:
        stat = token_file.stat()
        if stat.st_mode & 0o077:
            raise PermissionError("Provider token permissions must be 600.")
        self.base_url = base_url.rstrip("/")
        self.token = token_file.read_bytes().strip()
        self.timeout_seconds = timeout_seconds

    async def execute(self, offer: AcquiredControlledOffer) -> dict[str, object]:
        if offer.command_type != "execute_code":
            raise IsolatedWorkspaceExecutionError("Provider command type is invalid.")
        required = {
            "node_id",
            "command_id",
            "execution_id",
            "instruction",
            "instruction_digest",
            "request_digest",
            "boundary",
            "boundary_digest",
            "commit_subject",
        }
        if not required <= set(offer.payload):
            raise IsolatedWorkspaceExecutionError("Provider contract is incomplete.")
        payload = {
            "company_id": str(offer.payload["company_id"]),
            "node_id": str(offer.payload["node_id"]),
            "command_id": str(offer.payload["command_id"]),
            "execution_id": str(offer.payload["execution_id"]),
            "lease_id": str(offer.lease_id),
            "workspace_id": offer.workspace_id,
            "instruction": offer.payload["instruction"],
            "instruction_digest": offer.payload["instruction_digest"],
            "request_digest": offer.payload["request_digest"],
            "boundary_digest": offer.payload["boundary_digest"],
            "boundary": offer.payload["boundary"],
            "commit_subject": offer.payload["commit_subject"],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(self.token, canonical, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout_seconds
        ) as client:
            response = await client.post(
                "/execute",
                content=canonical,
                headers={
                    "Content-Type": "application/json",
                    "X-ACP-Provider-Signature": signature,
                },
            )
        if response.status_code != 200:
            raise AmbiguousProviderExecutionError(
                "Node Execution Provider rejected work."
            )
        result = response.json()
        return {
            "workspace_id": offer.workspace_id,
            "repository_key": offer.payload["repository_key"],
            "branch": offer.payload["expected_branch"],
            "head": result["result_head"],
            "starting_head": result["starting_head"],
            "commit_sha": result["commit_sha"],
            "clean": True,
            "file_count": len(result["files_changed"]),
            "file_boundary": result["files_changed"],
            "validation": result["validation"],
            "evidence": result["evidence"],
            "repository_mutated": True,
        }


def _safe_relative_path(value: str) -> bool:
    parts = value.split("/")
    return (
        bool(value)
        and not value.startswith("/")
        and all(part not in {"", ".", "..", ".git"} for part in parts)
    )
