from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.operational_migration.hcp_update_cohort_authority import (
    artifact_digest,
    canonical_bytes,
    verify_authority,
)


def _accepted_authority() -> dict[str, object]:
    records: list[dict[str, object]] = []
    specifications = (
        ("appointment", "OTHER_HELD", 6),
        ("customer", "CURRENT_OPERATIONAL", 5),
        ("customer", "SAFE_UPDATE", 15),
        ("job", "CURRENT_OPERATIONAL", 3),
        ("job", "SAFE_UPDATE", 22),
        ("job", "OTHER_HELD", 229),
    )
    for domain, cohort, count in specifications:
        for number in range(count):
            records.append(
                {
                    "domain": domain,
                    "source_id": f"{domain}_{cohort}_{number:03d}",
                    "original_assertion": "update",
                    "cohort": cohort,
                }
            )
    records.sort(key=lambda item: (item["domain"], item["source_id"]))
    value: dict[str, object] = {
        "contract": "hcp-update-runtime-cohorts/v1",
        "authority_contract": "hcp-source4-update-cohort-authority/v1",
        "source_package_digest": "4a4a9582d7fde37dba73ba9e93db5669d9341768c7f5741f6e8916971fd9ec60",
        "overlay_file_sha256": "ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558",
        "overlay_manifest_digest": "e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2",
        "hold_packet_sha256": "c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324",
        "records": records,
    }
    value["artifact_digest"] = artifact_digest(value)
    return value


def test_exact_update_cohort_is_canonical_and_stable(tmp_path: Path) -> None:
    authority = _accepted_authority()
    verify_authority(authority)
    first = canonical_bytes(authority)
    second = canonical_bytes(json.loads(first))
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    assert len(authority["records"]) == 280  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("overlay_file_sha256", "0" * 64, "accepted artifact binding"),
        ("hold_packet_sha256", "0" * 64, "accepted artifact binding"),
        ("source_package_digest", "0" * 64, "accepted artifact binding"),
    ),
)
def test_accepted_artifact_mismatch_fails_closed(
    field: str, replacement: str, message: str
) -> None:
    authority = _accepted_authority()
    authority[field] = replacement
    authority["artifact_digest"] = artifact_digest(authority)
    with pytest.raises(ValueError, match=message):
        verify_authority(authority)


def test_non_update_native_inference_and_update_to_create_are_rejected() -> None:
    for mutation in ("create", "native_id"):
        authority = copy.deepcopy(_accepted_authority())
        record = authority["records"][0]  # type: ignore[index]
        if mutation == "create":
            record["original_assertion"] = "create"
        else:
            record["native_id"] = "00000000-0000-0000-0000-000000000000"
        authority["artifact_digest"] = artifact_digest(authority)
        with pytest.raises(ValueError):
            verify_authority(authority)
