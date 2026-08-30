import json
from pathlib import Path

ROOT = Path(__file__).parents[3]


def _load(relative: str) -> dict[str, object]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_preview_acceptance_contract_is_closed_and_requires_reproducible_bindings() -> None:
    value = _load("docs/quality/crosscutting-preview-acceptance.v1.json")
    assert value["execution_environment"] == "PREVIEW_ONLY"
    assert value["classifications"] == ["PASS", "FAIL", "BLOCKED"]
    assert set(value["required_bindings"]) == {
        "git_sha",
        "alembic_head",
        "frontend_build_identity",
        "fixture_digest",
        "permission_catalog_fingerprint",
        "executed_at",
        "actual_result",
        "classification",
        "evidence_reference",
    }
    surfaces = value["surfaces"]
    assert isinstance(surfaces, list)
    assert len({item["id"] for item in surfaces}) == len(surfaces)


def test_physical_iphone_contract_has_all_canonical_personas_and_attacks() -> None:
    value = _load("docs/quality/physical-iphone-personas.v1.json")
    assert value["data_classification"] == "SYNTHETIC_ONLY"
    assert value["environment"] == "PREVIEW_ONLY"
    personas = value["personas"]
    assert isinstance(personas, list)
    assert {item["role"] for item in personas} == {
        "TECHNICIAN",
        "DISPATCHER",
        "SERVICE_CSR",
        "OFFICE_MANAGER",
        "COMPANY_ADMINISTRATOR",
        "OWN_DATA_ROLE",
    }
    assert len(value["mandatory_attacks"]) >= 6
    assert "Production" in value["prohibitions"]
