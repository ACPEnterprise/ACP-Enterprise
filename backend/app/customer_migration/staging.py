import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.housecall_pro_adapter import (
    AdaptedCustomerRecord,
    CustomerTransformationReport,
    HousecallProCustomerExportAdapter,
)
from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationChildException,
    CustomerMigrationEvidence,
    CustomerMigrationException,
    CustomerMigrationRun,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerMigrationStagingRun,
    utc_now,
)
from app.customer_migration.repository import CustomerMigrationStagingRepository
from app.platform.permissions.authorization import AuthorizationContext

SOURCE_SYSTEM = "housecall_pro"


class CustomerDryRunReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class CustomerDryRunReport:
    run_id: str
    artifact_id: str
    schema_version: str
    reused_staging: bool
    rows_discovered: int
    rows_accepted: int
    rows_rejected: int
    customers_proposed: int
    contacts_proposed: int
    service_locations_proposed: int
    billing_addresses_proposed: int
    child_exceptions: int
    duplicate_identities: int
    unmapped_fields: int

    def as_dict(self) -> dict[str, str | int | bool]:
        return {
            "run_id": self.run_id,
            "artifact_id": self.artifact_id,
            "schema_version": self.schema_version,
            "reused_staging": self.reused_staging,
            "rows_discovered": self.rows_discovered,
            "rows_accepted": self.rows_accepted,
            "rows_rejected": self.rows_rejected,
            "customers_proposed": self.customers_proposed,
            "contacts_proposed": self.contacts_proposed,
            "service_locations_proposed": self.service_locations_proposed,
            "billing_addresses_proposed": self.billing_addresses_proposed,
            "child_exceptions": self.child_exceptions,
            "duplicate_identities": self.duplicate_identities,
            "unmapped_fields": self.unmapped_fields,
        }


def _json_payload(model: BaseModel) -> dict[str, object]:
    return model.model_dump(mode="json")


