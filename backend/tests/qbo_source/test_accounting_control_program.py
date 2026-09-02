from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.qbo_source.accounting_control_program import seal_accounting_control_program
from app.qbo_source.evidence import ProtectedFilesystemEvidenceStore


def test_program_accepts_transition_controls_and_stops_at_ar(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    root = tmp_path / "protected"
    controls = root / "controls"
    controls.mkdir(parents=True)
    root.chmod(0o700)
    controls.chmod(0o700)
    for authority_id in (
        "qbo-current-environment-authority-v1",
        "qbo-transition-ledger-control-2024-02-19-v1",
        "qbo-transition-cash-balance-control-2024-02-19-v1",
        "qbo-cutoff-ar-aging-control-2026-08-31-v1",
    ):
        document: dict[str, object] = {"schema_version": "synthetic/v1"}
        document["evidence_digest"] = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        (controls / f"{authority_id}.json").write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":"))
        )
    store = ProtectedFilesystemEvidenceStore(root=root, repository_root=repository)
    result = seal_accounting_control_program(store=store)
    assert result["state"] == "ACCOUNTING_CONTROL_PROGRAM_READY_AT_AR_LEDGER_TIE_GATE"
    assert result["opening_ledger"] == "ACCEPTED"
    assert result["coa_owner_accountant_decisions"] == 92
    assert result["next_report"] == "ACCRUAL_TRIAL_BALANCE_2026-08-31"
