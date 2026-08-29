import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from typing import Literal, TypeAlias

from app.operational_migration.cutover import (
    ArtifactMigrationRecord,
    HistoryMigrationRecord,
)
from app.operational_migration.financial import (
    EstimateMigrationRecord,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
)

OperationalEntity = Literal[
    "job",
    "appointment",
    "estimate",
    "invoice",
    "payment",
    "note",
    "attachment",
]
OperationalRecord: TypeAlias = (
    JobMigrationRecord
    | AppointmentMigrationRecord
    | EstimateMigrationRecord
    | InvoiceMigrationRecord
    | PaymentMigrationRecord
    | HistoryMigrationRecord
    | ArtifactMigrationRecord
)
RejectionDisposition = Literal["rejected", "duplicate"]


class TransformationValidationError(ValueError):
    """A source-adapter validation failure containing no source values."""

    def __init__(self, code: str, *, fields: Sequence[str] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.fields = tuple(sorted(set(fields)))


@dataclass(frozen=True)
class SourceField:
    """One explicitly approved field in a versioned source export."""

    name: str
    required: bool

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip():
            raise ValueError("Source field names must be non-empty and normalized.")


@dataclass(frozen=True)
class ParsedSourceExport:
    """Format-independent rows plus the checksum of their original source bytes."""

    entity: OperationalEntity
    version: str
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, object], ...]
    source_sha256: str

    @classmethod
    def from_source_bytes(
        cls,
        *,
        entity: OperationalEntity,
        version: str,
        columns: Sequence[str],
        rows: Sequence[Mapping[str, object]],
        source_bytes: bytes,
    ) -> "ParsedSourceExport":
        return cls(
            entity=entity,
            version=version,
            columns=tuple(columns),
            rows=tuple(dict(row) for row in rows),
            source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        )


@dataclass(frozen=True)
class TransformationRejection:
    entity: OperationalEntity
    row_number: int | None
    disposition: RejectionDisposition
    code: str
    fields: tuple[str, ...] = ()
    source_id_sha256: str | None = None


@dataclass(frozen=True)
class TransformationReport:
    entity: OperationalEntity
    version: str
    source_sha256: str
    transformation_sha256: str
    source: int
    accepted: int
    rejected: int
    duplicate: int
    records: tuple[OperationalRecord, ...]
    rejections: tuple[TransformationRejection, ...]


RecordBuilder: TypeAlias = Callable[[Mapping[str, object]], OperationalRecord]


@dataclass(frozen=True)
class TransformationContract:
    """Exact source-layout contract registered only after a layout is known."""

    provider: str
    entity: OperationalEntity
    version: str
    fields: tuple[SourceField, ...]
    builder: RecordBuilder
    exact_columns: bool = False

    def __post_init__(self) -> None:
        if not self.provider or self.provider != self.provider.strip().lower():
            raise ValueError("Provider must be a normalized non-empty identifier.")
        if not self.version or self.version != self.version.strip():
            raise ValueError("Export version must be explicit.")
        names = [field.name for field in self.fields]
        if not names or len(names) != len(set(names)):
            raise ValueError("Source fields must be non-empty and unique.")

    @property
    def field_names(self) -> frozenset[str]:
        return frozenset(field.name for field in self.fields)

    @property
    def required_fields(self) -> frozenset[str]:
        return frozenset(field.name for field in self.fields if field.required)


EXPECTED_RECORD_TYPES: dict[OperationalEntity, type[object]] = {
    "job": JobMigrationRecord,
    "appointment": AppointmentMigrationRecord,
    "estimate": EstimateMigrationRecord,
    "invoice": InvoiceMigrationRecord,
    "payment": PaymentMigrationRecord,
    "note": HistoryMigrationRecord,
    "attachment": ArtifactMigrationRecord,
}


