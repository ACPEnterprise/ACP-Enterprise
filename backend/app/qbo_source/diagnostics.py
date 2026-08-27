from __future__ import annotations

import json
import os
import stat
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4


class OAuthDiagnosticStage(str, Enum):
    CALLBACK_REACHED = "CALLBACK_REACHED"
    STATE_VALIDATED = "STATE_VALIDATED"
    STATE_EXPIRED = "STATE_EXPIRED"
    STATE_INVALID = "STATE_INVALID"
    STATE_REPLAYED = "STATE_REPLAYED"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    TOKEN_EXCHANGE_STARTED = "TOKEN_EXCHANGE_STARTED"
    TOKEN_EXCHANGE_SUCCEEDED = "TOKEN_EXCHANGE_SUCCEEDED"
    TOKEN_EXCHANGE_FAILED = "TOKEN_EXCHANGE_FAILED"
    TOKEN_PERSISTENCE_FAILED = "TOKEN_PERSISTENCE_FAILED"
    TOKEN_PERSISTED_TEMPORARILY = "TOKEN_PERSISTED_TEMPORARILY"
    COMPANYINFO_REQUEST_STARTED = "COMPANYINFO_REQUEST_STARTED"
    COMPANYINFO_TRANSPORT_FAILED = "COMPANYINFO_TRANSPORT_FAILED"
    COMPANYINFO_PROVIDER_REJECTED = "COMPANYINFO_PROVIDER_REJECTED"
    COMPANYINFO_RESPONSE_MALFORMED = "COMPANYINFO_RESPONSE_MALFORMED"
    REALM_MISMATCH = "REALM_MISMATCH"
    COMPANY_NAME_MISMATCH = "COMPANY_NAME_MISMATCH"
    TOKEN_CLEANUP_SUCCEEDED = "TOKEN_CLEANUP_SUCCEEDED"
    TOKEN_CLEANUP_FAILED = "TOKEN_CLEANUP_FAILED"
    VERIFICATION_SUCCEEDED = "VERIFICATION_SUCCEEDED"
    CONNECTION_COMMITTED = "CONNECTION_COMMITTED"
    CONNECTION_FAILED = "CONNECTION_FAILED"


class ProtectedOAuthDiagnosticJournal:
    """Append-only, sanitized OAuth attempt evidence outside the repository."""

    def __init__(self, root: Path, *, repository_root: Path) -> None:
        self.root = root.expanduser().resolve()
        repository = repository_root.expanduser().resolve()
        if self.root == repository or repository in self.root.parents:
            raise ValueError("OAuth diagnostic root must remain outside Git")
        if self.root.exists() and stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            raise ValueError("OAuth diagnostic root permissions are too open")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.root, 0o700)

    def record(
        self,
        attempt_id: str,
        stage: OAuthDiagnosticStage,
        *,
        provider_status: int | None = None,
        failure_classification: str | None = None,
    ) -> None:
        if len(attempt_id) != 64 or any(
            c not in "0123456789abcdef" for c in attempt_id
        ):
            raise ValueError("opaque OAuth attempt identity required")
        attempt_root = self.root / attempt_id
        attempt_root.mkdir(mode=0o700, exist_ok=True)
        os.chmod(attempt_root, 0o700)
        document: dict[str, object] = {
            "schema_version": "qbo-sandbox-oauth-diagnostic/v1",
            "attempt_id": attempt_id,
            "environment": "sandbox",
            "stage": stage.value,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if provider_status is not None:
            document["provider_http_status"] = provider_status
        if failure_classification is not None:
            if not failure_classification.replace("_", "").isalnum():
                raise ValueError("sanitized failure classification required")
            document["failure_classification"] = failure_classification
        path = attempt_root / f"{time.time_ns()}-{uuid4().hex}.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(
                json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
            )
            target.flush()
            os.fsync(target.fileno())

    def has_attempt(self, attempt_id: str) -> bool:
        return (self.root / attempt_id).is_dir()
