from app.operational_migration.hcp_missing_payload_inventory import (
    build_missing_payload_inventory,
)


def record(
    domain: str, source_id: str, *, executable: bool = True
) -> dict[str, object]:
    return {
        "domain": domain,
        "source_id": source_id,
        "source_executable": executable,
        "payload_locator": f"acquisition/{domain}-page-0001.json#{domain}:{source_id}",
        "source_digest": "a" * 64,
        "parent_keys": ["job:job-1"],
    }


def packet(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "provider_company_id": "hcp-company-1",
        "digest": "b" * 64,
        "records": records,
    }


def test_inventory_separates_get_only_retrieval_from_unsupported_gaps() -> None:
    rows = [record("employee", "e-1"), record("estimate", "q-1"), record("job", "j-1")]
    result = build_missing_payload_inventory(
        packet=packet(rows), available_payload_locators=()
    )

    assert [(row["domain"], row["source_id"]) for row in result.records] == [
        ("employee", "e-1"),
        ("estimate", "q-1"),
    ]
    assert result.unsupported[0]["source_id"] == "j-1"
    assert result.unsupported[0]["retrieval_disposition"] == "UNSUPPORTED_OR_INCOMPLETE"
    assert result.records[0]["parent_keys"] == ["job:job-1"]
    assert result.counts["get_only_retrievable"] == 2
    assert result.http_method_allowlist == ("GET",)
    assert result.provider_writes_allowed is False


def test_inventory_excludes_available_and_nonexecutable_records() -> None:
    available = record("invoice", "i-1")
    held = record("employee", "e-held", executable=False)
    result = build_missing_payload_inventory(
        packet=packet([available, held]),
        available_payload_locators=(available["payload_locator"],),
    )
    assert result.records == ()
    assert result.unsupported == ()


def test_inventory_rejects_duplicate_identity_and_missing_binding() -> None:
    duplicate = record("employee", "e-1")
    try:
        build_missing_payload_inventory(
            packet=packet([duplicate, duplicate]), available_payload_locators=()
        )
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate identity was accepted")

    try:
        build_missing_payload_inventory(
            packet={"digest": "b" * 64, "records": []}, available_payload_locators=()
        )
    except ValueError as error:
        assert "Company binding" in str(error)
    else:
        raise AssertionError("missing provider binding was accepted")
