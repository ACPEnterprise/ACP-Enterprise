from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path


class SecretProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SecretMaterial:
    values: dict[str, str] = field(repr=False)
    generation: int


class ProtectedSecretProvider:
    """Workload-only protected-volume custody with atomic CAS rotation."""

    def __init__(self, *, root: Path, repository_root: Path, environment: str) -> None:
        self.root = root.expanduser().resolve()
        repository = repository_root.expanduser().resolve()
        if self.root == repository or repository in self.root.parents:
            raise SecretProviderError("secret_root_inside_repository")
        if self.root.exists() and stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            raise SecretProviderError("secret_root_permissions_too_open")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.environment = environment
        self._lock = self.root / ".custody.lock"
        descriptor = os.open(self._lock, os.O_RDWR | os.O_CREAT, 0o600)
        os.close(descriptor)
        os.chmod(self._lock, 0o600)

    def read(self, reference: str) -> SecretMaterial:
        path = self._path(reference)
        with self._locked():
            document = self._read_document(path)
        values = document.get("values")
        generation = document.get("generation")
        if not isinstance(values, dict) or not isinstance(generation, int):
            raise SecretProviderError("secret_material_invalid")
        if not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in values.items()
        ):
            raise SecretProviderError("secret_material_invalid")
        return SecretMaterial(values=values, generation=generation)

    def write(
        self,
        reference: str,
        values: dict[str, str],
        *,
        expected_generation: int | None,
    ) -> SecretMaterial:
        if not values or any(not key or not value for key, value in values.items()):
            raise SecretProviderError("secret_material_invalid")
        path = self._path(reference)
        with self._locked():
            current_generation = None
            if path.exists():
                current = self._read_document(path)
                current_generation = current.get("generation")
            if current_generation != expected_generation:
                raise SecretProviderError("secret_generation_conflict")
            generation = (expected_generation or 0) + 1
            self._atomic_write(
                path,
                {
                    "schema_version": "platform-protected-secret/v1",
                    "environment": self.environment,
                    "generation": generation,
                    "values": values,
                },
            )
        return SecretMaterial(values=values, generation=generation)

    def revoke(self, reference: str, *, expected_generation: int) -> None:
        path = self._path(reference)
        with self._locked():
            document = self._read_document(path)
            if document.get("generation") != expected_generation:
                raise SecretProviderError("secret_generation_conflict")
            path.unlink()

    def configured(self, reference: str) -> bool:
        try:
            self.read(reference)
        except SecretProviderError:
            return False
        return True

    def _path(self, reference: str) -> Path:
        environment_segment = f"/{self.environment}/"
        if (
            not reference
            or environment_segment not in reference
            or "://" in reference
            or ".." in reference
            or reference.startswith("/")
        ):
            raise SecretProviderError("secret_reference_environment_mismatch")
        return self.root / f"{hashlib.sha256(reference.encode()).hexdigest()}.json"

    def _read_document(self, path: Path) -> dict[str, object]:
        try:
            metadata = path.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) & 0o077
            ):
                raise SecretProviderError("secret_file_permissions_invalid")
            document = json.loads(path.read_bytes())
        except FileNotFoundError as error:
            raise SecretProviderError("secret_unavailable") from error
        except json.JSONDecodeError as error:
            raise SecretProviderError("secret_material_invalid") from error
        if (
            not isinstance(document, dict)
            or document.get("environment") != self.environment
        ):
            raise SecretProviderError("secret_environment_mismatch")
        return document

    def _atomic_write(self, path: Path, document: dict[str, object]) -> None:
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(
                    json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)

    def _locked(self) -> _FileLock:
        return _FileLock(self._lock)


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.descriptor: int | None = None

    def __enter__(self) -> None:
        self.descriptor = os.open(self.path, os.O_RDWR)
        fcntl.flock(self.descriptor, fcntl.LOCK_EX)

    def __exit__(self, *args: object) -> None:
        if self.descriptor is not None:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            os.close(self.descriptor)
