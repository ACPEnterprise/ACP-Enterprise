#!/usr/bin/env python3
"""Provision Google Ads Beta secrets into Platform custody without printing values."""

from __future__ import annotations

import argparse
import json
import stat
from pathlib import Path

from app.platform.secrets import ProtectedSecretProvider, SecretProviderError


def protected_value(path: Path) -> str:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise SecretProviderError("secret_source_permissions_invalid")
    value = path.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise SecretProviderError("secret_source_invalid")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--client-id-file", type=Path, required=True)
    parser.add_argument("--client-secret-file", type=Path, required=True)
    parser.add_argument("--developer-token-file", type=Path, required=True)
    parser.add_argument("--expected-client-generation", type=int)
    parser.add_argument("--expected-developer-generation", type=int)
    args = parser.parse_args()
    provider = ProtectedSecretProvider(
        root=args.runtime_root / "secrets",
        repository_root=args.repository_root,
        environment="beta",
    )
    client = provider.write(
        "marketing/beta/google-ads/client",
        {
            "client_id": protected_value(args.client_id_file),
            "client_secret": protected_value(args.client_secret_file),
        },
        expected_generation=args.expected_client_generation,
    )
    developer = provider.write(
        "marketing/beta/google-ads/developer",
        {"developer_token": protected_value(args.developer_token_file)},
        expected_generation=args.expected_developer_generation,
    )
    print(
        json.dumps(
            {
                "status": "PROVISIONED",
                "environment": "beta",
                "client_generation": client.generation,
                "developer_generation": developer.generation,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, SecretProviderError) as error:
        print(
            json.dumps(
                {
                    "status": "REJECTED",
                    "code": getattr(error, "code", "custody_unavailable"),
                }
            )
        )
        raise SystemExit(2) from None
