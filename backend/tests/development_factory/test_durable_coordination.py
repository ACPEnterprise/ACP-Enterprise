from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest
from development_factory.durable_coordination import (
    AuthorityFence,
    ClaimScope,
    CoordinationLimits,
    DurableCoordinationError,
    DurableCoordinationJournal,
)

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
QUEUE_DIGEST = "a" * 64


def fence(
    execution_id: str,
    *,
    assignment_id: str = "OM1-DF-DURABLE-COORDINATION-01",
    lease_id: str = "lease-one",
    version: int = 1,
    expires_at: datetime = NOW + timedelta(minutes=15),
) -> AuthorityFence:
    return AuthorityFence(
        assignment_id=assignment_id,
        execution_id=execution_id,
        worker_id="om1-worker",
        lease_id=lease_id,
        lease_version=version,
        lease_expires_at=expires_at,
        queue_digest=QUEUE_DIGEST,
    )


def scope(*, path: str = "backend/development_factory/**") -> ClaimScope:
    return ClaimScope((path,), ("repository:acp-enterprise",))


def test_atomic_claim_race_has_exactly_one_winner(tmp_path: Path) -> None:
    journal = DurableCoordinationJournal(tmp_path / "coordination")
    barrier = Barrier(2)

    def contend(lease_id: str) -> str:
        barrier.wait()
        try:
            journal.claim(fence("execution-race", lease_id=lease_id), scope(), now=NOW)
        except DurableCoordinationError:
            return "fenced"
        return "claimed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(contend, ("lease-one", "lease-two")))
    assert sorted(outcomes) == ["claimed", "fenced"]


def test_file_and_resource_fences_are_atomic_and_release_on_completion(
    tmp_path: Path,
) -> None:
    journal = DurableCoordinationJournal(tmp_path / "coordination")
    first = fence("execution-one")
    journal.claim(first, scope(), now=NOW)
    with pytest.raises(DurableCoordinationError, match="resource|file boundary"):
        journal.claim(
            fence(
                "execution-two",
                assignment_id="OM1-DF-SECOND",
                lease_id="lease-two",
            ),
            scope(path="backend/development_factory/coordination.py"),
            now=NOW,
        )
    journal.complete(first, evidence={"tests": "passed"}, now=NOW)
    journal.claim(
        fence(
            "execution-two",
            assignment_id="OM1-DF-SECOND",
            lease_id="lease-two",
        ),
        scope(path="backend/development_factory/coordination.py"),
        now=NOW,
    )


def test_stale_lease_version_is_fenced_after_monotonic_renewal(tmp_path: Path) -> None:
    journal = DurableCoordinationJournal(tmp_path / "coordination")
    original = fence("execution-renew")
    journal.claim(original, scope(), now=NOW)
    renewed = journal.renew(
        original,
        new_version=2,
        new_expires_at=NOW + timedelta(minutes=30),
        now=NOW + timedelta(seconds=1),
    )
    with pytest.raises(DurableCoordinationError, match="stale"):
        journal.checkpoint(
            original, phase="stale_writer", evidence={}, now=NOW + timedelta(seconds=2)
        )
    journal.checkpoint(
        renewed, phase="current_writer", evidence={}, now=NOW + timedelta(seconds=2)
    )


def test_checkpoint_tampering_fails_integrity_validation(tmp_path: Path) -> None:
    journal = DurableCoordinationJournal(tmp_path / "coordination")
    authority = fence("execution-integrity")
    journal.claim(authority, scope(), now=NOW)
    journal.checkpoint(
        authority, phase="workspace_ready", evidence={"clean": True}, now=NOW
    )
    path = tmp_path / "coordination" / "claims" / "execution-integrity.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["checkpoints"][1]["evidence"]["clean"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DurableCoordinationError, match="integrity"):
        journal.recover("execution-integrity", now=NOW)


def test_crash_restart_requires_digest_bound_reconciliation(tmp_path: Path) -> None:
    root = tmp_path / "coordination"
    authority = fence("execution-restart")
    DurableCoordinationJournal(root).claim(authority, scope(), now=NOW)
    restarted = DurableCoordinationJournal(root)
    decision = restarted.recover("execution-restart", now=NOW + timedelta(seconds=5))
    assert decision.state == "reconciliation_required"
    assert decision.last_checkpoint == "restart_reconciliation_required"
    with pytest.raises(DurableCoordinationError, match="stale"):
        restarted.release_reconciled(
            authority,
            reviewed_state_digest="0" * 64,
            now=NOW + timedelta(seconds=6),
        )
    final_digest = restarted.release_reconciled(
        authority,
        reviewed_state_digest=decision.state_digest,
        now=NOW + timedelta(seconds=6),
    )
    assert final_digest != decision.state_digest


def test_retry_budget_is_bounded_and_evidence_is_redacted(tmp_path: Path) -> None:
    journal = DurableCoordinationJournal(
        tmp_path / "coordination",
        limits=CoordinationLimits(max_retry_attempts=3, max_retry_delay_seconds=0),
    )
    authority = fence("execution-retry")
    journal.claim(authority, scope(), now=NOW)
    attempts = 0

    def transient() -> str:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("token=never-store-this-value")

    with pytest.raises(DurableCoordinationError, match="budget exhausted"):
        journal.retry_transient(
            authority,
            transient,
            sleep=lambda _: None,
            now=lambda: NOW + timedelta(seconds=attempts),
        )
    assert attempts == 3
    content = (tmp_path / "coordination" / "claims" / "execution-retry.json").read_text(
        encoding="utf-8"
    )
    assert "never-store-this-value" not in content
    assert "[REDACTED]" in content


def test_resource_and_evidence_limits_fail_closed(tmp_path: Path) -> None:
    journal = DurableCoordinationJournal(
        tmp_path / "coordination",
        limits=CoordinationLimits(max_resources=1, max_evidence_bytes=64),
    )
    with pytest.raises(DurableCoordinationError, match="resource limit"):
        journal.claim(
            fence("execution-limits"),
            ClaimScope(("backend/**",), ("one", "two")),
            now=NOW,
        )
    authority = fence("execution-evidence")
    journal.claim(authority, ClaimScope(("backend/**",), ("one",)), now=NOW)
    with pytest.raises(DurableCoordinationError, match="evidence limit"):
        journal.checkpoint(
            authority,
            phase="oversized",
            evidence={"output": "x" * 100},
            now=NOW,
        )
