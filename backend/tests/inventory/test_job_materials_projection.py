from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.inventory.job_materials import extract_expected_materials


def test_extracts_only_version_pinned_material_components() -> None:
    snapshot_id = uuid4()
    snapshot = SimpleNamespace(
        id=snapshot_id,
        quantity=Decimal(2),
        snapshot_data={
            "quantity": "2",
            "components": [
                {
                    "type": "material",
                    "code": " pipe-1 ",
                    "label": "Pipe",
                    "quantity": "3",
                },
                {"type": "labor", "code": "LABOR", "label": "Labor", "quantity": "1"},
            ],
        },
    )

    result = extract_expected_materials((snapshot,), {snapshot_id: "a" * 64})  # type: ignore[arg-type]

    assert len(result) == 1
    assert result[0].code == "PIPE-1"
    assert result[0].quantity == Decimal(6)
    assert result[0].snapshot_ids == (snapshot_id,)
    assert result[0].snapshot_digests == ("a" * 64,)


def test_preserves_unbound_material_as_source_required_evidence() -> None:
    snapshot_id = uuid4()
    snapshot = SimpleNamespace(
        id=snapshot_id,
        quantity=Decimal(1),
        snapshot_data={
            "components": [
                {"type": "material", "label": "Owner-selected valve", "quantity": "1"}
            ],
        },
    )

    result = extract_expected_materials((snapshot,), {snapshot_id: "b" * 64})  # type: ignore[arg-type]

    assert result[0].code is None
    assert result[0].label == "Owner-selected valve"
    assert result[0].quantity == Decimal(1)