class OperationalTransformationPipeline:
    """Fail-closed source export transformation into migration contracts."""

    def __init__(
        self,
        *,
        provider: str,
        contracts: Sequence[TransformationContract] = (),
    ) -> None:
        normalized = provider.strip().lower()
        if not normalized:
            raise ValueError("Provider is required.")
        self.provider = normalized
        self._contracts: dict[
            tuple[OperationalEntity, str], TransformationContract
        ] = {}
        for contract in contracts:
            if contract.provider != self.provider:
                raise ValueError("Contract provider does not match the pipeline.")
            key = (contract.entity, contract.version)
            if key in self._contracts:
                raise ValueError("Duplicate entity and export-version contract.")
            self._contracts[key] = contract

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _is_missing(value: object) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _record_payload(record: OperationalRecord) -> dict[str, object]:
        if not is_dataclass(record):
            raise TypeError("Transformation builders must return migration records.")
        return asdict(record)

    def _report(
        self,
        *,
        export: ParsedSourceExport,
        records: Sequence[OperationalRecord],
        rejections: Sequence[TransformationRejection],
    ) -> TransformationReport:
        payload = {
            "provider": self.provider,
            "entity": export.entity,
            "version": export.version,
            "source_sha256": export.source_sha256,
            "records": [self._record_payload(record) for record in records],
            "rejections": [asdict(rejection) for rejection in rejections],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        return TransformationReport(
            entity=export.entity,
            version=export.version,
            source_sha256=export.source_sha256,
            transformation_sha256=digest,
            source=len(export.rows),
            accepted=len(records),
            rejected=sum(
                rejection.disposition == "rejected" for rejection in rejections
            ),
            duplicate=sum(
                rejection.disposition == "duplicate" for rejection in rejections
            ),
            records=tuple(records),
            rejections=tuple(rejections),
        )

    def _fatal(
        self,
        export: ParsedSourceExport,
        *,
        code: str,
        fields: Sequence[str] = (),
    ) -> TransformationReport:
        return self._report(
            export=export,
            records=(),
            rejections=(
                TransformationRejection(
                    entity=export.entity,
                    row_number=None,
                    disposition="rejected",
                    code=code,
                    fields=tuple(sorted(set(fields))),
                ),
            ),
        )

    def transform(
        self,
        export: ParsedSourceExport,
        *,
        expected_source_sha256: str,
    ) -> TransformationReport:
        if len(expected_source_sha256) != 64 or (
            expected_source_sha256 != export.source_sha256
        ):
            return self._fatal(export, code="source_checksum_mismatch")
        contract = self._contracts.get((export.entity, export.version))
        if contract is None:
            return self._fatal(export, code="unsupported_export_version")
        if len(export.columns) != len(set(export.columns)):
            return self._fatal(export, code="duplicate_columns")
        unknown = set(export.columns) - contract.field_names
        if unknown:
            return self._fatal(export, code="unknown_columns", fields=tuple(unknown))
        if contract.exact_columns and set(export.columns) != contract.field_names:
            return self._fatal(
                export,
                code="changed_layout",
                fields=tuple(contract.field_names - set(export.columns)),
            )
        missing_columns = contract.required_fields - set(export.columns)
        if missing_columns:
            return self._fatal(
                export,
                code="missing_required_columns",
                fields=tuple(missing_columns),
            )

        records: list[OperationalRecord] = []
        rejections: list[TransformationRejection] = []
        seen_source_ids: set[str] = set()
        expected_type = EXPECTED_RECORD_TYPES[export.entity]
        for row_number, source_row in enumerate(export.rows, start=1):
            row = dict(source_row)
            row_unknown = set(row) - contract.field_names
            if row_unknown:
                rejections.append(
                    TransformationRejection(
                        entity=export.entity,
                        row_number=row_number,
                        disposition="rejected",
                        code="unknown_fields",
                        fields=tuple(sorted(row_unknown)),
                    )
                )
                continue
            missing = {
                field
                for field in contract.required_fields
                if field not in row or self._is_missing(row[field])
            }
            if missing:
                rejections.append(
                    TransformationRejection(
                        entity=export.entity,
                        row_number=row_number,
                        disposition="rejected",
                        code="missing_required_fields",
                        fields=tuple(sorted(missing)),
                    )
                )
                continue
            try:
                record = contract.builder(row)
                if not isinstance(record, expected_type):
                    raise TransformationValidationError("record_contract_mismatch")
                source_id = record.source_id
                if not isinstance(source_id, str) or not source_id.strip():
                    raise TransformationValidationError(
                        "source_identity_missing", fields=("source_id",)
                    )
            except TransformationValidationError as error:
                rejections.append(
                    TransformationRejection(
                        entity=export.entity,
                        row_number=row_number,
                        disposition="rejected",
                        code=error.code,
                        fields=error.fields,
                    )
                )
                continue
            except (TypeError, ValueError):
                rejections.append(
                    TransformationRejection(
                        entity=export.entity,
                        row_number=row_number,
                        disposition="rejected",
                        code="transformation_failed",
                    )
                )
                continue

            source_hash = self._hash(source_id)
            if source_id in seen_source_ids:
                rejections.append(
                    TransformationRejection(
                        entity=export.entity,
                        row_number=row_number,
                        disposition="duplicate",
                        code="duplicate_source_identity",
                        source_id_sha256=source_hash,
                    )
                )
                continue
            seen_source_ids.add(source_id)
            records.append(record)
        return self._report(
            export=export,
            records=records,
            rejections=rejections,
        )


def housecall_pro_operational_pipeline() -> OperationalTransformationPipeline:
    """Return the exact sealed SOURCE.4 contracts; unknown layouts still fail."""

    from app.operational_migration.hcp_source4_contracts import source4_contracts

    return OperationalTransformationPipeline(
        provider="housecall_pro", contracts=source4_contracts()
    )
