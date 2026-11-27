from __future__ import annotations

import importlib.util
import json
import stat
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)
PASSPHRASE = b"owner-controlled-test-passphrase"


def module():
    spec = importlib.util.spec_from_file_location(
        "enterprise_release_authority",
        ROOT / "scripts" / "enterprise_release_authority.py",
    )
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def review_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_independent_review",
        ROOT / "scripts" / "validate-independent-review.py",
    )
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def private_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def enrolled(tmp_path: Path):
    authority = module()
    root = tmp_path / "authority"
    root.mkdir(mode=0o700)
    receipt = authority.create_enrollment(
        root,
        custodian_id="michael-fouse",
        custodian_name="Michael Fouse",
        reviewer_id="enterprise-independent-review",
        reviewer_name="Enterprise Independent Qualification Review",
        owner_approval_id=str(uuid.uuid4()),
        passphrase=PASSPHRASE,
        now=NOW,
    )
    registry = root / "trust" / "authority.json"
    public_key = Path(receipt["public_key_reference"])
    private_key = Path(receipt["private_key_reference"])
    return authority, root, receipt, registry, public_key, private_key


def release_values() -> dict[str, str]:
    return {
        "candidate_sha": "a" * 40,
        "migration_head": "u1v3x5z7b9d2",
        "backup_receipt_sha256": "b" * 64,
        "restore_receipt_sha256": "c" * 64,
        "rollback_target_sha": "d" * 40,
        "rollback_target_release": "enterprise-beta-3d415c07",
    }


def review_receipt(
    path: Path, *, defects: list[str] | None = None, **overrides: object
) -> Path:
    values = release_values()
    review: dict[str, object] = {
        "contract": "enterprise-release-independent-review/v1",
        "review_id": str(uuid.uuid4()),
        "candidate_sha": values["candidate_sha"],
        "migration_head": values["migration_head"],
        "backup_receipt_sha256": values["backup_receipt_sha256"],
        "restore_receipt_sha256": values["restore_receipt_sha256"],
        "rollback_target": {
            "sha": values["rollback_target_sha"],
            "release": values["rollback_target_release"],
        },
        "scope": "BETA_PREVIEW",
        "reviewer": {
            "id": "enterprise-independent-review",
            "name": "Enterprise Independent Qualification Review",
            "role": "Enterprise Independent Qualification Reviewer",
        },
        "evidence_archive_sha256": "e" * 64,
        "mandatory_gates_passed": not defects,
        "defects": defects or [],
        "decision": "APPROVE" if not defects else "NO_GO",
        "reviewed_at": (NOW - timedelta(minutes=10)).isoformat(),
    }
    review.update(overrides)
    private_json(path, review)
    return path


def issue(tmp_path: Path):
    authority, root, receipt, registry, public_key, private_key = enrolled(tmp_path)
    review = review_receipt(tmp_path / "review.json")
    approval = tmp_path / "approval.json"
    authority.issue_approval(
        root,
        registry_path=registry,
        trusted_key_path=public_key,
        private_key_path=private_key,
        expected_key_id=receipt["key_id"],
        review_path=review,
        output_path=approval,
        passphrase=PASSPHRASE,
        now=NOW,
        **release_values(),
    )
    return authority, root, receipt, registry, public_key, private_key, review, approval


def test_owner_enrollment_creates_named_encrypted_authority_and_audit(
    tmp_path: Path,
) -> None:
    authority, root, receipt, registry, public_key, private_key = enrolled(tmp_path)

    assert receipt["authority_id"] == "twelvehats-beta-release-authority"
    assert receipt["custodian"] == {"id": "michael-fouse", "name": "Michael Fouse"}
    assert receipt["key_id"].startswith("beta-era-20261123-")
    assert b"ENCRYPTED PRIVATE KEY" in private_key.read_bytes()
    assert stat.S_IMODE(private_key.stat().st_mode) == 0o600
    assert stat.S_IMODE(public_key.stat().st_mode) == 0o600
    trusted, key, _ = authority.validate_registry(
        registry,
        public_key,
        expected_key_id=receipt["key_id"],
        now=NOW,
        for_issuance=True,
    )
    assert trusted["independent_review"]["required"] is True
    assert key["status"] == "active"
    assert authority.verify_audit(root)["events"] == 1


def test_enrollment_rejects_custodian_as_independent_reviewer(tmp_path: Path) -> None:
    authority = module()
    root = tmp_path / "authority"
    root.mkdir(mode=0o700)

    with pytest.raises(authority.AuthorityError, match="reviewer must differ"):
        authority.create_enrollment(
            root,
            custodian_id="michael-fouse",
            custodian_name="Michael Fouse",
            reviewer_id="michael-fouse",
            reviewer_name="Michael Fouse",
            owner_approval_id=str(uuid.uuid4()),
            passphrase=PASSPHRASE,
            now=NOW,
        )


def test_issuer_requires_exact_independent_review_and_validates_v2_artifact(
    tmp_path: Path,
) -> None:
    authority, _, receipt, registry, public_key, _, _, approval = issue(tmp_path)

    result = authority.validate_approval(
        approval,
        registry,
        public_key,
        expected_key_id=receipt["key_id"],
        now=NOW + timedelta(minutes=1),
        **release_values(),
    )

    assert result["contract"] == "enterprise-preview-release-approval/v2"
    assert result["issuer"] == "twelvehats-beta-release-authority"
    assert result["custodian"] == "Michael Fouse"
    assert result["candidate_sha"] == "a" * 40


