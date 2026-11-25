import pytest
from app.customer_migration.intelligent_mapping import preview_mapping


def test_csv_and_xlsx_headers_map_by_meaning_not_position() -> None:
    csv = preview_mapping(("Customer ID", "First Name", "ZIP Code", "Legacy Segment"))
    xlsx = preview_mapping(("ZIP Code", "Legacy Segment", "First Name", "Customer ID"))
    assert {item.source_header: item.target_field for item in csv.mappings} == {
        item.source_header: item.target_field for item in xlsx.mappings
    }
    assert csv.unused_headers == ("Legacy Segment",)
    assert csv.admission_authorized is False


def test_exact_replay_is_idempotent_and_preserves_unused_fields() -> None:
    headers = ("Company Name", "Email Address", "Custom Territory")
    assert preview_mapping(headers) == preview_mapping(headers)
    result = preview_mapping(headers)
    assert result.unused_headers == ("Custom Territory",)
    assert len(result.mapping_digest) == 64


def test_ambiguous_target_is_reported_not_guessed() -> None:
    result = preview_mapping(("Phone", "Mobile Phone"))
    assert result.mappings[0].target_field == "phone"
    assert result.mappings[1].target_field is None
    assert result.mappings[1].confidence == "AMBIGUOUS"
    assert result.exceptions == ("ambiguous target phone: Mobile Phone",)


def test_duplicate_normalized_headers_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicate normalized"):
        preview_mapping(("First Name", "first-name"))
