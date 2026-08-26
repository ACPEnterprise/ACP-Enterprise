from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .intuit import (
    AuthorizationStateStore,
    IntuitAuthenticationError,
    IntuitEnvironment,
    OAuthAuthorizationCoordinator,
    PendingAuthorization,
)

CALLBACK_PATH = "/api/v1/integrations/qbo/oauth/callback"


def exact_callback_uri(origin: str) -> str:
    parsed = urlparse(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or "*" in origin
    ):
        raise ValueError("exact HTTPS callback origin without wildcard is required")
    return origin.rstrip("/") + CALLBACK_PATH


class ProtectedAuthorizationStateStore(AuthorizationStateStore):
    """Restricted short-lived OAuth state store; state is atomically single-use."""

    def __init__(self, root: Path, *, repository_root: Path) -> None:
        self.root = root.expanduser().resolve()
        repository = repository_root.expanduser().resolve()
        if self.root == repository or repository in self.root.parents:
            raise ValueError("OAuth state root must remain outside Git")
        if self.root.exists():
            if stat.S_IMODE(self.root.stat().st_mode) & 0o077:
                raise ValueError("OAuth state root permissions are too open")
        else:
            self.root.mkdir(parents=True, mode=0o700)
        os.chmod(self.root, 0o700)

    async def put(self, pending: PendingAuthorization) -> None:
        path = self._path(pending.state)
        document = {
            **asdict(pending),
            "environment": pending.environment.value,
            "expires_at": pending.expires_at.isoformat(),
        }
        content = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())

    async def consume(self, state: str) -> PendingAuthorization | None:
        path = self._path(state)
        claimed = path.with_suffix(".claimed")
        try:
            os.replace(path, claimed)
        except FileNotFoundError:
            return None
        try:
            document = json.loads(claimed.read_bytes())
            return PendingAuthorization(
                state=str(document["state"]),
                environment=IntuitEnvironment(str(document["environment"])),
                redirect_uri=str(document["redirect_uri"]),
                token_reference=str(document["token_reference"]),
                expires_at=datetime.fromisoformat(str(document["expires_at"])),
            )
        finally:
            claimed.unlink(missing_ok=True)

    def _path(self, state: str) -> Path:
        if len(state) < 32:
            raise ValueError("valid OAuth state is required")
        return self.root / f"{hashlib.sha256(state.encode()).hexdigest()}.json"


class OAuthCallbackHandler:
    """Framework-neutral callback handler; callers must not log its arguments."""

    def __init__(self, coordinator: OAuthAuthorizationCoordinator) -> None:
        self.coordinator = coordinator

    async def handle(
        self,
        *,
        code: str | None,
        state: str | None,
        realm_id: str | None,
        provider_error: str | None = None,
    ) -> str:
        if provider_error:
            raise IntuitAuthenticationError("oauth_provider_rejected")
        if not code or not state or not realm_id:
            raise IntuitAuthenticationError("oauth_callback_incomplete")
        authorized = await self.coordinator.complete(
            code=code, state=state, realm_id=realm_id
        )
        return authorized.realm_id
