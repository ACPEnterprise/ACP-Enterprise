from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.engineering_control.repository_readiness import readiness_is_current


def evidence(now: datetime, **changes: object) -> dict[str, object]:
    readiness: dict[str, object] = {
        "ready": True,
        "repository_key": "acp-enterprise",
        "branch": "customer-management-v1",
        "candidate_head": "a" * 40,
        "observed_head": "a" * 40,
        "worker_id": str(uuid4()),
        "provider_software_sha": "b" * 40,
        "prepared_at": now.isoformat(),
    }
    readiness.update(changes)
    return {"provider_repository_readiness": readiness}


def test_matching_fresh_repository_evidence_is_ready() -> None:
    now = datetime.now(timezone.utc)
    value = evidence(now)
    assert readiness_is_current(
        value,
        repository_key="acp-enterprise",
        branch="customer-management-v1",
        candidate_head="a" * 40,
        now=now,
    )


def test_stale_or_mismatched_repository_evidence_fails_closed() -> None:
    now = datetime.now(timezone.utc)
    assert not readiness_is_current(
        evidence(now - timedelta(minutes=3)),
        repository_key="acp-enterprise",
        branch="customer-management-v1",
        candidate_head="a" * 40,
        now=now,
    )
    assert not readiness_is_current(
        evidence(now, observed_head="c" * 40),
        repository_key="acp-enterprise",
        branch="customer-management-v1",
        candidate_head="a" * 40,
        now=now,
    )