def _payload_sha256(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class CustomerAdapterDryRunService:
    def __init__(
        self,
        *,
        adapter: HousecallProCustomerExportAdapter | None = None,
        repository: CustomerMigrationStagingRepository | None = None,
    ) -> None:
        self.adapter = adapter or HousecallProCustomerExportAdapter()
        self.repository = repository or CustomerMigrationStagingRepository()

    @staticmethod
    def _counts(report: CustomerTransformationReport) -> dict[str, int]:
        return {
            "customers": len(report.records),
            "contacts": sum(record.contact is not None for record in report.records),
            "service_locations": sum(
                len(record.service_locations) for record in report.records
            ),
            "billing_addresses": sum(
                record.billing_address is not None for record in report.records
            ),
            "child_exceptions": len(report.child_exceptions),
            "unmapped_fields": sum(
                len(record.unmapped_fields) for record in report.records
            ),
        }

    @staticmethod
    def _candidate(
        source_row: CustomerMigrationSourceRow,
        *,
        entity_type: str,
        ordinal: int,
        model: BaseModel,
    ) -> CustomerMigrationCandidate:
        payload = _json_payload(model)
        return CustomerMigrationCandidate(
            source_row_id=source_row.id,
            entity_type=entity_type,
            ordinal=ordinal,
            payload_sha256=_payload_sha256(payload),
            payload=payload,
        )

    async def _stage_record(
        self,
        session: AsyncSession,
        *,
        artifact: CustomerMigrationSourceArtifact,
        record: AdaptedCustomerRecord,
    ) -> CustomerMigrationSourceRow:
        source_row = CustomerMigrationSourceRow(
            artifact_id=artifact.id,
            row_number=record.row_number,
            source_identity=record.source_id,
            source_id_sha256=hashlib.sha256(record.source_id.encode()).hexdigest(),
            source_row_sha256=record.source_row_sha256,
            disposition="accepted",
            reason_code=None,
        )
        self.repository.add_source_row(session, source_row)
        await session.flush()
        self.repository.add_candidate(
            session,
            self._candidate(
                source_row, entity_type="customer", ordinal=0, model=record.customer
            ),
        )
        if record.contact is not None:
            self.repository.add_candidate(
                session,
                self._candidate(
                    source_row, entity_type="contact", ordinal=0, model=record.contact
                ),
            )
        for ordinal, location in enumerate(record.service_locations):
            self.repository.add_candidate(
                session,
                self._candidate(
                    source_row,
                    entity_type="service_location",
                    ordinal=ordinal,
                    model=location,
                ),
            )
        if record.billing_address is not None:
            self.repository.add_candidate(
                session,
                self._candidate(
                    source_row,
                    entity_type="billing_address",
                    ordinal=0,
                    model=record.billing_address,
                ),
            )
        for field_name, value in sorted(record.unmapped_fields.items()):
            field_evidence = {"field_name": field_name, "value": value}
            self.repository.add_evidence(
                session,
                CustomerMigrationEvidence(
                    source_row_id=source_row.id,
                    evidence_type="unmapped_field",
                    evidence_key=field_name,
                    evidence_sha256=_payload_sha256(field_evidence),
                    evidence=field_evidence,
                ),
            )
        for group in record.incomplete_address_groups:
            group_evidence: dict[str, object] = {
                "address_group_number": group.address_group_number,
                "source_fields": group.source_fields,
            }
            self.repository.add_evidence(
                session,
                CustomerMigrationEvidence(
                    source_row_id=source_row.id,
                    evidence_type="incomplete_address_group",
                    evidence_key=str(group.address_group_number),
                    evidence_sha256=group.source_group_sha256,
                    evidence=group_evidence,
                ),
            )
        return source_row

    async def _stage_new_artifact(
        self,
        session: AsyncSession,
        *,
        artifact: CustomerMigrationSourceArtifact,
        report: CustomerTransformationReport,
    ) -> None:
        accepted_rows: dict[str, CustomerMigrationSourceRow] = {}
        for record in report.records:
            source_row = await self._stage_record(
                session, artifact=artifact, record=record
            )
            accepted_rows[source_row.source_id_sha256 or ""] = source_row
        for rejection in report.rejections:
            if rejection.row_number is None or rejection.source_row_sha256 is None:
                raise CustomerDryRunReadinessError(
                    "schema-level rejection cannot be staged as source rows"
                )
            source_row = CustomerMigrationSourceRow(
                artifact_id=artifact.id,
                row_number=rejection.row_number,
                source_identity=None,
                source_id_sha256=rejection.source_id_sha256,
                source_row_sha256=rejection.source_row_sha256,
                disposition=rejection.disposition,
                reason_code=rejection.code,
            )
            self.repository.add_source_row(session, source_row)
        await session.flush()
        for exception in report.child_exceptions:
            resolved_source_row = accepted_rows.get(exception.source_id_sha256)
            if resolved_source_row is None:
                raise CustomerDryRunReadinessError(
                    "child exception parent row could not be resolved"
                )
            self.repository.add_child_exception(
                session,
                CustomerMigrationChildException(
                    source_row_id=resolved_source_row.id,
                    source_id_sha256=exception.source_id_sha256,
                    contract_version=exception.contract_version,
                    address_group_number=exception.address_group_number,
                    missing_fields=list(exception.missing_fields),
                    reason_code=exception.reason_code,
                    evidence_sha256=exception.evidence_sha256,
                ),
            )

    async def _verify_reused_artifact(
        self,
        session: AsyncSession,
        *,
        artifact: CustomerMigrationSourceArtifact,
        report: CustomerTransformationReport,
        counts: dict[str, int],
    ) -> None:
        if (
            artifact.schema_version != report.schema_version
            or artifact.transformation_sha256 != report.transformation_sha256
            or artifact.row_count != report.source
        ):
            raise CustomerDryRunReadinessError(
                "existing artifact staging does not match deterministic transformation"
            )
        persisted_rows = await session.scalar(
            select(func.count())
            .select_from(CustomerMigrationSourceRow)
            .where(CustomerMigrationSourceRow.artifact_id == artifact.id)
        )
        candidate_rows = await session.execute(
            select(
                CustomerMigrationCandidate.entity_type,
                func.count(CustomerMigrationCandidate.id),
            )
            .join(CustomerMigrationSourceRow)
            .where(CustomerMigrationSourceRow.artifact_id == artifact.id)
            .group_by(CustomerMigrationCandidate.entity_type)
        )
        if persisted_rows != report.source:
            raise CustomerDryRunReadinessError(
                "existing artifact row staging is incomplete"
            )
        candidate_counts: dict[str, int] = {
            entity_type: count for entity_type, count in candidate_rows.all()
        }
        expected_candidates = {
            "customer": counts["customers"],
            "contact": counts["contacts"],
            "service_location": counts["service_locations"],
            "billing_address": counts["billing_addresses"],
        }
        if any(
            candidate_counts.get(entity_type, 0) != expected
            for entity_type, expected in expected_candidates.items()
        ):
            raise CustomerDryRunReadinessError(
                "existing artifact candidate staging is incomplete"
            )
        evidence_count = await session.scalar(
            select(func.count())
            .select_from(CustomerMigrationEvidence)
            .join(CustomerMigrationSourceRow)
            .where(CustomerMigrationSourceRow.artifact_id == artifact.id)
        )
        expected_evidence = counts["unmapped_fields"] + counts["child_exceptions"]
        if evidence_count != expected_evidence:
            raise CustomerDryRunReadinessError(
                "existing artifact evidence staging is incomplete"
            )
        child_exception_count = await session.scalar(
            select(func.count())
            .select_from(CustomerMigrationChildException)
            .join(CustomerMigrationSourceRow)
            .where(CustomerMigrationSourceRow.artifact_id == artifact.id)
        )
        if child_exception_count != counts["child_exceptions"]:
            raise CustomerDryRunReadinessError(
                "existing artifact child-exception staging is incomplete"
            )

    async def run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_bytes: bytes,
        expected_source_sha256: str,
    ) -> CustomerDryRunReport:
        report = self.adapter.transform(
            source_bytes, expected_source_sha256=expected_source_sha256
        )
        if report.schema_version is None:
            reason = report.rejections[0].code if report.rejections else "unknown"
            raise CustomerDryRunReadinessError(
                f"source artifact failed closed validation: {reason}"
            )
        active_branch = context.active_branch
        if active_branch is None:
            raise CustomerDryRunReadinessError("an active branch is required")
        if active_branch.company_id != context.company.id:
            raise CustomerDryRunReadinessError(
                "active branch does not belong to company"
            )
        counts = self._counts(report)
        async with factory() as session, session.begin():
            artifact = await self.repository.find_artifact(
                session,
                company_id=context.company.id,
                branch_id=active_branch.id,
                source_system=SOURCE_SYSTEM,
                source_sha256=report.source_sha256,
            )
            reused = artifact is not None
            if artifact is None:
                artifact = CustomerMigrationSourceArtifact(
                    company_id=context.company.id,
                    branch_id=active_branch.id,
                    source_system=SOURCE_SYSTEM,
                    source_sha256=report.source_sha256,
                    schema_version=report.schema_version,
                    transformation_sha256=report.transformation_sha256,
                    byte_size=len(source_bytes),
                    row_count=report.source,
                )
                self.repository.add_artifact(session, artifact)
                await session.flush()
                await self._stage_new_artifact(
                    session, artifact=artifact, report=report
                )
            else:
                await self._verify_reused_artifact(
                    session, artifact=artifact, report=report, counts=counts
                )
            run = CustomerMigrationRun(
                company_id=context.company.id,
                branch_id=active_branch.id,
                initiated_by_user_id=context.user.id,
                source_system=SOURCE_SYSTEM,
                source_sha256=report.source_sha256,
                mode="dry_run",
                status="completed",
                source_count=report.source,
                accepted_count=report.accepted,
                rejected_count=report.rejected,
                duplicate_count=report.duplicate,
                unresolved_count=0,
                completed_at=utc_now(),
            )
            session.add(run)
            await session.flush()
            self.repository.add_staging_run(
                session,
                CustomerMigrationStagingRun(
                    run_id=run.id,
                    artifact_id=artifact.id,
                    reused_staging=reused,
                    customers_proposed=counts["customers"],
                    contacts_proposed=counts["contacts"],
                    service_locations_proposed=counts["service_locations"],
                    billing_addresses_proposed=counts["billing_addresses"],
                    child_exception_count=counts["child_exceptions"],
                    unmapped_field_count=counts["unmapped_fields"],
                ),
            )
            for rejection in report.rejections:
                if rejection.row_number is None:
                    continue
                session.add(
                    CustomerMigrationException(
                        run_id=run.id,
                        row_number=rejection.row_number,
                        entity_type="customer",
                        source_id_sha256=rejection.source_id_sha256,
                        disposition=rejection.disposition,
                        reason_code=rejection.code,
                        detail="Source row failed deterministic transformation validation.",
                    )
                )
        return CustomerDryRunReport(
            run_id=str(run.id),
            artifact_id=str(artifact.id),
            schema_version=report.schema_version,
            reused_staging=reused,
            rows_discovered=report.source,
            rows_accepted=report.accepted,
            rows_rejected=report.rejected,
            customers_proposed=counts["customers"],
            contacts_proposed=counts["contacts"],
            service_locations_proposed=counts["service_locations"],
            billing_addresses_proposed=counts["billing_addresses"],
            child_exceptions=counts["child_exceptions"],
            duplicate_identities=report.duplicate,
            unmapped_fields=counts["unmapped_fields"],
        )
