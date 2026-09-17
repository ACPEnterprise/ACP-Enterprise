from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts/release-secret-custody-check.py"


def _repository(tmp_path: Path, tracked_content: bytes) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(("git", "init", "-q", str(repository)), check=True)
    env_example = repository / ".env.preview.example"
    env_example.write_text(
        "DATABASE_URL=SET_ME\n"
        "ACCESS_TOKEN_KEYS=SET_ME\n"
        "PLATFORM_CONTRACT_EXPECTED_FINGERPRINT=SET_ME\n",
        encoding="utf-8",
    )
    candidate = repository / "candidate.txt"
    candidate.write_bytes(tracked_content)
    subprocess.run(
        ("git", "-C", str(repository), "add", env_example.name, candidate.name),
        check=True,
    )
    return repository, env_example


def _run(repository: Path, env_example: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            str(SCRIPT),
            "--env-example",
            str(env_example),
            "--repository-root",
            str(repository),
        ),
        check=False,
        text=True,
        capture_output=True,
    )


def test_secret_custody_accepts_tracked_nonsecret_content(tmp_path: Path) -> None:
    repository, env_example = _repository(tmp_path, b"ordinary release evidence\n")

    result = _run(repository, env_example)

    assert result.returncode == 0
    assert "Tracked credential signatures detected: 0" in result.stdout


@pytest.mark.parametrize(
    ("classification", "secret"),
    (
        ("github_token", b"ghp_" + b"1234567890abcdefghijklmnop"),
        ("gitlab_token", b"glpat-" + b"1234567890abcdefghijklmnop"),
        ("google_api_key", b"AIza" + b"1234567890abcdefghijklmnopqrstuvwxy"),
        ("npm_token", b"npm_" + b"1234567890abcdefghijklmnopqrstuvwxyz"),
        (
            "sendgrid_api_key",
            b"SG." + b"1234567890abcdefghij" + b"." + b"1234567890abcdefghijklmnop",
        ),
        ("twilio_api_key", b"SK" + b"0123456789abcdef0123456789abcdef"),
        (
            "private_key",
            b"-----BEGIN ENCRYPTED PRIVATE KEY-----\n"
            + b"A" * 64
            + b"\n-----END ENCRYPTED PRIVATE KEY-----",
        ),
    ),
)
def test_secret_custody_rejects_signature_without_printing_value(
    tmp_path: Path, classification: str, secret: bytes
) -> None:
    repository, env_example = _repository(tmp_path, secret + b"\n")

    result = _run(repository, env_example)

    assert result.returncode == 1
    assert f"candidate.txt ({classification})" in result.stdout
    assert secret.decode() not in result.stdout
