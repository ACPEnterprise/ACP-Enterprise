from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_bundle import (
    AUTHORITY_CONTRACT,
    BUNDLE_CONTRACT,
    NovemberQualificationAuthority,
    REQUIRED_FILES,
    SEALED_HANDOFF_CONTRACT,
)


COMPANY = "3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd"
BRANCH = "887f413a-70dc-4ab1-98aa-8e84f4e7efd0"
ACTOR = "c427ebd1-7583-4c0d-9c54-55a0c1214174"
HCP_COMPANY = "aba4de03-d1b7-4c4e-8fb6-32a3fca713f5"
REPOSITORY_SHA = "f9888ce8338a0b74d4e4ac7ec21cdafa53039a1f"
ACQUISITION = "02820d1bbdb0a2468304cf493f717b8cae3982c5f8774404a813e07208680754"
RECONCILIATION = "7aaed3abde50d943cb4f981fbdcb185c19b1656e1cf3d1d8da6b20631ca12536"
ATTACHMENT_CUSTODY = "c11e31d63541d6e5c202535d85f73fab161d969f19dc0b737f7085582fbed79e"
SCHEMA_HEAD = "yp8r0t2v4x6z"
POLICY = "285d288b98da96140fff9e25200b95beb120d05a2b5196560a89d0a616dd7c0e"


def _record(source_id: str, domain: str, disposition: str, *, allowed: bool, reason: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "source_id": source_id,
        "domain": domain,
        "lineage": "EXACT",
        "disposition": disposition,
        "admission_allowed": allowed,
    }
    if reason:
        value["reason_class"] = reason
    return value


def _manifest() -> dict[str, Any]:
    records = [
        *(_record(f"job-{index}", "job", "HOLD_QUARANTINE", allowed=False) for index in range(22)),
        *(_record(f"appointment-duplicate-{index}", "appointment", "HOLD", allowed=False, reason="duplicate_risk") for index in range(13)),
        *(_record(f"technician-{index}", "technician", "HOLD", allowed=False, reason="unresolved_technician") for index in range(2)),
        _record("appointment-unassigned", "appointment", "HOLD", allowed=False, reason="unassigned"),
        _record("job-clean", "job", "CREATE", allowed=True),
        _record("appointment-clean", "appointment", "UPDATE", allowed=True),
        _record("customer-replay", "customer", "REPLAY", allowed=True),
    ]
    return {
        "contract": BUNDLE_CONTRACT,
        "environment": "preview",
        "scope": {
            "acp_company_id": COMPANY,
            "acp_branch_id": BRANCH,
            "authorized_actor_id": ACTOR,
            "hcp_provider_company_id": HCP_COMPANY,
        },
        "authority": {"repository_sha": REPOSITORY_SHA, "schema_head": SCHEMA_HEAD},
        "digests": {
            "acquisition_digest": ACQUISITION,
            "reconciliation_digest": RECONCILIATION,
            "attachment_custody_digest": ATTACHMENT_CUSTODY,
        },
        "attachments": {"bodies_included": False, "custody_digest": ATTACHMENT_CUSTODY},
        "dispositions": {
            "locationless_open_jobs": {"count": 22, "disposition": "HOLD_QUARANTINE"},
            "legacy_duplicate_risk_appointments": {"count": 13, "disposition": "HOLD"},
            "unresolved_technician_identities": {"count": 2, "disposition": "HOLD"},
            "unassigned_appointments": {"count": 1, "disposition": "HOLD"},
            "strict_open_relationship_failures": {"count": 0, "disposition": "NONE"},
        },
        "qualification": {
            "held_identities_excluded": True,
            "clean_records_not_blocked": True,
            "unexplained_omissions": 0,
            "missing_lineage": 0,
            "ambiguous_lineage": 0,
        },
        "record_assertions": records,
    }


