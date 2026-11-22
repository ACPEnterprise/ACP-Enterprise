"""Provider-neutral, file-only customer roster staging.

The engine deliberately stops at staging. It does not create customers, merge
identities, import jobs, or touch provider systems. A later admission boundary
must consume the reconciled rows and apply its own authorization and source
lineage rules.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID
from xml.etree import ElementTree

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_FORMATS = {"csv", "xlsx"}
SUPPORTED_FIELDS = frozenset(
    {
        "source_record_id",
        "display_name",
        "first_name",
        "last_name",
        "company_name",
        "email",
        "phone",
        "address",
        "city",
        "state",
        "postal_code",
    }
)


class ImportSchemaError(ValueError):
    """The source file cannot be safely staged."""


def _sha256(value: bytes | str) -> str:
    raw = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


@dataclass(frozen=True)
class CustomerImportScope:
    tenant_id: UUID
    branch_id: UUID
    source_provider: str
    source_namespace: str

    def __post_init__(self) -> None:
        for name in ("source_provider", "source_namespace"):
            value = _clean(getattr(self, name)).lower()
            if (
                not value
                or len(value) > 80
                or not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]*", value)
            ):
                raise ValueError(
                    f"{name} must be a bounded lowercase source identifier"
                )
            object.__setattr__(self, name, value)

    def identity_key(self, source_record_id: str) -> str:
        record_id = _clean(source_record_id)
        if not record_id or len(record_id) > 191:
            raise ValueError("source_record_id must be present and bounded")
        # Provider and namespace are intentionally both retained. This prevents
        # housecall_pro and housecall_pro_source4 from silently colliding.
        return f"{self.source_provider}:{self.source_namespace}:{record_id}"


@dataclass(frozen=True)
class CustomerImportMapping:
    """Maps source headers to canonical customer staging fields."""

    source_record_id: str
    fields: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        mapping = {"source_record_id": self.source_record_id, **dict(self.fields)}
        if any(
            not isinstance(canonical, str) or not isinstance(header, str)
            for canonical, header in mapping.items()
        ):
            raise ValueError("mapping fields and headers must be strings")
        if set(mapping) - SUPPORTED_FIELDS:
            raise ValueError("mapping contains unsupported canonical fields")
        if len(set(mapping.values())) != len(mapping.values()):
            raise ValueError("two canonical fields cannot use the same source header")
        if any(not _clean(header) for header in mapping.values()):
            raise ValueError("mapping headers cannot be blank")
        object.__setattr__(self, "fields", mapping)

    @property
    def digest(self) -> str:
        return _sha256(
            json.dumps(
                dict(sorted(self.fields.items())), separators=(",", ":"), sort_keys=True
            )
        )


@dataclass(frozen=True)
class StagedCustomerRow:
    row_number: int
    source_record_id: str
    source_identity_key: str
    source_row_sha256: str
    payload: Mapping[str, str]
    disposition: str
    reason_code: str | None = None
    validation_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationCounts:
    source_rows: int
    ready: int
    duplicates: int
    held: int
    rejected: int

    @property
    def reconciled(self) -> bool:
        return (
            self.source_rows == self.ready + self.duplicates + self.held + self.rejected
        )

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "source_rows": self.source_rows,
            "ready": self.ready,
            "duplicates": self.duplicates,
            "held": self.held,
            "rejected": self.rejected,
            "reconciled": self.reconciled,
        }


@dataclass(frozen=True)
class ImportBatchResult:
    batch_key: str
    source_sha256: str
    mapping_sha256: str
    schema_version: str
    file_format: str
    rows: tuple[StagedCustomerRow, ...]
    counts: ReconciliationCounts
    reused: bool


@dataclass(frozen=True)
class ImportAuditEvent:
    event_key: str
    event_type: str
    details: Mapping[str, object]


class ImportStore(Protocol):
    def get(self, batch_key: str) -> ImportBatchResult | None: ...

    def put(self, result: ImportBatchResult) -> None: ...

    def audit(self, batch_key: str, event: ImportAuditEvent) -> None: ...

    def events(self, batch_key: str) -> tuple[ImportAuditEvent, ...]: ...

    def processed_rows(self, batch_key: str) -> frozenset[int]: ...

    def mark_processed(self, batch_key: str, row_numbers: Iterable[int]) -> None: ...


class InMemoryImportStore:
    """Deterministic store used by unit tests and local import previews."""

    def __init__(self) -> None:
        self.batches: dict[str, ImportBatchResult] = {}
        self.audit_events: dict[str, dict[str, ImportAuditEvent]] = {}
        self.processed: dict[str, set[int]] = {}

    def get(self, batch_key: str) -> ImportBatchResult | None:
        return self.batches.get(batch_key)

    def put(self, result: ImportBatchResult) -> None:
        self.batches.setdefault(result.batch_key, result)

    def audit(self, batch_key: str, event: ImportAuditEvent) -> None:
        self.audit_events.setdefault(batch_key, {}).setdefault(event.event_key, event)

    def events(self, batch_key: str) -> tuple[ImportAuditEvent, ...]:
        return tuple(self.audit_events.get(batch_key, {}).values())

    def processed_rows(self, batch_key: str) -> frozenset[int]:
        return frozenset(self.processed.get(batch_key, set()))

    def mark_processed(self, batch_key: str, row_numbers: Iterable[int]) -> None:
        self.processed.setdefault(batch_key, set()).update(row_numbers)


def _csv_rows(content: bytes) -> tuple[str, list[dict[str, str]]]:
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = tuple(reader.fieldnames or ())
        if not headers:
            raise ImportSchemaError("file has no header row")
        if len(headers) != len(set(headers)):
            raise ImportSchemaError("file contains duplicate column headers")
        rows = list(reader)
        if any(None in row for row in rows):
            raise ImportSchemaError("file contains rows with more values than headers")
        return "csv", [
            {header: _clean(row.get(header)) for header in headers} for row in rows
        ]
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ImportSchemaError("file is not a valid UTF-8 CSV") from exc


def _xlsx_rows(content: bytes) -> tuple[str, list[dict[str, str]]]:
    """Read the small, ordinary xlsx subset needed for staging without a runtime dependency."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for item in root.findall("x:si", ns):
                    shared.append(
                        "".join(
                            node.text or ""
                            for node in item.iter()
                            if node.tag.endswith("}t") or node.tag == "t"
                        )
                    )
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rel_ns = (
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
            )
            sheet = workbook.find(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"
            )
            if sheet is None:
                raise ImportSchemaError("xlsx has no worksheet")
            relation = sheet.attrib.get(rel_ns + "id")
            target = next(
                (
                    item.attrib.get("Target")
                    for item in rels
                    if item.attrib.get("Id") == relation
                ),
                None,
            )
            if not target:
                raise ImportSchemaError("xlsx worksheet relationship is missing")
            worksheet_path = (
                "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
            )
            root = ElementTree.fromstring(archive.read(worksheet_path))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ImportSchemaError("file is not a valid xlsx workbook") from exc

    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    matrix: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", ns):
        values: list[str] = []
        for cell in row.findall("x:c", ns):
            value = cell.find("x:v", ns)
            if cell.attrib.get("t") == "inlineStr":
                raw = "".join(
                    node.text or ""
                    for node in cell.iter()
                    if node.tag.endswith("}t") or node.tag == "t"
                )
            else:
                raw = (value.text or "") if value is not None else ""
            if cell.attrib.get("t") == "s" and raw:
                raw = shared[int(raw)]
            values.append(_clean(raw))
        matrix.append(values)
    if not matrix or not matrix[0]:
        raise ImportSchemaError("xlsx has no header row")
    headers = matrix[0]
    if len(headers) != len(set(headers)):
        raise ImportSchemaError("file contains duplicate column headers")
    return "xlsx", [dict(zip(headers, row, strict=False)) for row in matrix[1:]]


