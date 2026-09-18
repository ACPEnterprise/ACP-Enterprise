import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_update_runtime_successor_command import _cohorts


def _write_private_json(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "cohorts.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_cohorts_loads_a_valid_record_list(tmp_path: Path) -> None:
    path = _write_private_json(
        tmp_path,
        {
            "contract": "hcp-update-runtime-cohorts/v1",
            "records": [
                {
                    "domain": "customer",
                    "source_id": "cus_1",
                    "cohort": "CURRENT_OPERATIONAL",
                }
            ],
        },
    )

    assert _cohorts(path) == {("customer", "cus_1"): "CURRENT_OPERATIONAL"}


@pytest.mark.parametrize("records", [None, {}, ["not-an-object"]])
def test_cohorts_rejects_non_record_collections(
    tmp_path: Path, records: object
) -> None:
    path = _write_private_json(
        tmp_path,
        {"contract": "hcp-update-runtime-cohorts/v1", "records": records},
    )

    with pytest.raises(ValueError, match="list of objects"):
        _cohorts(path)
