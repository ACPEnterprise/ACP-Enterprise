from __future__ import annotations

import asyncio
import fcntl
import json
import os
import stat
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from .intuit import (
    ACCOUNTING_SCOPE,
    ClientCredential,
    OAuthToken,
    SecretProvider,
)


class SandboxSecretStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ProtectedSandboxSecretProvider(SecretProvider):
    """Sandbox-only filesystem secret provider on an owner-restricted volume."""

    CLIENT_REFERENCE = "qbo-sandbox/client"
    TOKEN_REFERENCE = "qbo-sandbox/token"

    def __init__(self, *, root: Path, repository_root: Path) -> None:
        self.root = root.expanduser().resolve()
        repository = repository_root.expanduser().resolve()
        if self.root == repository or repository in self.root.parents:
            raise SandboxSecretStoreError("sandbox_secret_root_inside_repository")
        if self.root.exists() and stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            raise SandboxSecretStoreError("sandbox_secret_root_permissions_too_open")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._lock_path = self.root / ".token.lock"
        self._ensure_lock_file()

    async def get_client_credential(self, reference: str) -> ClientCredential:
        self._require_reference(reference, self.CLIENT_REFERENCE)
        return await asyncio.to_thread(self._read_client)

    async def get_token(self, reference: str) -> OAuthToken:
        self._require_reference(reference, self.TOKEN_REFERENCE)
        return await asyncio.to_thread(self._read_token)

    async def put_token(
        self, reference: str, token: OAuthToken, *, expected_generation: int | None
    ) -> None:
        self._require_reference(reference, self.TOKEN_REFERENCE)
        await asyncio.to_thread(self._put_token, token, expected_generation)

    async def delete_token(self, reference: str) -> None:
        self._require_reference(reference, self.TOKEN_REFERENCE)
        await asyncio.to_thread(self._delete_token)

    @property
    def client_path(self) -> Path:
        return self.root / "development-client.json"

    @property
    def token_path(self) -> Path:
        return self.root / "sandbox-token.json"

    def _read_client(self) -> ClientCredential:
        document = self._read_document(
            self.client_path, "sandbox_client_not_configured"
        )
        if document.get("environment") != "sandbox":
            raise SandboxSecretStoreError("sandbox_client_environment_invalid")
        client_id = document.get("client_id")
        client_secret = document.get("client_secret")
        if not isinstance(client_id, str) or not isinstance(client_secret, str):
            raise SandboxSecretStoreError("sandbox_client_material_invalid")
        if not client_id or not client_secret:
            raise SandboxSecretStoreError("sandbox_client_material_invalid")
        return ClientCredential(client_id=client_id, client_secret=client_secret)

    def _read_token(self) -> OAuthToken:
        with self._locked():
            document = self._read_document(
                self.token_path, "sandbox_token_not_configured"
            )
            return self._token_from_document(document)

    def _put_token(self, token: OAuthToken, expected_generation: int | None) -> None:
        if token.scope != ACCOUNTING_SCOPE:
            raise SandboxSecretStoreError("sandbox_token_scope_invalid")
        with self._locked():
            if expected_generation is None:
                if self.token_path.exists():
                    raise SandboxSecretStoreError("sandbox_token_already_exists")
            else:
                current = self._read_document(
                    self.token_path, "sandbox_token_generation_conflict"
                )
                if current.get("generation") != expected_generation:
                    raise SandboxSecretStoreError("sandbox_token_generation_conflict")
            document = {
                "schema_version": "qbo-sandbox-token/v1",
                "environment": "sandbox",
                "access_token": token.access_token,
                "refresh_token": token.refresh_token,
                "access_expires_at": token.access_expires_at.isoformat(),
                "refresh_expires_at": (
                    token.refresh_expires_at.isoformat()
                    if token.refresh_expires_at
                    else None
                ),
                "scope": token.scope,
                "generation": token.generation,
                "realm_id": token.realm_id,
            }
            self._atomic_write(self.token_path, document)

    def _delete_token(self) -> None:
        with self._locked():
            try:
                self.token_path.unlink()
            except FileNotFoundError:
                return

    def _token_from_document(self, document: dict[str, object]) -> OAuthToken:
        try:
            if document["environment"] != "sandbox":
                raise ValueError
            access_expires_at = datetime.fromisoformat(
                str(document["access_expires_at"])
            )
            refresh_value = document.get("refresh_expires_at")
            token = OAuthToken(
                access_token=str(document["access_token"]),
                refresh_token=str(document["refresh_token"]),
                access_expires_at=access_expires_at,
                refresh_expires_at=(
                    datetime.fromisoformat(str(refresh_value))
                    if refresh_value is not None
                    else None
                ),
                scope=str(document["scope"]),
                generation=int(str(document["generation"])),
                realm_id=(
                    str(document["realm_id"])
                    if document.get("realm_id") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SandboxSecretStoreError("sandbox_token_material_invalid") from error
        return token

    def _read_document(self, path: Path, missing_code: str) -> dict[str, object]:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & 0o077:
                raise SandboxSecretStoreError(
                    "sandbox_secret_file_permissions_too_open"
                )
            value = json.loads(path.read_bytes())
        except FileNotFoundError as error:
            raise SandboxSecretStoreError(missing_code) from error
        except json.JSONDecodeError as error:
            raise SandboxSecretStoreError("sandbox_secret_document_invalid") from error
        if not isinstance(value, dict):
            raise SandboxSecretStoreError("sandbox_secret_document_invalid")
        return value

    def _atomic_write(self, path: Path, document: Mapping[str, object]) -> None:
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(
                    json.dumps(
                        document,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                )
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)

    def _ensure_lock_file(self) -> None:
        descriptor = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        os.close(descriptor)
        os.chmod(self._lock_path, 0o600)

    def _locked(self) -> _FileLock:
        return _FileLock(self._lock_path)

    @staticmethod
    def _require_reference(actual: str, expected: str) -> None:
        if actual != expected:
            raise SandboxSecretStoreError("sandbox_secret_reference_rejected")


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._descriptor: int | None = None

    def __enter__(self) -> None:
        self._descriptor = os.open(self.path, os.O_RDWR)
        fcntl.flock(self._descriptor, fcntl.LOCK_EX)

    def __exit__(self, *args: object) -> None:
        if self._descriptor is not None:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            os.close(self._descriptor)
            self._descriptor = None
