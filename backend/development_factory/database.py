from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class DisposableDatabaseConfig:
    postgres_container: str
    backend_container: str
    database_user: str
    disposable_prefix: str


class DisposableDatabase:
    def __init__(self, config: DisposableDatabaseConfig, repo_root: Path) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,30}", config.disposable_prefix):
            raise ValueError("disposable database prefix is unsafe")
        self.config = config
        self.repo_root = repo_root
        self.name = f"{config.disposable_prefix}{uuid4().hex[:12]}"
        self.created = False

    def create(self, timeout: int = 60) -> None:
        self._run(
            [
                "docker",
                "exec",
                self.config.postgres_container,
                "createdb",
                "-U",
                self.config.database_user,
                self.name,
            ],
            timeout,
        )
        self.created = True

    def backend(self, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
        if not self.created:
            raise RuntimeError("disposable database was not created")
        safe_name = re.fullmatch(r"[a-z0-9_]+", self.name)
        if safe_name is None:
            raise RuntimeError("unsafe disposable database name")
        return self._run(
            [
                "docker",
                "exec",
                self.config.backend_container,
                "sh",
                "-lc",
                f'DATABASE_URL="${{DATABASE_URL%/*}}/{self.name}" {command}',
            ],
            timeout,
        )

    def drop_and_verify(self, timeout: int = 60) -> None:
        if self.created:
            self._run(
                [
                    "docker",
                    "exec",
                    self.config.postgres_container,
                    "dropdb",
                    "--force",
                    "-U",
                    self.config.database_user,
                    self.name,
                ],
                timeout,
            )
            self.created = False
        result = self._run(
            [
                "docker",
                "exec",
                self.config.postgres_container,
                "psql",
                "-U",
                self.config.database_user,
                "-d",
                "postgres",
                "-Atc",
                f"SELECT datname FROM pg_database WHERE datname = '{self.name}'",
            ],
            timeout,
        )
        if result.stdout.strip():
            raise RuntimeError("disposable database teardown verification failed")

    def _run(
        self, command: list[str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )


def config_from_dict(payload: dict[str, object]) -> DisposableDatabaseConfig:
    database = payload.get("database")
    if not isinstance(database, dict) or database.get("mode") != "docker":
        raise ValueError("safe disposable Docker database configuration is required")
    required = (
        "postgres_container",
        "backend_container",
        "database_user",
        "disposable_prefix",
    )
    if any(not isinstance(database.get(key), str) for key in required):
        raise ValueError("disposable database configuration is incomplete")
    return DisposableDatabaseConfig(
        postgres_container=str(database["postgres_container"]),
        backend_container=str(database["backend_container"]),
        database_user=str(database["database_user"]),
        disposable_prefix=str(database["disposable_prefix"]),
    )
