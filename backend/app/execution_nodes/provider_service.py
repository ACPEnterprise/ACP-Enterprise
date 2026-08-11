import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .contracts import ProviderBoundary, ProviderExecutionRequest
from .provider import CodexImplementation, ControlledExecutionProvider, ProviderJournal
from .workspaces import WorkspaceManager


class BoundaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_repository: str
    allowed_branch: str
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    permitted_operations: tuple[str, ...]
    validation_requirements: tuple[str, ...]


class ExecutionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: UUID
    node_id: UUID
    command_id: UUID
    execution_id: UUID
    lease_id: UUID
    workspace_id: str
    instruction: str
    instruction_digest: str
    request_digest: str
    boundary_digest: str
    boundary: BoundaryPayload
    commit_subject: str


def create_app() -> FastAPI:
    token_path = Path(os.environ["ACP_PROVIDER_TOKEN_FILE"]).resolve(strict=True)
    if token_path.stat().st_mode & 0o077:
        raise RuntimeError(
            "Provider token file must not be accessible by group or other users."
        )
    token = token_path.read_bytes().strip()
    repositories = json.loads(
        Path(os.environ["ACP_PROVIDER_REPOSITORIES_FILE"]).read_text()
    )
    journal = ProviderJournal(Path(os.environ["ACP_PROVIDER_STATE_ROOT"]))
    provider = ControlledExecutionProvider(
        WorkspaceManager(
            Path(os.environ["ACP_PROVIDER_WORKSPACE_ROOT"]),
            {key: Path(value) for key, value in repositories.items()},
        ),
        journal,
        CodexImplementation(
            Path(os.environ["ACP_PROVIDER_CODEX_EXECUTABLE"]),
            Path(os.environ["ACP_PROVIDER_CODEX_HOME"]),
            Path(os.environ["ACP_PROVIDER_EVIDENCE_ROOT"]),
        ),
    )
    app = FastAPI(
        title="ACP Controlled Execution Provider",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "healthy",
            "provider": "controlled-code-execution",
            "repositories": sorted(repositories),
        }

    @app.post("/execute")
    def execute(
        payload: ExecutionPayload,
        signature: Annotated[str, Header(alias="X-ACP-Provider-Signature")],
    ) -> dict[str, object]:
        canonical = json.dumps(
            payload.model_dump(mode="json", exclude_none=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        expected = hmac.new(token, canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(
                status_code=401, detail="Provider request authentication failed."
            )
        boundary = ProviderBoundary(**payload.boundary.model_dump())
        request = ProviderExecutionRequest(
            **payload.model_dump(exclude={"boundary"}), boundary=boundary
        )
        result = provider.execute(request)
        return {
            "execution_id": str(result.execution_id),
            "lease_id": str(result.lease_id),
            "phase": result.phase.value,
            "starting_head": result.starting_head,
            "result_head": result.result_head,
            "commit_sha": result.commit_sha,
            "files_changed": result.files_changed,
            "validation": result.validation,
            "evidence": result.evidence,
        }

    @app.get("/executions/{execution_id}/status")
    def execution_status(
        execution_id: UUID,
        signature: Annotated[str, Header(alias="X-ACP-Provider-Signature")],
    ) -> dict[str, object]:
        canonical = str(execution_id).encode()
        expected = hmac.new(token, canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(
                status_code=401, detail="Provider request authentication failed."
            )
        record = journal.latest_record_for_execution(execution_id)
        if not record:
            raise HTTPException(status_code=404, detail="Execution status unavailable.")
        return record

    return app


app = create_app()
