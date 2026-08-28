import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.worker_runtime.recovery import RecoveryRecord, WorkerRecoveryJournal


def _stored(journal: WorkerRecoveryJournal, *, result=None) -> RecoveryRecord:
    record = RecoveryRecord(
        phase="reconciliation_required",
        offer_id=uuid4(),
        lease_id=uuid4(),
        started_at=datetime.now(timezone.utc),
        result=result,
    )
    journal.store(record)
    return record


def test_acknowledgement_archives_before_releasing_active_block(tmp_path) -> None:
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    journal = WorkerRecoveryJournal(directory)
    record = _stored(journal)
    digest = journal.digest()
    assert digest is not None

    archive_digest = journal.acknowledge(
        acknowledgement_id=uuid4(),
        expected_journal_digest=digest,
        audit_digest="a" * 64,
        acknowledged_at=datetime.now(timezone.utc),
        worker_id=uuid4(),
        command_id=uuid4(),
        execution_id=uuid4(),
        offer_id=record.offer_id,
        lease_id=record.lease_id,
    )

    assert journal.load() is None
    archive = directory / "recovery-history" / f"{digest}.json"
    assert archive.exists()
    assert archive.stat().st_mode & 0o077 == 0
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_digest
    preserved = json.loads(archive.read_text())
    assert preserved["journal"]["phase"] == "reconciliation_required"
    assert preserved["journal_digest"] == digest


def test_acknowledgement_rejects_pending_result(tmp_path) -> None:
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    journal = WorkerRecoveryJournal(directory)
    record = _stored(journal, result={"outcome": "succeeded"})
    with pytest.raises(ValueError, match="normal delivery"):
        journal.acknowledge(
            acknowledgement_id=uuid4(),
            expected_journal_digest=journal.digest() or "",
            audit_digest="a" * 64,
            acknowledged_at=datetime.now(timezone.utc),
            worker_id=uuid4(),
            command_id=uuid4(),
            execution_id=uuid4(),
            offer_id=record.offer_id,
            lease_id=record.lease_id,
        )
    assert journal.load() == record


def test_acknowledgement_rejects_wrong_lineage_or_digest(tmp_path) -> None:
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    journal = WorkerRecoveryJournal(directory)
    record = _stored(journal)
    acknowledgement_id = uuid4()
    acknowledged_at = datetime.now(timezone.utc)
    worker_id = uuid4()
    command_id = uuid4()
    execution_id = uuid4()
    with pytest.raises(ValueError, match="digest"):
        journal.acknowledge(
            acknowledgement_id=acknowledgement_id,
            expected_journal_digest="b" * 64,
            audit_digest="a" * 64,
            acknowledged_at=acknowledged_at,
            worker_id=worker_id,
            command_id=command_id,
            execution_id=execution_id,
            offer_id=record.offer_id,
            lease_id=record.lease_id,
        )
    with pytest.raises(ValueError, match="lineage"):
        journal.acknowledge(
            acknowledgement_id=acknowledgement_id,
            expected_journal_digest=journal.digest() or "",
            audit_digest="a" * 64,
            acknowledged_at=acknowledged_at,
            worker_id=worker_id,
            command_id=command_id,
            execution_id=execution_id,
            offer_id=record.offer_id,
            lease_id=uuid4(),
        )
    assert journal.load() == record
