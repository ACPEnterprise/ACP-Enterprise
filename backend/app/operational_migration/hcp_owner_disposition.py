"""Machine-bindable HCP.MIGRATION.1A owner and target-readiness contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

CONTRACT_VERSION = "hcp-owner-disposition/v1"


class BlockerClass(StrEnum):
    OWNER_DECISION = "owner_decision"
    EXTERNAL_EVIDENCE = "external_evidence"
    EXPLICIT_EXCEPTION = "explicit_exception"


@dataclass(frozen=True)
class DispositionAlternative:
    identifier: str
    migration_effect: str
    consequence: str
    reversible_before_cutover: bool

    def __post_init__(self) -> None:
        if not self.identifier or not self.migration_effect or not self.consequence:
            raise ValueError("complete disposition alternative evidence is required")


@dataclass(frozen=True)
class OwnerDecisionGroup:
    identifier: str
    affected_count: int
    reason: str
    evidence_sha256: str
    recommended_default: str | None
    alternatives: tuple[DispositionAlternative, ...]
    representative_native_id_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.identifier.startswith("HCP1A.") or self.affected_count < 1:
            raise ValueError("stable HCP1A decision identity and count are required")
        if len(self.evidence_sha256) != 64 or not self.alternatives:
            raise ValueError("decision group evidence is incomplete")
        ids = {item.identifier for item in self.alternatives}
        if len(ids) != len(self.alternatives):
            raise ValueError("alternative identifiers must be unique")
        if self.recommended_default is not None and self.recommended_default not in ids:
            raise ValueError("recommended default must identify an alternative")

    @property
    def binding_digest(self) -> str:
        return canonical_sha256(
            {"contract": CONTRACT_VERSION, "decision": asdict(self)}
        )


@dataclass(frozen=True)
class OwnerDecisionBinding:
    """An explicit owner choice bound to the exact reviewed decision group."""

    group_identifier: str
    binding_digest: str
    selected_alternative: str
    bound_at: datetime
    authority: str

    @classmethod
    def bind(
        cls,
        group: OwnerDecisionGroup,
        *,
        binding_digest: str,
        selected_alternative: str,
        authority: str,
        bound_at: datetime | None = None,
    ) -> OwnerDecisionBinding:
        if binding_digest != group.binding_digest:
            raise ValueError(
                "binding digest does not match the reviewed decision group"
            )
        if selected_alternative not in {
            alternative.identifier for alternative in group.alternatives
        }:
            raise ValueError(
                "selected alternative is not defined by the decision group"
            )
        if not authority.strip():
            raise ValueError("binding authority is required")
        return cls(
            group_identifier=group.identifier,
            binding_digest=binding_digest,
            selected_alternative=selected_alternative,
            bound_at=bound_at or datetime.now(timezone.utc),
            authority=authority.strip(),
        )

    @property
    def receipt_digest(self) -> str:
        return canonical_sha256({"contract": CONTRACT_VERSION, "binding": asdict(self)})


@dataclass(frozen=True)
class RecordDisposition:
    native_id: str
    selected_alternative: str
    reason: str


@dataclass(frozen=True)
class OwnerDecisionRecordBinding:
    """Bind a mixed group without treating distinct source identities alike."""

    group_identifier: str
    binding_digest: str
    record_dispositions: tuple[RecordDisposition, ...]
    bound_at: datetime
    authority: str

    @classmethod
    def bind(
        cls,
        group: OwnerDecisionGroup,
        *,
        binding_digest: str,
        record_dispositions: tuple[RecordDisposition, ...],
        authority: str,
        bound_at: datetime | None = None,
    ) -> OwnerDecisionRecordBinding:
        if binding_digest != group.binding_digest:
            raise ValueError(
                "binding digest does not match the reviewed decision group"
            )
        if len(record_dispositions) != group.affected_count:
            raise ValueError("every affected source identity requires a disposition")
        native_ids = [item.native_id for item in record_dispositions]
        if len(native_ids) != len(set(native_ids)) or any(
            not item for item in native_ids
        ):
            raise ValueError("record disposition native identities must be unique")
        alternatives = {item.identifier for item in group.alternatives}
        if any(
            item.selected_alternative not in alternatives or not item.reason.strip()
            for item in record_dispositions
        ):
            raise ValueError("record disposition alternative and reason are required")
        return cls(
            group_identifier=group.identifier,
            binding_digest=binding_digest,
            record_dispositions=tuple(
                sorted(record_dispositions, key=lambda item: item.native_id)
            ),
            bound_at=bound_at or datetime.now(timezone.utc),
            authority=authority.strip(),
        )

    @property
    def receipt_digest(self) -> str:
        return canonical_sha256({"contract": CONTRACT_VERSION, "binding": asdict(self)})


@dataclass(frozen=True)
class BranchScopeBinding:
    group_identifier: str
    binding_digest: str
    selected_alternative: str
    company_id: UUID
    branch_id: UUID
    source_business_unit_to_branch: tuple[tuple[str, UUID], ...]
    default_branch_for_missing_business_unit: UUID
    preserve_source_business_unit_evidence: bool
    bound_at: datetime
    authority: str

    @classmethod
    def bind(
        cls,
        group: OwnerDecisionGroup,
        *,
        binding_digest: str,
        company_id: UUID,
        branch_id: UUID,
        source_business_unit_ids: tuple[str, ...],
        authority: str,
        bound_at: datetime | None = None,
    ) -> BranchScopeBinding:
        alternative = "OWNER_MAP_BUSINESS_UNIT_AND_DEFAULT"
        if binding_digest != group.binding_digest:
            raise ValueError(
                "binding digest does not match the reviewed decision group"
            )
        if alternative not in {item.identifier for item in group.alternatives}:
            raise ValueError("Branch mapping alternative is not defined")
        if not source_business_unit_ids or len(source_business_unit_ids) != len(
            set(source_business_unit_ids)
        ):
            raise ValueError("unique source Business Unit identities are required")
        if any(not item.startswith("buu_") for item in source_business_unit_ids):
            raise ValueError("native HCP Business Unit identities are required")
        return cls(
            group_identifier=group.identifier,
            binding_digest=binding_digest,
            selected_alternative=alternative,
            company_id=company_id,
            branch_id=branch_id,
            source_business_unit_to_branch=tuple(
                (item, branch_id) for item in sorted(source_business_unit_ids)
            ),
            default_branch_for_missing_business_unit=branch_id,
            preserve_source_business_unit_evidence=True,
            bound_at=bound_at or datetime.now(timezone.utc),
            authority=authority.strip(),
        )

    @property
    def receipt_digest(self) -> str:
        return canonical_sha256({"contract": CONTRACT_VERSION, "binding": asdict(self)})


@dataclass(frozen=True)
class UnlinkedEstimateExceptionBinding:
    group_identifier: str
    binding_digest: str
    selected_alternative: str
    exception_contract_identifier: str
    native_estimate_ids: tuple[str, ...]
    prohibited_effects: tuple[str, ...]
    preserve_source_evidence: bool
    reversible_before_cutover: bool
    bound_at: datetime
    authority: str

    @classmethod
    def bind(
        cls,
        group: OwnerDecisionGroup,
        *,
        binding_digest: str,
        native_estimate_ids: tuple[str, ...],
        authority: str,
        bound_at: datetime | None = None,
    ) -> UnlinkedEstimateExceptionBinding:
        alternative = "MIGRATE_UNLINKED_EXCEPTION_IF_SUPPORTED"
        if binding_digest != group.binding_digest:
            raise ValueError(
                "binding digest does not match the reviewed decision group"
            )
        if alternative not in {item.identifier for item in group.alternatives}:
            raise ValueError("unlinked Estimate alternative is not defined")
        if len(native_estimate_ids) != 24 or len(set(native_estimate_ids)) != 24:
            raise ValueError("the reviewed 24 unique Estimate identities are required")
        if any(not item.startswith("csr_") for item in native_estimate_ids):
            raise ValueError("native HCP Estimate identities are required")
        return cls(
            group_identifier=group.identifier,
            binding_digest=binding_digest,
            selected_alternative=alternative,
            exception_contract_identifier="UNLINKED_NON_OPERATIONAL_ESTIMATE",
            native_estimate_ids=tuple(sorted(native_estimate_ids)),
            prohibited_effects=(
                "accepted_accounting_truth",
                "job_activation",
                "job_completion",
                "job_creation",
                "job_dispatch",
                "job_financial_posting",
                "job_scheduling",
            ),
            preserve_source_evidence=True,
            reversible_before_cutover=True,
            bound_at=bound_at or datetime.now(timezone.utc),
            authority=authority.strip(),
        )

    @property
    def receipt_digest(self) -> str:
        return canonical_sha256({"contract": CONTRACT_VERSION, "binding": asdict(self)})


@dataclass(frozen=True)
class NonProductionTarget:
    environment: str
    database_url: str
    expected_database: str
    production_access_enabled: bool
    preview_access_enabled: bool
    initially_empty_required: bool

    def validate(self) -> str:
        parsed = urlparse(self.database_url)
        database = parsed.path.removeprefix("/")
        if self.environment != "migration_rehearsal":
            raise ValueError("target must be explicitly migration_rehearsal")
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("target host is not isolated")
        if database != self.expected_database or database != "acp_hcp_rehearsal_import":
            raise ValueError("target database identity is not approved")
        if self.production_access_enabled or self.preview_access_enabled:
            raise ValueError("Preview and Production access must be disabled")
        if not self.initially_empty_required:
            raise ValueError("an initially empty target is required")
        return canonical_sha256(
            {
                "environment": self.environment,
                "scheme": parsed.scheme,
                "hostname": parsed.hostname,
                "port": parsed.port,
                "database": database,
                "production_access_enabled": self.production_access_enabled,
                "preview_access_enabled": self.preview_access_enabled,
                "initially_empty_required": self.initially_empty_required,
            }
        )


@dataclass(frozen=True)
class RehearsalScope:
    company_id: UUID
    branch_id: UUID
    company_code: str
    branch_code: str


async def initialize_rehearsal_scope(
    session: Any,
    *,
    target: NonProductionTarget,
    company_name: str,
    company_code: str,
    branch_name: str,
    branch_code: str,
    timezone_name: str,
) -> RehearsalScope:
    """Create only the tenancy prerequisite in an empty isolated rehearsal DB."""
    from sqlalchemy import func, select

    from app.platform.bootstrap.repository import BOOTSTRAP_ADVISORY_LOCK_ID
    from app.platform.branch.models import Branch
    from app.platform.company.models import Company

    target.validate()
    normalized_company_code = company_code.strip().upper()
    normalized_branch_code = branch_code.strip().upper()
    if not all(
        value.strip()
        for value in (
            company_name,
            normalized_company_code,
            branch_name,
            normalized_branch_code,
            timezone_name,
        )
    ):
        raise ValueError("complete Company/Branch rehearsal identity is required")

    async with session.begin():
        await session.execute(
            select(func.pg_advisory_xact_lock(BOOTSTRAP_ADVISORY_LOCK_ID))
        )
        company_count = await session.scalar(select(func.count()).select_from(Company))
        branch_count = await session.scalar(select(func.count()).select_from(Branch))
        if company_count or branch_count:
            raise ValueError("rehearsal scope initialization requires an empty target")
        company = Company(
            name=company_name.strip(),
            code=normalized_company_code,
            status="active",
            timezone=timezone_name.strip(),
        )
        session.add(company)
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name=branch_name.strip(),
            code=normalized_branch_code,
            status="active",
            timezone=timezone_name.strip(),
            is_primary=True,
        )
        session.add(branch)
        await session.flush()
        return RehearsalScope(
            company_id=company.id,
            branch_id=branch.id,
            company_code=company.code,
            branch_code=branch.code,
        )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode()
    ).hexdigest()


def seal_owner_packet(groups: tuple[OwnerDecisionGroup, ...]) -> str:
    identifiers = [group.identifier for group in groups]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate owner decision identifier")
    return canonical_sha256(
        {
            "contract": CONTRACT_VERSION,
            "groups": [
                {**asdict(group), "binding_digest": group.binding_digest}
                for group in sorted(groups, key=lambda item: item.identifier)
            ],
        }
    )