def test_independent_review_is_validatable_before_signed_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, receipt, registry, public_key, _, review, approval = issue(tmp_path)

    approval.unlink()
    values = release_values()
    validator = review_validator()
    monkeypatch.setattr(validator, "utc_now", lambda: NOW)
    result = validator.validate_independent_review_receipt(
        SimpleNamespace(
            review_receipt=review,
            registry=registry,
            trusted_key=public_key,
            key_id=receipt["key_id"],
            **values,
        )
    )

    assert result["contract"] == "enterprise-release-independent-review/v1"
    assert result["candidate_sha"] == "a" * 40
    assert result["review_receipt_sha256"]


def test_independent_review_validation_does_not_accept_missing_receipt(
    tmp_path: Path,
) -> None:
    _, _, receipt, registry, public_key, _ = enrolled(tmp_path)

    with pytest.raises(ValueError, match="must be a regular file"):
        values = release_values()
        review_validator().validate_independent_review_receipt(
            SimpleNamespace(
                review_receipt=tmp_path / "missing-review.json",
                registry=registry,
                trusted_key=public_key,
                key_id=receipt["key_id"],
                **values,
            )
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("candidate_sha", "f" * 40, "candidate_sha does not match"),
        ("mandatory_gates_passed", False, "not passed every mandatory gate"),
        ("decision", "NO_GO", "unresolved defects or is not approved"),
    ),
)
def test_issuer_rejects_unqualified_or_mismatched_review(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    authority, root, receipt, registry, public_key, private_key = enrolled(tmp_path)
    review = review_receipt(tmp_path / "review.json", **{field: value})

    with pytest.raises(authority.AuthorityError, match=message):
        authority.issue_approval(
            root,
            registry_path=registry,
            trusted_key_path=public_key,
            private_key_path=private_key,
            expected_key_id=receipt["key_id"],
            review_path=review,
            output_path=tmp_path / "approval.json",
            passphrase=PASSPHRASE,
            now=NOW,
            **release_values(),
        )


def test_tampering_wrong_key_and_expiry_fail_closed(tmp_path: Path) -> None:
    authority, _, receipt, registry, public_key, _, _, approval = issue(tmp_path)
    artifact = json.loads(approval.read_text())
    artifact["candidate_sha"] = "f" * 40
    private_json(approval, artifact)

    with pytest.raises(authority.AuthorityError, match="candidate_sha does not match"):
        authority.validate_approval(
            approval,
            registry,
            public_key,
            expected_key_id=receipt["key_id"],
            now=NOW + timedelta(minutes=1),
            **release_values(),
        )

    second = tmp_path / "second"
    second.mkdir()
    _, _, _, _, _, _, _, clean_approval = issue(second)
    with pytest.raises(authority.AuthorityError, match="expired"):
        authority.validate_approval(
            clean_approval,
            second / "authority" / "trust" / "authority.json",
            Path(
                json.loads(
                    (second / "authority" / "receipts" / "enrollment.json").read_text()
                )["public_key_reference"]
            ),
            expected_key_id=json.loads(
                (second / "authority" / "receipts" / "enrollment.json").read_text()
            )["key_id"],
            now=NOW + timedelta(hours=2),
            **release_values(),
        )


def test_rotation_preserves_short_verification_window_and_revocation_blocks(
    tmp_path: Path,
) -> None:
    authority, root, receipt, registry, public_key, private_key, _, approval = issue(
        tmp_path
    )
    rotation = authority.rotate_key(
        root,
        registry_path=registry,
        current_key_id=receipt["key_id"],
        current_private_key_path=private_key,
        current_passphrase=PASSPHRASE,
        new_passphrase=b"new-owner-controlled-passphrase",
        owner_approval_id=str(uuid.uuid4()),
        now=NOW + timedelta(minutes=5),
    )
    old_result = authority.validate_approval(
        approval,
        registry,
        public_key,
        expected_key_id=receipt["key_id"],
        now=NOW + timedelta(minutes=6),
        **release_values(),
    )
    assert old_result["key_id"] == receipt["key_id"]
    new_private = Path(rotation["private_key_reference"])
    authority.revoke_key(
        root,
        registry_path=registry,
        key_id=rotation["key_id"],
        private_key_path=new_private,
        passphrase=b"new-owner-controlled-passphrase",
        reason="qualification drill",
        owner_approval_id=str(uuid.uuid4()),
        now=NOW + timedelta(minutes=7),
    )
    with pytest.raises(authority.AuthorityError, match="active"):
        authority.validate_registry(
            registry,
            Path(rotation["public_key_reference"]),
            expected_key_id=rotation["key_id"],
            now=NOW + timedelta(minutes=8),
        )
    assert authority.verify_audit(root)["events"] == 4


def test_wrong_private_key_and_unsafe_files_are_rejected(tmp_path: Path) -> None:
    authority, _, receipt, registry, public_key, private_key = enrolled(tmp_path)
    public_key.chmod(0o644)
    with pytest.raises(authority.AuthorityError, match="mode 0600"):
        authority.validate_registry(
            registry,
            public_key,
            expected_key_id=receipt["key_id"],
            now=NOW,
        )
    private_key.chmod(0o600)
    with pytest.raises(authority.AuthorityError, match="could not be unlocked"):
        authority.load_private_key(private_key, b"wrong-passphrase-value")
