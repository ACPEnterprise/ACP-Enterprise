import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.accounting.opening_source_adapter import SealedOpeningPackageAdapter


def _payload(manifest_digest: str) -> dict[str, object]:
    cutoff = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc).isoformat()
    digest = "a" * 64
    return {
        "realm_id": "realm-1",
        "package_identity": "run-1",
        "source_version": "qbo-v1",
        "cutoff_at": cutoff,
        "cutoff_timezone": "America/New_York",
        "acquired_at": cutoff,
        "source_as_of": cutoff,
        "source_manifest_digest": manifest_digest,
        "trial_balance": [
            {
                "source_identity": "cash",
                "account_type": "Bank",
                "debit": "10",
                "credit": "0",
                "source_version": "1",
                "source_digest": digest,
            },
            {
                "source_identity": "equity",
                "account_type": "Equity",
                "equity_category": "retained_earnings",
                "debit": "0",
                "credit": "10",
                "source_version": "1",
                "source_digest": digest,
            },
        ],
        "ar_control_balance": "0",
        "ap_control_balance": "0",
    }


def test_adapter_resolves_only_digest_bound_server_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_digest = "b" * 64
    packet = SimpleNamespace(
        manifest={"run_id": "run-1"},
        bounded_manifest={"realm_id": "realm-1"},
        manifest_sha256=manifest_digest,
    )
    monkeypatch.setattr(
        "app.accounting.opening_source_adapter.latest_bounded_evidence",
        lambda root: packet,
    )
    (tmp_path / "controls").mkdir()
    payload = _payload(manifest_digest)
    payload_digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (tmp_path / "controls" / "opening-run-1.json").write_text(
        json.dumps(
            {
                "opening_control_request": payload,
                "opening_control_request_digest": payload_digest,
            }
        )
    )
    result = SealedOpeningPackageAdapter(tmp_path).resolve("run-1")
    assert result.package_identity == "run-1"
    assert result.realm_id == "realm-1"


def test_adapter_rejects_tampered_server_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packet = SimpleNamespace(
        manifest={"run_id": "run-1"},
        bounded_manifest={"realm_id": "realm-1"},
        manifest_sha256="b" * 64,
    )
    monkeypatch.setattr(
        "app.accounting.opening_source_adapter.latest_bounded_evidence",
        lambda root: packet,
    )
    (tmp_path / "controls").mkdir()
    (tmp_path / "controls" / "opening-run-1.json").write_text(
        json.dumps(
            {
                "opening_control_request": _payload("b" * 64),
                "opening_control_request_digest": "c" * 64,
            }
        )
    )
    with pytest.raises(Exception, match="digest conflicts"):
        SealedOpeningPackageAdapter(tmp_path).resolve("run-1")
