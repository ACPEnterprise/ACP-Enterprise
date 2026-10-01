"""Bounded staging of sealed HCP Employee authority into Workforce review."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.hcp_migration2b import (
    EmployeeCrosswalkCommand,
    canonical_sha256,
)
from app.operational_migration.hcp_migration2c import EMPLOYEE_NAMESPACE
from app.operational_migration.models import (
    HcpEmployeeSourceCrosswalk,
    HcpMigrationMasterRun,
)
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import MigrationPermission

CONTRACT = "hcp-workforce-source-authority/v1"
AUTHORITY_PATH = (
    Path(__file__).parent
    / "authorities"
    / "hcp-workforce-source-authority.v1.json"
)


@dataclass(frozen=True, slots=True)
class WorkforceSourceRecord:
    provider_employee_id: str
    canonical_source_name: str
    source_email: str
    owner_current_email: str | None
    employment_status: str
    status_effective_at: str | None
    source_as_of: str
    source_snapshot_digest: str
    source_record_digest: str
    owner_disposition: str

    @property
    def creates_candidate(self) -> bool:
        return self.employment_status == "ACTIVE"

    @property
    def crosswalk_disposition(self) -> str:
        return (
            "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE"
            if self.creates_candidate
            else "EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS"
        )

    @property
    def names(self) -> tuple[str, str]:
        first, separator, last = self.canonical_source_name.strip().rpartition(" ")
        if not separator or not first or not last:
            raise ValueError("source Employee name must contain first and last names")
        return first, last

    def validate(self) -> None:
        if not self.provider_employee_id.startswith("pro_"):
            raise ValueError("exact HCP provider Employee identity is required")
        for name, value in (
            ("source_snapshot_digest", self.source_snapshot_digest),
            ("source_record_digest", self.source_record_digest),
        ):
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        _ = self.names
        if self.employment_status not in {"ACTIVE", "TERMINATED"}:
            raise ValueError("unsupported source employment status")
        if self.employment_status == "TERMINATED":
            if self.owner_current_email is not None or self.status_effective_at is None:
                raise ValueError("terminated source Employee cannot be invitational")
        elif self.owner_disposition not in {
            "SAFE_CREATE",
            "OWNER_IDENTITY_DECISION_REQUIRED",
        }:
            raise ValueError("active source Employee disposition is invalid")


@dataclass(frozen=True, slots=True)
class WorkforceSourcePacket:
    source_package_digest: str
    branch_code: str
    records: tuple[WorkforceSourceRecord, ...]
    digest: str

    @classmethod
    def load(cls, path: Path = AUTHORITY_PATH) -> WorkforceSourcePacket:
        raw: dict[str, Any] = json.loads(path.read_text())
        if raw.get("contract") != CONTRACT:
            raise ValueError("unsupported Workforce source authority contract")
        records = tuple(WorkforceSourceRecord(**item) for item in raw["records"])
        packet = cls(
            source_package_digest=raw["source_package_digest"],
            branch_code=raw["branch_code"],
            records=records,
            digest=canonical_sha256(raw),
        )
        packet.validate()
        return packet

    def validate(self) -> None:
        if len(self.source_package_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.source_package_digest
        ):
            raise ValueError("Workforce authority requires a sealed SOURCE.4 digest")
        if self.branch_code != "MAIN" or len(self.records) != 7:
            raise ValueError("Workforce authority cardinality or Branch is invalid")
        if len({item.provider_employee_id for item in self.records}) != len(self.records):
            raise ValueError("duplicate HCP Employee identity")
        for record in self.records:
            record.validate()
        if sum(item.employment_status == "ACTIVE" for item in self.records) != 6:
            raise ValueError("exactly six active source identities are required")
        if sum(item.employment_status == "TERMINATED" for item in self.records) != 1:
            raise ValueError("exactly one terminated source identity is required")
        if sum(
            item.owner_disposition == "OWNER_IDENTITY_DECISION_REQUIRED"
            for item in self.records
        ) != 1:
            raise ValueError("exactly one owner identity decision is required")


@dataclass(frozen=True, slots=True)
class WorkforceSourceStagingResult:
    packet_digest: str
    staged: int
    created_candidates: int
    terminated: int
    owner_decisions: int
    replayed: int


class WorkforceSourceStagingService:
    async def stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        packet: WorkforceSourcePacket,
    ) -> WorkforceSourceStagingResult:
        packet.validate()
        if not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL):
            raise ValueError("Migration execution authority is required")
        if context.active_branch is None or context.active_branch.code != packet.branch_code:
            raise ValueError("MAIN Branch authority is required")
        master = await session.scalar(
            select(HcpMigrationMasterRun)
            .where(
                HcpMigrationMasterRun.id == master_run_id,
                HcpMigrationMasterRun.company_id == context.company.id,
                HcpMigrationMasterRun.branch_id == context.active_branch.id,
                HcpMigrationMasterRun.package_digest == packet.source_package_digest,
                HcpMigrationMasterRun.status == "completed_current_operational",
            )
            .with_for_update()
        )
        if master is None:
            raise ValueError("completed current-operational SOURCE.4 lineage is required")

        created_candidates = 0
        replayed = 0
        for record in packet.records:
            existing = await session.scalar(
                select(HcpEmployeeSourceCrosswalk).where(
                    HcpEmployeeSourceCrosswalk.company_id == context.company.id,
                    HcpEmployeeSourceCrosswalk.native_employee_id
                    == record.provider_employee_id,
                    HcpEmployeeSourceCrosswalk.evidence_version == 1,
                )
            )
            employee_id = (
                uuid5(
                    EMPLOYEE_NAMESPACE,
                    f"{context.company.id}:{record.provider_employee_id}",
                )
                if record.creates_candidate
                else None
            )
            command = EmployeeCrosswalkCommand(
                native_employee_id=record.provider_employee_id,
                disposition=record.crosswalk_disposition,
                source_digest=record.source_record_digest,
                owner_receipt_digest=packet.digest,
                employee_id=employee_id,
                package_digest=packet.source_package_digest,
            )
            if existing is not None:
                if (
                    existing.master_run_id != master_run_id
                    or existing.evidence_digest != command.evidence_digest
                    or existing.employee_id != employee_id
                ):
                    raise ValueError("conflicting HCP Employee source authority")
                replayed += 1
                continue
            if employee_id is not None:
                if await session.get(Employee, employee_id) is not None:
                    raise ValueError("deterministic Employee exists without source authority")
                first_name, last_name = record.names
                session.add(
                    Employee(
                        id=employee_id,
                        company_id=context.company.id,
                        membership_id=None,
                        home_branch_id=context.active_branch.id,
                        employee_number=f"HCP-{record.source_record_digest[:16].upper()}",
                        first_name=first_name,
                        last_name=last_name,
                        display_name=record.canonical_source_name,
                        job_title=None,
                        employee_type="employee",
                        status="inactive",
                        hire_date=None,
                        termination_date=None,
                        created_by_user_id=context.user.id,
                        updated_by_user_id=context.user.id,
                    )
                )
                await session.flush()
                created_candidates += 1
            session.add(
                HcpEmployeeSourceCrosswalk(
                    company_id=context.company.id,
                    branch_id=context.active_branch.id,
                    master_run_id=master_run_id,
                    prior_evidence_id=None,
                    employee_id=employee_id,
                    native_employee_id=record.provider_employee_id,
                    disposition=record.crosswalk_disposition,
                    package_digest=packet.source_package_digest,
                    source_digest=record.source_record_digest,
                    owner_receipt_digest=packet.digest,
                    evidence_digest=command.evidence_digest,
                    evidence_version=1,
                )
            )
            await session.flush()
        return WorkforceSourceStagingResult(
            packet_digest=packet.digest,
            staged=len(packet.records),
            created_candidates=created_candidates,
            terminated=sum(item.employment_status == "TERMINATED" for item in packet.records),
            owner_decisions=sum(
                item.owner_disposition == "OWNER_IDENTITY_DECISION_REQUIRED"
                for item in packet.records
            ),
            replayed=replayed,
        )


workforce_source_staging_service = WorkforceSourceStagingService()