class CustomerImportEngine:
    """Stage and resume customer files with deterministic replay semantics."""

    def __init__(self, store: ImportStore | None = None) -> None:
        self.store = store or InMemoryImportStore()

    def stage(
        self,
        content: bytes,
        *,
        filename: str,
        scope: CustomerImportScope,
        mapping: CustomerImportMapping,
        schema_version: str = "customer-file-staging/v1",
    ) -> ImportBatchResult:
        file_format = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if file_format == "xls":
            raise ImportSchemaError(
                "legacy .xls is not supported; save the workbook as .xlsx"
            )
        if file_format not in SUPPORTED_FORMATS:
            raise ImportSchemaError("customer import supports .csv and .xlsx files")
        detected_format, raw_rows = (
            _csv_rows(content) if file_format == "csv" else _xlsx_rows(content)
        )
        if detected_format != file_format:
            raise ImportSchemaError("file format does not match filename")
        headers = set(raw_rows[0]) if raw_rows else set()
        missing = set(mapping.fields.values()) - headers
        if missing:
            raise ImportSchemaError(
                f"mapped source columns are missing: {sorted(missing)}"
            )

        source_sha256 = _sha256(content)
        batch_key = _sha256(
            "\x1f".join(
                (
                    str(scope.tenant_id),
                    str(scope.branch_id),
                    scope.source_provider,
                    scope.source_namespace,
                    source_sha256,
                    mapping.digest,
                )
            )
        )
        existing = self.store.get(batch_key)
        if existing is not None:
            return ImportBatchResult(**{**existing.__dict__, "reused": True})

        rows: list[StagedCustomerRow] = []
        seen: set[str] = set()
        for row_number, raw in enumerate(raw_rows, start=2):
            payload = {
                canonical: _clean(raw.get(header))
                for canonical, header in mapping.fields.items()
            }
            source_id = payload.get("source_record_id", "")
            errors: list[str] = []
            if not source_id:
                errors.append("missing_source_record_id")
            if not any(
                payload.get(field)
                for field in (
                    "display_name",
                    "first_name",
                    "last_name",
                    "company_name",
                    "email",
                    "phone",
                    "address",
                )
            ):
                errors.append("missing_customer_identity_fields")
            row_digest = _sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":"))
            )
            identity_key = (
                scope.identity_key(source_id) if source_id else f"invalid:{row_number}"
            )
            if errors:
                disposition, reason = "rejected", errors[0]
            elif identity_key in seen:
                disposition, reason = "duplicate", "duplicate_source_identity_in_file"
            else:
                disposition, reason = "ready", None
                seen.add(identity_key)
            rows.append(
                StagedCustomerRow(
                    row_number,
                    source_id,
                    identity_key,
                    row_digest,
                    payload,
                    disposition,
                    reason,
                    tuple(errors),
                )
            )

        counts = ReconciliationCounts(
            source_rows=len(rows),
            ready=sum(row.disposition == "ready" for row in rows),
            duplicates=sum(row.disposition == "duplicate" for row in rows),
            held=sum(row.disposition == "held" for row in rows),
            rejected=sum(row.disposition == "rejected" for row in rows),
        )
        if not counts.reconciled:
            raise RuntimeError("customer import reconciliation counts do not balance")
        result = ImportBatchResult(
            batch_key,
            source_sha256,
            mapping.digest,
            schema_version,
            file_format,
            tuple(rows),
            counts,
            False,
        )
        self.store.put(result)
        self.store.audit(
            batch_key,
            ImportAuditEvent(
                "stage",
                "customer_import_staged",
                {
                    "counts": counts.as_dict(),
                    "source_provider": scope.source_provider,
                    "source_namespace": scope.source_namespace,
                },
            ),
        )
        return result

    def resume(
        self, batch_key: str, *, limit: int = 100
    ) -> tuple[StagedCustomerRow, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        batch = self.store.get(batch_key)
        if batch is None:
            raise KeyError(batch_key)
        processed = self.store.processed_rows(batch_key)
        rows = tuple(
            row
            for row in batch.rows
            if row.disposition == "ready" and row.row_number not in processed
        )
        selected = rows[:limit]
        self.store.mark_processed(batch_key, (row.row_number for row in selected))
        self.store.audit(
            batch_key,
            ImportAuditEvent(
                f"resume:{len(self.store.events(batch_key))}",
                "customer_import_resumed",
                {"limit": limit, "ready_rows": len(rows)},
            ),
        )
        return selected
