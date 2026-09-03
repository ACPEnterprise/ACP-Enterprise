import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_successor_reconciliation import (
    PrivateReuseEntry,
    PrivateSuccessorManifest,
)
from app.operational_migration.hcp_successor_reconciliation_command import (
    SuccessorReadAuthority,
    sealed_identities,
    write_private_manifest,
)


def test_authority_is_required_and_must_be_private(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(SafeEvidenceError) as caught:
        SuccessorReadAuthority.load(missing)
    assert caught.value.code == "successor_authority_invalid"

    authority = tmp_path / "authority.json"
    authority.write_text(json.dumps({"contract": "wrong"}))
    authority.chmod(0o644)
    with pytest.raises(SafeEvidenceError) as caught:
        SuccessorReadAuthority.load(authority)
    assert caught.value.code == "successor_authority_permissions_unsafe"


def test_sealed_plan_extraction_covers_operational_domains() -> None:
    customer = SimpleNamespace(
        source_identity="customer-1",
        service_location_source_identities=("location-1", "location-2"),
    )
    plan = SimpleNamespace(
        customers=SimpleNamespace(reviewed=SimpleNamespace(aggregates=(customer,))),
        jobs=(SimpleNamespace(source_id="job-1"),),
        appointments=(SimpleNamespace(source_id="appointment-1"),),
        estimates=(SimpleNamespace(source_id="estimate-1"),),
        invoices=(SimpleNamespace(source_id="invoice-1"),),
        payments=(SimpleNamespace(source_id="payment-1"),),
    )
    identities = sealed_identities(plan)
    assert {(item.domain, item.source_id) for item in identities} == {
        ("customer", "customer-1"),
        ("service_location", "location-1"),
        ("service_location", "location-2"),
        ("job", "job-1"),
        ("appointment", "appointment-1"),
        ("estimate", "estimate-1"),
        ("invoice", "invoice-1"),
        ("payment", "payment-1"),
    }


def test_private_manifest_write_is_atomic_private_and_replay_safe(
    tmp_path: Path,
) -> None:
    protected = tmp_path / "protected"
    protected.mkdir(mode=0o700)
    output = protected / "successors.json"
    entry = PrivateReuseEntry("customer", "private-source", "private-target")
    from app.operational_migration.hcp_successor_reconciliation import (
        IdentityBinding,
        SealedIdentity,
        reconcile_successors_v2,
    )

    result = reconcile_successors_v2(
        current_bindings=[
            IdentityBinding(
                "customer", "housecall_pro", "private-source", "private-target"
            )
        ],
        sealed_source4=[SealedIdentity("customer", "private-source")],
    )
    manifest = result.private_manifest
    assert manifest.entries == (entry,)
    write_private_manifest(output, manifest)
    assert output.stat().st_mode & 0o777 == 0o600
    original = output.read_bytes()
    write_private_manifest(output, manifest)
    assert output.read_bytes() == original

    contradictory = PrivateSuccessorManifest(
        (), __import__("hashlib").sha256(b"[]").hexdigest()
    )
    with pytest.raises(SafeEvidenceError) as caught:
        write_private_manifest(output, contradictory)
    assert caught.value.code == "successor_manifest_output_conflict"


def test_public_output_contains_no_private_ids(
    capsys, monkeypatch, tmp_path: Path
) -> None:
    import app.operational_migration.hcp_successor_reconciliation_command as command

    async def safe_run(_authority):
        return {
            "command": command.COMMAND_VERSION,
            "report": {"disposition_counts": {"reuse_legacy_target": 1}},
            "private_manifest": {"digest": "a" * 64, "entry_count": 1},
        }

    monkeypatch.setattr(command.SuccessorReadAuthority, "load", lambda _path: object())
    monkeypatch.setattr(command, "run", safe_run)
    assert command.main(["--authority-file", str(tmp_path / "authority")]) == 0
    stdout = capsys.readouterr().out
    assert "private-source" not in stdout
    assert "private-target" not in stdout
    assert '"entry_count": 1' in stdout
