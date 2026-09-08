"""Renew short-lived factory access without persisting bearer access tokens."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


class FactoryCredentialError(RuntimeError):
    """A deliberately secret-free credential failure."""


@dataclass(frozen=True)
class RenewedFactoryAccess:
    access_token: str
    access_token_expires_at: datetime


class FactoryRefreshCredential:
    """Mode-0600 rotating refresh credential for a bounded delegation.

    The refresh token is replaced atomically after every successful rotation. Access
    tokens exist only in memory and this object never includes credential material in
    errors or logging.
    """

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def _read_document(self) -> dict[str, Any]:
        try:
            if self.path.is_symlink():
                raise FactoryCredentialError(
                    "factory refresh credential must not be a symbolic link"
                )
            path = self.path.resolve(strict=True)
            metadata = path.stat()
        except FactoryCredentialError:
            raise
        except OSError as error:
            raise FactoryCredentialError(
                "factory refresh credential is unavailable"
            ) from error
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise FactoryCredentialError(
                "factory refresh credential must be a regular mode-0600 file"
            )
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise FactoryCredentialError(
                "factory refresh credential is invalid"
            ) from error
        if not isinstance(document, dict):
            raise FactoryCredentialError("factory refresh credential is invalid")
        return document

    def _replace(self, refresh_token: str) -> None:
        if self.path.is_symlink():
            raise FactoryCredentialError(
                "factory refresh credential must not be a symbolic link"
            )
        destination = self.path.resolve(strict=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    {"refresh_token": refresh_token}, stream, separators=(",", ":")
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    async def renew(
        self,
        *,
        control_api_url: str,
        delegation_expires_at: datetime,
        now: datetime | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> RenewedFactoryAccess:
        current_time = now or datetime.now(timezone.utc)
        if delegation_expires_at.tzinfo is None:
            raise FactoryCredentialError("delegation expiry must include a timezone")
        if current_time >= delegation_expires_at:
            raise FactoryCredentialError("delegation is expired; access renewal denied")
        document = self._read_document()
        refresh_token = document.get("refresh_token")
        if not isinstance(refresh_token, str) or len(refresh_token) < 32:
            raise FactoryCredentialError("factory refresh credential is invalid")
        try:
            async with httpx.AsyncClient(
                base_url=control_api_url.rstrip("/"),
                transport=transport,
                timeout=15.0,
            ) as client:
                response = await client.post(
                    "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
                )
            if response.status_code != 200:
                raise FactoryCredentialError("factory access renewal was denied")
            payload = response.json()
            access_token = payload["access_token"]
            rotated_refresh_token = payload["refresh_token"]
            access_expires_at = datetime.fromisoformat(
                str(payload["access_token_expires_at"]).replace("Z", "+00:00")
            )
            if (
                not isinstance(access_token, str)
                or not access_token
                or not isinstance(rotated_refresh_token, str)
                or len(rotated_refresh_token) < 32
                or access_expires_at.tzinfo is None
            ):
                raise ValueError
        except FactoryCredentialError:
            raise
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise FactoryCredentialError("factory access renewal failed") from error
        self._replace(rotated_refresh_token)
        return RenewedFactoryAccess(access_token, access_expires_at)