def _write_bundle(tmp_path: Path, *, mutate: Any = None) -> tuple[Path, NovemberQualificationAuthority]:
    payloads = {
        name: json.dumps({"fixture": name}, sort_keys=True).encode()
        for name in REQUIRED_FILES
        if name != "BUNDLE-MANIFEST.json"
    }
    manifest = _manifest()
    manifest["file_sha256"] = {name: hashlib.sha256(value).hexdigest() for name, value in payloads.items()}
    if mutate:
        mutate(manifest)
    payloads["BUNDLE-MANIFEST.json"] = json.dumps(manifest, sort_keys=True).encode()
    path = tmp_path / "november-handoff.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payloads):
            archive.writestr(name, payloads[name])
    path.chmod(0o600)
    bundle_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, NovemberQualificationAuthority(
        bundle_path=path,
        bundle_sha256=bundle_sha,
        expected_repository_sha=REPOSITORY_SHA,
        expected_schema_head=SCHEMA_HEAD,
        expected_company_id=COMPANY,
        expected_branch_id=BRANCH,
        expected_actor_id=ACTOR,
        expected_hcp_provider_company_id=HCP_COMPANY,
        expected_environment="preview",
        expected_acquisition_digest=ACQUISITION,
        expected_reconciliation_digest=RECONCILIATION,
        expected_attachment_custody_digest=ATTACHMENT_CUSTODY,
    )


def test_november_bundle_qualifies_without_attachment_bodies(tmp_path: Path) -> None:
    _, authority = _write_bundle(tmp_path)

    result = authority.verify()

    assert result["qualification"] == "PASS"
    assert result["attachment_bodies_required"] is False
    assert result["counts"] == {"create": 1, "update": 1, "replay": 1, "hold": 38}
    assert result["unexplained_omissions"] == 0


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda manifest: manifest["dispositions"]["locationless_open_jobs"].update(count=21), "hcp_november_disposition_count_mismatch"),
        (lambda manifest: manifest["attachments"].update(bodies_included=True), "hcp_november_attachment_bodies_present"),
        (lambda manifest: manifest["record_assertions"][0].update(admission_allowed=True), "hcp_november_held_identity_admittable"),
        (lambda manifest: manifest["record_assertions"][0].update(lineage="AMBIGUOUS"), "hcp_november_record_lineage_invalid"),
        (lambda manifest: manifest["qualification"].pop("missing_lineage"), "hcp_november_qualification_gap"),
    ],
)
def test_november_bundle_fails_closed_on_unsafe_evidence(tmp_path: Path, mutate, code: str) -> None:
    _, authority = _write_bundle(tmp_path, mutate=mutate)

    with pytest.raises(SafeEvidenceError) as error:
        authority.verify()

    assert error.value.code == code


def test_november_bundle_rejects_outer_sha_tampering(tmp_path: Path) -> None:
    path, authority = _write_bundle(tmp_path)
    path.write_bytes(path.read_bytes() + b"tamper")
    path.chmod(0o600)

    with pytest.raises(SafeEvidenceError) as error:
        authority.verify()

    assert error.value.code == "hcp_november_bundle_sha256_mismatch"


def test_authority_contract_requires_private_mode(tmp_path: Path) -> None:
    path, authority = _write_bundle(tmp_path)
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(
        json.dumps(
            {
                "contract": AUTHORITY_CONTRACT,
                "bundle_path": str(path),
                "bundle_sha256": authority.bundle_sha256,
                "expected_repository_sha": REPOSITORY_SHA,
                "expected_schema_head": SCHEMA_HEAD,
                "expected_company_id": COMPANY,
                "expected_branch_id": BRANCH,
                "expected_actor_id": ACTOR,
                "expected_hcp_provider_company_id": HCP_COMPANY,
                "expected_environment": "preview",
                "expected_acquisition_digest": ACQUISITION,
                "expected_reconciliation_digest": RECONCILIATION,
                "expected_attachment_custody_digest": ATTACHMENT_CUSTODY,
            }
        )
    )
    authority_path.chmod(0o644)

    with pytest.raises(SafeEvidenceError) as error:
        NovemberQualificationAuthority.load(authority_path)

    assert error.value.code == "hcp_november_authority_permissions"


