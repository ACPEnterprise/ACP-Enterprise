from __future__ import annotations

import io
import zipfile
from uuid import uuid4

import pytest

from app.customer_import.engine import (
    CustomerImportEngine,
    CustomerImportMapping,
    CustomerImportScope,
    ImportSchemaError,
    InMemoryImportStore,
)


def scope(namespace: str = "housecall_pro") -> CustomerImportScope:
    return CustomerImportScope(uuid4(), uuid4(), "housecall_pro", namespace)


def mapping() -> CustomerImportMapping:
    return CustomerImportMapping(
        source_record_id="ID",
        fields={
            "display_name": "Name",
            "email": "Email",
        },
    )


def csv_bytes(*rows: str) -> bytes:
    return ("ID,Name,Email\n" + "\n".join(rows) + "\n").encode()


def test_csv_reconciles_rows_and_replay_is_idempotent() -> None:
    store = InMemoryImportStore()
    engine = CustomerImportEngine(store)
    first = engine.stage(
        csv_bytes("cus-1,Ada,ada@example.test", "cus-1,Ada duplicate,", ",Missing ID,"),
        filename="customers.csv",
        scope=scope(),
        mapping=mapping(),
    )

    assert first.counts.as_dict() == {
        "source_rows": 3,
        "ready": 1,
        "duplicates": 1,
        "held": 0,
        "rejected": 1,
        "reconciled": True,
    }
    replay = engine.stage(
        csv_bytes("cus-1,Ada,ada@example.test", "cus-1,Ada duplicate,", ",Missing ID,"),
        filename="customers.csv",
        scope=scope(),
        mapping=mapping(),
    )
    # A different tenant is a different batch; replay must use the same scope.
    assert replay.reused is False

    same_scope = scope()
    first = engine.stage(
        csv_bytes("cus-2,Bea,bea@example.test"),
        filename="customers.csv",
        scope=same_scope,
        mapping=mapping(),
    )
    replay = engine.stage(
        csv_bytes("cus-2,Bea,bea@example.test"),
        filename="customers.csv",
        scope=same_scope,
        mapping=mapping(),
    )
    assert replay.reused is True
    assert replay.batch_key == first.batch_key
    assert engine.resume(first.batch_key, limit=1)[0].source_record_id == "cus-2"
    assert engine.resume(first.batch_key, limit=1) == ()


def test_provider_namespace_is_part_of_identity_and_never_collides() -> None:
    store = InMemoryImportStore()
    engine = CustomerImportEngine(store)
    provider_id = "same-native-id"
    source4 = engine.stage(
        csv_bytes(f"{provider_id},Source 4,source4@example.test"),
        filename="customers.csv",
        scope=scope("housecall_pro_source4"),
        mapping=mapping(),
    )
    legacy = engine.stage(
        csv_bytes(f"{provider_id},Legacy,legacy@example.test"),
        filename="customers.csv",
        scope=scope("housecall_pro"),
        mapping=mapping(),
    )
    assert source4.rows[0].source_identity_key != legacy.rows[0].source_identity_key
    assert source4.rows[0].source_identity_key.endswith(":same-native-id")
    assert legacy.rows[0].source_identity_key.endswith(":same-native-id")


def test_xlsx_staging_uses_first_worksheet_and_same_validation_contract() -> None:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as workbook:
        workbook.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Customers" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
            '</Relationships>',
        )
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>ID</t></is></c>'
            '<c r="B1" t="inlineStr"><is><t>Name</t></is></c></row>'
            '<row r="2"><c r="A2" t="inlineStr"><is><t>x-1</t></is></c>'
            '<c r="B2" t="inlineStr"><is><t>Xavier</t></is></c></row></sheetData>'
            '</worksheet>',
        )
    result = CustomerImportEngine().stage(
        content.getvalue(),
        filename="customers.xlsx",
        scope=scope(),
        mapping=CustomerImportMapping(source_record_id="ID", fields={"display_name": "Name"}),
    )
    assert result.file_format == "xlsx"
    assert result.counts.ready == 1


def test_missing_mapped_column_fails_closed() -> None:
    with pytest.raises(ImportSchemaError, match="missing"):
        CustomerImportEngine().stage(
            b"ID,Name\nx-1,Xavier\n",
            filename="customers.csv",
            scope=scope(),
            mapping=CustomerImportMapping(
                source_record_id="ID", fields={"email": "Email"}
            ),
        )


def test_duplicate_headers_fail_closed() -> None:
    with pytest.raises(ImportSchemaError, match="duplicate column headers"):
        CustomerImportEngine().stage(
            b"ID,ID,Name\nx-1,x-1,Xavier\n",
            filename="customers.csv",
            scope=scope(),
            mapping=CustomerImportMapping(source_record_id="ID", fields={"display_name": "Name"}),
        )


def test_mapping_rejects_non_string_headers() -> None:
    with pytest.raises(ValueError, match="must be strings"):
        CustomerImportMapping(source_record_id="ID", fields={"email": 12})  # type: ignore[arg-type]
