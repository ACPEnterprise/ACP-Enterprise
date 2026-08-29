from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

MAX_CREDENTIAL_BYTES: Final = 4096
CLIENT_DOCUMENT_NAME: Final = "development-client.json"


class DevelopmentCredentialProvisioningError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DevelopmentCredentialProvisioningResult:
    status: str
    target: Path
    environment: str = "sandbox"
    directory_mode: str = "0700"
    file_mode: str = "0600"

    def safe_document(self) -> dict[str, str]:
        return {
            "status": self.status,
            "target": str(self.target),
            "environment": self.environment,
            "directory_mode": self.directory_mode,
            "file_mode": self.file_mode,
        }


def provision_development_credentials(
    *,
    client_id_file: Path,
    client_secret_file: Path,
    secret_root: Path,
    repository_root: Path,
) -> DevelopmentCredentialProvisioningResult:
    """Import legacy protected files into the sandbox provider document."""

    source_paths = (
        client_id_file.expanduser().absolute(),
        client_secret_file.expanduser().absolute(),
    )
    repository = repository_root.expanduser().resolve()
    for source in source_paths:
        if source == repository or repository in source.parents:
            raise DevelopmentCredentialProvisioningError(
                "credential_source_inside_repository"
            )
    if source_paths[0] == source_paths[1]:
        raise DevelopmentCredentialProvisioningError("credential_sources_conflict")

    root = secret_root.expanduser().absolute()
    if root == repository or repository in root.parents:
        raise DevelopmentCredentialProvisioningError(
            "credential_target_inside_repository"
        )
    _prepare_secret_root(root)
    target = root / CLIENT_DOCUMENT_NAME
    if target in source_paths:
        raise DevelopmentCredentialProvisioningError("credential_target_conflict")

    document = {
        "environment": "sandbox",
        "client_id": _read_legacy_value(source_paths[0], "client_id"),
        "client_secret": _read_legacy_value(source_paths[1], "client_secret"),
    }
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()

    if target.exists() or target.is_symlink():
        if _target_matches(target, document):
            return DevelopmentCredentialProvisioningResult(
                status="ALREADY_CURRENT", target=target
            )
        raise DevelopmentCredentialProvisioningError("credential_target_conflict")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".development-client.", suffix=".tmp", dir=root
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            if _target_matches(target, document):
                return DevelopmentCredentialProvisioningResult(
                    status="ALREADY_CURRENT", target=target
                )
            raise DevelopmentCredentialProvisioningError(
                "credential_target_conflict"
            ) from None
        os.chmod(target, 0o600)
        directory_descriptor = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)

    return DevelopmentCredentialProvisioningResult(status="PROVISIONED", target=target)


def _prepare_secret_root(root: Path) -> None:
    if root.exists() and root.is_symlink():
        raise DevelopmentCredentialProvisioningError("credential_root_symlink_rejected")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise DevelopmentCredentialProvisioningError("credential_root_invalid")
    if metadata.st_uid != os.getuid():
        raise DevelopmentCredentialProvisioningError("credential_root_owner_invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise DevelopmentCredentialProvisioningError(
            "credential_root_permissions_invalid"
        )
    os.chmod(root, 0o700)


def _read_legacy_value(source: Path, label: str) -> str:
    try:
        metadata = source.lstat()
    except FileNotFoundError as error:
        raise DevelopmentCredentialProvisioningError(
            f"{label}_source_missing"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise DevelopmentCredentialProvisioningError(f"{label}_source_invalid")
    if metadata.st_uid != os.getuid():
        raise DevelopmentCredentialProvisioningError(f"{label}_owner_invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise DevelopmentCredentialProvisioningError(f"{label}_permissions_invalid")
    if not 0 < metadata.st_size <= MAX_CREDENTIAL_BYTES:
        raise DevelopmentCredentialProvisioningError(f"{label}_size_invalid")

    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        payload = os.read(descriptor, MAX_CREDENTIAL_BYTES + 1)
    finally:
        os.close(descriptor)
    if not payload or len(payload) > MAX_CREDENTIAL_BYTES:
        raise DevelopmentCredentialProvisioningError(f"{label}_size_invalid")
    if payload.endswith(b"\n"):
        payload = payload[:-1]
    if not payload or b"\n" in payload or b"\r" in payload or b"\x00" in payload:
        raise DevelopmentCredentialProvisioningError(f"{label}_format_invalid")
    try:
        value = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DevelopmentCredentialProvisioningError(
            f"{label}_format_invalid"
        ) from error
    if value != value.strip():
        raise DevelopmentCredentialProvisioningError(f"{label}_format_invalid")
    return value


def _target_matches(target: Path, expected: dict[str, str]) -> bool:
    metadata = target.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise DevelopmentCredentialProvisioningError("credential_target_invalid")
    if metadata.st_uid != os.getuid():
        raise DevelopmentCredentialProvisioningError("credential_target_owner_invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise DevelopmentCredentialProvisioningError(
            "credential_target_permissions_invalid"
        )
    try:
        actual = json.loads(target.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise DevelopmentCredentialProvisioningError(
            "credential_target_invalid"
        ) from error
    return actual == expected


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision protected QBO credentials")
    subparsers = parser.add_subparsers(dest="command", required=True)
    provision = subparsers.add_parser("provision-development")
    provision.add_argument("--client-id-file", required=True, type=Path)
    provision.add_argument("--client-secret-file", required=True, type=Path)
    provision.add_argument("--secret-root", required=True, type=Path)
    provision.add_argument("--repository-root", required=True, type=Path)
    args = parser.parse_args()

    try:
        result = provision_development_credentials(
            client_id_file=args.client_id_file,
            client_secret_file=args.client_secret_file,
            secret_root=args.secret_root,
            repository_root=args.repository_root,
        )
    except DevelopmentCredentialProvisioningError as error:
        print(json.dumps({"status": "REJECTED", "code": error.code}))
        raise SystemExit(2) from None
    print(json.dumps(result.safe_document(), sort_keys=True))


if __name__ == "__main__":
    main()