def _write_sealed_handoff(tmp_path: Path, *, omissions: bool = False) -> NovemberQualificationAuthority:
    root = tmp_path / "qualified-bundle"
    root.mkdir()
    payloads: dict[str, bytes] = {}
    for name in REQUIRED_FILES:
        if name != "BUNDLE-MANIFEST.json":
            payloads[name] = json.dumps({"fixture": name}, sort_keys=True).encode()
    payloads["reconciliation/reconciliation-manifest.json"] = json.dumps(
        {
            "summary": {
                "locationless_open_jobs_hold": 22,
                "legacy_duplicate_risk_appointments_hold": 13,
                "technicians_unresolved_hold": 2,
                "unassigned_open_work_appointments_intent_not_proven": 1,
                "strict_open_appointment_relationship_failures": 0,
            }
        }, sort_keys=True
    ).encode()
    payloads["policy/final-operational-cutover-disposition.json"] = json.dumps(
        {
            "digest": POLICY,
            "source_reconciliation_digest": RECONCILIATION,
            "source_mutation": False,
            "live_database_access": False,
            "network_access": False,
            "hold_contamination": {
                "inherent_contamination_if_final_policy_is_enforced": False,
                "unrelated_clean_jobs_blocked": 0,
                "unrelated_clean_appointments_blocked": 0,
            },
            "unexplained_omissions_in_original_gate": (
                [{"source_id": "omitted"}] if omissions else []
            ),
        }, sort_keys=True
    ).encode()
    for name, value in payloads.items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(value)
    manifest = {
        "contract": SEALED_HANDOFF_CONTRACT,
        "scope": {
            "company_id": COMPANY,
            "branch_id": BRANCH,
            "actor_id": ACTOR,
            "hcp_provider_company_id": HCP_COMPANY,
        },
        "source_digests": {
            "acquisition": ACQUISITION,
            "reconciliation": RECONCILIATION,
            "attachment_custody": ATTACHMENT_CUSTODY,
        },
        "target": {"label": "clean-beta", "accessed_during_preparation": False},
        "safety": {
            "beta_accessed": False,
            "hcp_reacquired": False,
            "live_database_mutated": False,
            "pushed_to_github": False,
        },
        "excluded": {"attachment_bodies": {"count": 621, "sealed_bytes": 3}},
        "included_files": [
            {"path": name, "sha256": hashlib.sha256(value).hexdigest()}
            for name, value in sorted(payloads.items())
        ],
    }
    (root / "BUNDLE-MANIFEST.json").write_text(json.dumps(manifest, sort_keys=True))
    archive = tmp_path / "handoff.tar.gz"
    archive.write_bytes(b"sealed-archive-fixture")
    archive.chmod(0o600)
    return NovemberQualificationAuthority(
        bundle_path=archive,
        bundle_root=root,
        bundle_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        expected_repository_sha=REPOSITORY_SHA,
        expected_schema_head=SCHEMA_HEAD,
        expected_company_id=COMPANY,
        expected_branch_id=BRANCH,
        expected_actor_id=ACTOR,
        expected_hcp_provider_company_id=HCP_COMPANY,
        expected_environment="preview",
        expected_acquisition_digest=ACQUISITION,
        expected_reconciliation_digest=RECONCILIATION,
        expected_attachment_custody_digest=ATTACHMENT_CUSTODY,
        expected_policy_digest=POLICY,
    )


def test_sealed_tar_handoff_qualifies_from_private_unpacked_root(tmp_path: Path) -> None:
    result = _write_sealed_handoff(tmp_path).verify()

    assert result["bundle_contract"] == SEALED_HANDOFF_CONTRACT
    assert result["dispositions"]["locationless_open_jobs"] == 22
    assert result["attachment_bodies_required"] is False


def test_sealed_tar_handoff_rejects_unexplained_omissions(tmp_path: Path) -> None:
    with pytest.raises(SafeEvidenceError) as error:
        _write_sealed_handoff(tmp_path, omissions=True).verify()

    assert error.value.code == "hcp_november_qualification_gap"
