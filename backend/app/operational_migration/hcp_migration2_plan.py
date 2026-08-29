"""Deterministic protected SOURCE.4 execution-plan construction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationChildException,
    CustomerMigrationRun,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.financials.models import Estimate, Invoice, Payment
from app.jobs.models import Job
from app.operational_migration.hcp_hybrid_customer import canonical_sha256
from app.operational_migration.hcp_migration2_runner import (
    HcpMigration2ExecutionPlan,
    HcpMigration2Runner,
    ProtectedSource4Loader,
    SafeEvidenceError,
    _file_sha256,
    _safe_json,
)
from app.operational_migration.hcp_migration2a import (
    UnlinkedEstimateEvidenceCommand,
)
from app.operational_migration.hcp_migration2b import (
    MASTER_CONTRACT,
    MASTER_NAMESPACE,
    HoldCommand,
    MasterRunCommand,
    PlanOutcomeCommand,
)
from app.operational_migration.hcp_migration2c import (
    ORCHESTRATOR_VERSION,
    STAGING_NAMESPACE,
    CompletionRequirements,
    EmployeeCandidateCommand,
)
from app.operational_migration.hcp_migration2i import (
    ChildOutcomeCounts,
    ChildRepairPlan,
    requalify_financial_commands,
    requalify_operational_commands,
)
from app.operational_migration.hcp_migration2k1 import (
    AppointmentCorrectionCheckpoint,
    AppointmentSequencePlan,
    RetainedAppointmentProjection,
    SupersedingAppointmentRepairPlan,
    build_appointment_sequence_plan,
    qualify_retained_checkpoint,
)
from app.operational_migration.hcp_owner_disposition import NonProductionTarget
from app.operational_migration.hcp_rehearsal_authority import (
    ACTOR_ID,
    BRANCH_ID,
    COMPANY_ID,
)
from app.operational_migration.hcp_source4_contracts import (
    APPOINTMENT_COLUMNS,
    ESTIMATE_COLUMNS,
    INVOICE_COLUMNS,
    JOB_COLUMNS,
    NOTE_COLUMNS,
    PAYMENT_COLUMNS,
)
from app.operational_migration.models import (
    HcpMigrationChildAdmission,
    HcpMigrationChildRepair,
    HcpMigrationHold,
    HcpMigrationMasterRun,
    HcpMigrationPlanOutcome,
    OperationalMigrationRun,
)
from app.operational_migration.transformation import (
    ParsedSourceExport,
    TransformationReport,
    housecall_pro_operational_pipeline,
)
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment

BUILDER_VERSION = "hcp-migration-2g-plan-builder/v1"
PLAN_NAMESPACE = UUID("97f2dc73-7473-5275-9ea2-dfc24fb0ea58")


@dataclass(frozen=True)
class HcpMigration2RepairAuthority:
    master_run_id: UUID
    original_plan_id: UUID
    original_plan_digest: str
    repair_plan_digest: str
    customer_child_run_id: UUID
    operational_child_run_id: UUID
    financial_child_run_id: UUID
    history_child_run_id: UUID


@dataclass(frozen=True)
class HcpMigration2RepairResult:
    state: str
    master_run_id: UUID
    master_status: str
    repair_plan_digest: str
    operational_repair_run_id: UUID
    financial_repair_run_id: UUID
    reconciliation_digest: str | None

    def safe_output(self) -> dict[str, object]:
        return {
            "state": self.state,
            "master_run_id": str(self.master_run_id),
            "master_status": self.master_status,
            "repair_plan_digest": self.repair_plan_digest,
            "operational_repair_run_id": str(self.operational_repair_run_id),
            "financial_repair_run_id": str(self.financial_repair_run_id),
            "reconciliation_digest": self.reconciliation_digest,
        }


SCHEMA_HEAD = "f3a5c7e9b102"

T = TypeVar("T")


@dataclass(frozen=True)
class HcpMigration2PlanSummary:
    plan_id: UUID
    plan_digest: str
    builder_version: str
    source_counts: dict[str, int]
    command_counts: dict[str, int]
    outcome_counts: dict[str, dict[str, int]]

    def safe_output(self) -> dict[str, object]:
        return asdict(self)


class RehearsalAdmissionState(StrEnum):
    NO_MASTER = "NO_MASTER"
    MATCHING_INCOMPLETE_MASTER = "MATCHING_INCOMPLETE_MASTER"
    MATCHING_INCOMPLETE_MASTER_WITH_ACCEPTED_REPAIR_PLAN = (
        "MATCHING_INCOMPLETE_MASTER_WITH_ACCEPTED_REPAIR_PLAN"
    )
    COMPLETED_MASTER = "COMPLETED_MASTER"
    CONTRADICTORY_MASTER = "CONTRADICTORY_MASTER"
    MULTIPLE_UNEXPECTED_MASTERS = "MULTIPLE_UNEXPECTED_MASTERS"


def _objects(value: object, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping) or not isinstance(value.get(key), list):
        raise SafeEvidenceError("protected_collection_layout_invalid", "0" * 64)
    rows = value[key]
    if any(not isinstance(item, Mapping) for item in rows):
        raise SafeEvidenceError("protected_collection_row_invalid", "1" * 64)
    return [dict(item) for item in rows if isinstance(item, Mapping)]


def _unique(rows: Sequence[Mapping[str, object]], prefix: str) -> None:
    identities: set[str] = set()
    for row in rows:
        identity = row.get("id")
        if not isinstance(identity, str) or not identity.startswith(prefix):
            raise SafeEvidenceError("native_identity_invalid", canonical_sha256(row))
        if identity in identities:
            raise SafeEvidenceError(
                "duplicate_native_identity",
                hashlib.sha256(identity.encode()).hexdigest(),
            )
        identities.add(identity)


def _command_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _report(
    *, entity: str, version: str, columns: tuple[str, ...], rows: list[dict[str, Any]]
) -> TransformationReport:
    ordered = sorted(rows, key=lambda row: str(row.get("id", "")))
    source_bytes = canonical_sha256(ordered).encode()
    export = ParsedSourceExport.from_source_bytes(
        entity=entity,  # type: ignore[arg-type]
        version=version,
        columns=columns,
        rows=ordered,
        source_bytes=source_bytes,
    )
    result = housecall_pro_operational_pipeline().transform(
        export, expected_source_sha256=export.source_sha256
    )
    return result


def _typed(report: TransformationReport, expected: type[T]) -> tuple[T, ...]:
    records = tuple(item for item in report.records if isinstance(item, expected))
    if len(records) != len(report.records):
        raise SafeEvidenceError(
            "transformation_record_type_invalid", report.transformation_sha256
        )
    return records


class HcpMigration2ExecutionPlanBuilder:
    """Build the sole complete plan from sealed evidence without emitting rows."""

    def __init__(
        self,
        *,
        package_root: Path,
        control_csv: Path,
        migration1a_root: Path,
    ) -> None:
        self.package_root = package_root.resolve()
        self.migration1a_root = migration1a_root.resolve()
        self.loader = ProtectedSource4Loader(self.package_root, control_csv)

    def _pages(self, entity: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted((self.package_root / "raw" / entity).glob("page-*.json")):
            rows.extend(_objects(_safe_json(path), entity))
        return rows

    def _bindings(self) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        root = self.migration1a_root / "owner" / "bindings"
        receipts = self.loader.verify_owner_receipts(root)
        values: dict[str, dict[str, Any]] = {}
        for path in sorted(root.glob("*.json")):
            value = _safe_json(path)
            if not isinstance(value, Mapping):
                raise SafeEvidenceError("owner_receipt_shape_invalid", "2" * 64)
            identifier = value.get("group_identifier")
            if isinstance(identifier, str):
                values[identifier] = dict(value)
        return receipts, values

    def _appointments(
        self, jobs: Mapping[str, Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        manifest = _safe_json(
            self.package_root / "relationship-appointments-manifest.json"
        )
        if not isinstance(manifest, Mapping) or not isinstance(
            manifest.get("artifacts"), list
        ):
            raise SafeEvidenceError("appointment_manifest_layout_invalid", "3" * 64)
        by_hash = {
            hashlib.sha256(identity.encode()).hexdigest(): row
            for identity, row in jobs.items()
        }
        files: dict[str, Path] = {}
        for folder in ("job-appointments-2023-plus", "job-appointments-retry"):
            for path in (self.package_root / "raw" / folder).glob("*.json"):
                files[_file_sha256(path)] = path
        result: list[dict[str, Any]] = []
        for artifact in manifest["artifacts"]:
            if not isinstance(artifact, Mapping) or artifact.get("http_status") != 200:
                continue
            job = by_hash.get(str(artifact.get("job_identity_sha256")))
            digest = artifact.get("effective_retry_sha256") or artifact.get(
                "response_sha256"
            )
            selected_path = files.get(str(digest))
            if job is None or selected_path is None:
                raise SafeEvidenceError(
                    "appointment_parent_evidence_missing", canonical_sha256(artifact)
                )
            customer = job.get("customer")
            address = job.get("address")
            if not isinstance(customer, Mapping) or not isinstance(address, Mapping):
                raise SafeEvidenceError(
                    "appointment_parent_layout_invalid", canonical_sha256(job)
                )
            for item in _objects(_safe_json(selected_path), "appointments"):
                item.update(
                    {
                        "anytime": False,
                        "arrival_window_minutes": item.get("arrival_window_minutes"),
                        "start_date": None,
                        "_source_digest": canonical_sha256(item),
                        "_source_job_id": job["id"],
                        "_source_customer_id": customer.get("id"),
                        "_source_location_id": address.get("id"),
                        "_job_status": job.get("work_status"),
                        "_owner_disposition": "MIGRATE_SOURCE_REPORTED",
                    }
                )
                result.append(item)
        _unique(result, "appt_")
        return result

    def build(
        self,
        *,
        baseline_counts: dict[str, int],
        company_id: UUID = COMPANY_ID,
        branch_id: UUID = BRANCH_ID,
        actor_id: UUID = ACTOR_ID,
    ) -> tuple[HcpMigration2ExecutionPlan, HcpMigration2PlanSummary]:
        if (company_id, branch_id, actor_id) != (COMPANY_ID, BRANCH_ID, ACTOR_ID):
            raise SafeEvidenceError("sanctioned_scope_mismatch", "4" * 64)
        customers = self.loader.load_customers()
        receipts, bindings = self._bindings()
        jobs_raw = self._pages("jobs")
        estimates_raw = self._pages("estimates")
        invoices_raw = self._pages("invoices")
        employees_raw = self._pages("employees")
        _unique(jobs_raw, "job_")
        _unique(estimates_raw, "csr_")
        _unique(invoices_raw, "invoice_")
        _unique(employees_raw, "pro_")
        jobs_by_id = {str(row["id"]): row for row in jobs_raw}

        crosswalk = _safe_json(
            self.package_root / "reconciliation" / "job-native-control-crosswalk.json"
        )
        if not isinstance(crosswalk, list):
            raise SafeEvidenceError("job_crosswalk_layout_invalid", "5" * 64)
        held_jobs = {
            str(row["native_job_id"])
            for row in crosswalk
            if isinstance(row, Mapping)
            and row.get("history_layer") == "day_one_cutover_state"
            and row.get("control_classification") == "ABSENT"
            and row.get("source_status") in {"pro canceled", "user canceled"}
            and row.get("outstanding_balance_source_value") not in {0, "0", None}
        }
        representative = _safe_json(
            self.migration1a_root / "owner" / "representative-examples.json"
        )
        if not isinstance(representative, Mapping) or not isinstance(
            representative.get("HCP1A.RECENT_ZERO_BALANCE_CANCELED_JOBS.V1"), list
        ):
            raise SafeEvidenceError("job_owner_evidence_missing", "6" * 64)
        history_jobs = {
            str(row["native_job_id"])
            for row in representative["HCP1A.RECENT_ZERO_BALANCE_CANCELED_JOBS.V1"]
            if isinstance(row, Mapping)
        }
        if len(held_jobs) != 296 or len(history_jobs) != 3:
            raise SafeEvidenceError(
                "job_owner_disposition_accounting_mismatch",
                canonical_sha256([len(held_jobs), len(history_jobs)]),
            )
        job_rows: list[dict[str, Any]] = []
        for source in jobs_raw:
            if source["id"] in held_jobs:
                continue
            disposition = (
                "MIGRATE_CANCELED_HISTORY_ONLY"
                if source["id"] in history_jobs
                else "MIGRATE_SOURCE_REPORTED"
            )
            job_rows.append(
                {
                    **source,
                    "_source_digest": canonical_sha256(source),
                    "_owner_disposition": disposition,
                }
            )
        job_report = _report(
            entity="job",
            version="hcp_source4_jobs_api_v1",
            columns=JOB_COLUMNS,
            rows=job_rows,
        )
        job_parent_exceptions = tuple(
            item
            for item in job_report.rejections
            if item.code == "native_identity_invalid" and item.fields == ("address.id",)
        )
        if job_report.duplicate or len(job_parent_exceptions) != job_report.rejected:
            raise SafeEvidenceError(
                "job_transformation_incomplete", job_report.transformation_sha256
            )

        all_appointment_rows = self._appointments(jobs_by_id)
        appointment_rows = [
            row
            for row in all_appointment_rows
            if row["_source_job_id"] not in held_jobs
        ]
        appointment_report = _report(
            entity="appointment",
            version="hcp_source4_job_appointments_api_v1",
            columns=APPOINTMENT_COLUMNS,
            rows=appointment_rows,
        )
        appointment_parent_exceptions = tuple(
            item
            for item in appointment_report.rejections
            if item.code == "native_identity_invalid"
            and item.fields == ("_source_location_id",)
        )
        if (
            appointment_report.duplicate
            or len(appointment_parent_exceptions) != appointment_report.rejected
        ):
            raise SafeEvidenceError(
                "appointment_transformation_incomplete",
                appointment_report.transformation_sha256,
            )

        open_work = _safe_json(
            self.migration1a_root.parent
            / "hcp-migration-1-20260828T000000Z"
            / "owner"
            / "open-work.json"
        )
        if not isinstance(open_work, list) or len(open_work) != 278:
            raise SafeEvidenceError("open_work_authority_invalid", "7" * 64)
        open_job_ids = {
            str(item["native_job_id"])
            for item in open_work
            if isinstance(item, Mapping)
        }
        if len(open_job_ids) != 278:
            raise SafeEvidenceError("open_work_identity_conflict", "8" * 64)
        day_one_estimates = _safe_json(
            self.migration1a_root.parent
            / "hcp-migration-1-20260828T000000Z"
            / "owner"
            / "day-one-estimates.json"
        )
        if not isinstance(day_one_estimates, list) or len(day_one_estimates) != 350:
            raise SafeEvidenceError("day_one_estimate_authority_invalid", "9" * 64)
        day_one_ids = {
            str(item["native_estimate_id"])
            for item in day_one_estimates
            if isinstance(item, Mapping)
        }
        open_customer_ids = {
            str(jobs_by_id[identity]["customer"]["id"]) for identity in open_job_ids
        }
        continuity_estimates = {
            str(item["id"]): item
            for item in estimates_raw
            if item["id"] in day_one_ids
            and isinstance(item.get("customer"), Mapping)
            and item["customer"].get("id") in open_customer_ids
        }
        if len(continuity_estimates) != 89:
            raise SafeEvidenceError(
                "estimate_continuity_scope_mismatch",
                canonical_sha256(len(continuity_estimates)),
            )
        option_to_estimate = {
            str(option["id"]): identity
            for identity, estimate in continuity_estimates.items()
            for option in estimate.get("options", [])
            if isinstance(option, Mapping) and isinstance(option.get("id"), str)
        }
        estimate_links: dict[str, set[tuple[str, str]]] = {}
        for job in jobs_raw:
            candidates = {
                job.get("original_estimate_id"),
                *(job.get("original_estimate_uuids") or []),
            }
            for candidate in candidates:
                if isinstance(candidate, str) and candidate in option_to_estimate:
                    estimate_links.setdefault(option_to_estimate[candidate], set()).add(
                        (str(job["id"]), candidate)
                    )
        open_linked = {
            identity: {link for link in links if link[0] in open_job_ids}
            for identity, links in estimate_links.items()
            if any(link[0] in open_job_ids for link in links)
        }
        if len(open_linked) != 22:
            raise SafeEvidenceError(
                "open_linked_estimate_count_mismatch",
                canonical_sha256(len(open_linked)),
            )
        unlinked_binding = bindings["HCP1A.UNLINKED_DAY1_ESTIMATES.V1"]
        unlinked_ids = set(unlinked_binding.get("native_estimate_ids", []))
        estimate_rows: list[dict[str, Any]] = []
        unlinked_commands: list[UnlinkedEstimateEvidenceCommand] = []
        linked_relationship_exceptions = 0
        for source in estimates_raw:
            raw_options = source.get("options")
            options: list[object] = raw_options if isinstance(raw_options, list) else []
            if source["id"] in unlinked_ids:
                unlinked_commands.append(
                    UnlinkedEstimateEvidenceCommand(
                        native_estimate_id=str(source["id"]),
                        source_digest=canonical_sha256(source),
                        package_digest=customers.package_digest,
                        owner_binding_digest=receipts[
                            "HCP1A.UNLINKED_DAY1_ESTIMATES.V1"
                        ],
                        native_customer_id=str(source.get("customer", {}).get("id"))
                        if isinstance(source.get("customer"), Mapping)
                        else None,
                        native_service_location_id=str(
                            source.get("address", {}).get("id")
                        )
                        if isinstance(source.get("address"), Mapping)
                        else None,
                        source_status=str(source.get("work_status")),
                        option_evidence=tuple(
                            dict(item) for item in options if isinstance(item, Mapping)
                        ),
                        source_timestamps={
                            "created_at": source.get("created_at"),
                            "updated_at": source.get("updated_at"),
                        },
                        source_context={
                            "provider": "housecall_pro",
                            "authoritative_job_link": False,
                        },
                    )
                )
            elif (
                source["id"] in open_linked and len(open_linked[str(source["id"])]) == 1
            ):
                job_id, selected = next(iter(open_linked[str(source["id"])]))
                if job_id not in held_jobs:
                    estimate_rows.append(
                        {
                            **source,
                            "_source_digest": canonical_sha256(source),
                            "_source_job_id": job_id,
                            "_selected_option_id": selected,
                            "_owner_disposition": "MIGRATE_AUTHORITATIVE_JOB_LINK",
                        }
                    )
            elif source["id"] in open_linked:
                linked_relationship_exceptions += 1
        if len(unlinked_commands) != 24:
            raise SafeEvidenceError(
                "unlinked_estimate_accounting_mismatch",
                canonical_sha256(len(unlinked_commands)),
            )
        estimate_report = _report(
            entity="estimate",
            version="hcp_source4_estimate_options_api_v1",
            columns=ESTIMATE_COLUMNS,
            rows=estimate_rows,
        )
        estimate_identity_exceptions = tuple(
            item
            for item in estimate_report.rejections
            if item.code == "native_identity_invalid"
            and item.fields == ("_selected_option_id",)
        )
        if (
            estimate_report.duplicate
            or len(estimate_identity_exceptions) != estimate_report.rejected
        ):
            raise SafeEvidenceError(
                "estimate_transformation_incomplete",
                estimate_report.transformation_sha256,
            )

        financial_hold_ids = {
            str(row["id"])
            for row in invoices_raw
            if row.get("due_amount") not in {0, "0", None}
        }
        if len(financial_hold_ids) != 298:
            raise SafeEvidenceError(
                "financial_hold_accounting_mismatch",
                canonical_sha256(len(financial_hold_ids)),
            )
        invoice_rows: list[dict[str, Any]] = []
        payment_rows: list[dict[str, Any]] = []
        for source in invoices_raw:
            if source["id"] in financial_hold_ids or source.get("job_id") in held_jobs:
                continue
            invoice_rows.append(
                {
                    **source,
                    "_source_digest": canonical_sha256(source),
                    "_owner_disposition": "PRESERVE_SOURCE_FINANCIAL_ASSERTION",
                }
            )
            for payment in source.get("payments", []):
                if isinstance(payment, Mapping):
                    payment_rows.append(
                        {
                            **payment,
                            "_source_digest": canonical_sha256(payment),
                            "_source_invoice_id": source["id"],
                            "_owner_disposition": "SOURCE_ASSERTION_ONLY",
                        }
                    )
        _unique(payment_rows, "invpay_")
        invoice_report = _report(
            entity="invoice",
            version="hcp_source4_invoices_api_v1",
            columns=INVOICE_COLUMNS,
            rows=invoice_rows,
        )
        invoice_source_exceptions = tuple(
            item
            for item in invoice_report.rejections
            if item.code in {"invoice_amount_conflict", "changed_nested_layout"}
            and item.fields in {("amount", "subtotal"), ("refunds",)}
        )
        if (
            invoice_report.duplicate
            or len(invoice_source_exceptions) != invoice_report.rejected
        ):
            raise SafeEvidenceError(
                "invoice_transformation_incomplete",
                invoice_report.transformation_sha256,
            )
        accepted_invoice_ids = {item.source_id for item in invoice_report.records}
        payment_rows = [
            row
            for row in payment_rows
            if row["_source_invoice_id"] in accepted_invoice_ids
        ]
        payment_report = _report(
            entity="payment",
            version="hcp_source4_invoice_payments_api_v1",
            columns=PAYMENT_COLUMNS,
            rows=payment_rows,
        )
        if payment_report.rejected or payment_report.duplicate:
            raise SafeEvidenceError(
                "financial_transformation_incomplete",
                canonical_sha256(
                    [
                        invoice_report.transformation_sha256,
                        payment_report.transformation_sha256,
                    ]
                ),
            )

        notes_raw: list[dict[str, Any]] = []
        for job in jobs_raw:
            for note in job.get("notes", []):
                if isinstance(note, Mapping):
                    notes_raw.append(
                        {
                            **note,
                            "_source_digest": canonical_sha256(note),
                            "_source_job_id": job["id"],
                            "_occurred_at": None,
                            "_owner_disposition": "PRESERVE_PARTIAL_PROVENANCE",
                        }
                    )
        note_report = _report(
            entity="note",
            version="hcp_source4_job_notes_partial_api_v1",
            columns=NOTE_COLUMNS,
            rows=notes_raw,
        )
        if (
            note_report.accepted
            or note_report.duplicate
            or note_report.rejected != len(notes_raw)
        ):
            raise SafeEvidenceError(
                "note_partial_provenance_accounting_mismatch",
                note_report.transformation_sha256,
            )

        employee_binding = bindings["HCP1A.EMPLOYEE_CROSSWALK.V1"]
        dispositions = {
            str(item["native_id"]): str(item["selected_alternative"])
            for item in employee_binding.get("record_dispositions", [])
            if isinstance(item, Mapping)
        }
        if set(dispositions) != {str(row["id"]) for row in employees_raw}:
            raise SafeEvidenceError(
                "employee_disposition_identity_mismatch", canonical_sha256(dispositions)
            )
        employees = tuple(
            EmployeeCandidateCommand(
                native_employee_id=str(row["id"]),
                disposition=dispositions[str(row["id"])],
                source_digest=canonical_sha256(row),
                owner_receipt_digest=receipts["HCP1A.EMPLOYEE_CROSSWALK.V1"],
                first_name=str(row.get("first_name") or "").strip() or None
                if dispositions[str(row["id"])]
                == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE"
                else None,
                last_name=str(row.get("last_name") or "").strip() or None
                if dispositions[str(row["id"])]
                == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE"
                else None,
                display_name=(
                    f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()
                    or None
                )
                if dispositions[str(row["id"])]
                == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE"
                else None,
                job_title=str(row.get("role") or "").strip() or None
                if dispositions[str(row["id"])]
                == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE"
                else None,
            )
            for row in sorted(employees_raw, key=lambda item: str(item["id"]))
        )
        for item in employees:
            item.validate()
        if (
            sum(
                item.disposition == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE"
                for item in employees
            )
            != 6
        ):
            raise SafeEvidenceError("employee_create_count_mismatch", "6" * 64)

        holds = tuple(
            sorted(
                (
                    *(
                        HoldCommand(
                            entity_kind="job",
                            native_id=identity,
                            hold_code="CANCELED_JOB_BALANCE_RECONCILIATION",
                            evidence_digest=canonical_sha256(jobs_by_id[identity]),
                            reconciliation_key=canonical_sha256(["job", identity]),
                            owner_disposition="HOLD_OPERATIONAL_RECONCILE_BALANCE",
                        )
                        for identity in held_jobs
                    ),
                    *(
                        HoldCommand(
                            entity_kind="invoice",
                            native_id=identity,
                            hold_code="UNRESOLVED_FINANCIAL_BALANCE",
                            evidence_digest=canonical_sha256(
                                next(
                                    row for row in invoices_raw if row["id"] == identity
                                )
                            ),
                            reconciliation_key=canonical_sha256(["invoice", identity]),
                        )
                        for identity in financial_hold_ids
                    ),
                ),
                key=lambda item: (item.entity_kind, item.native_id),
            )
        )

        source_counts = {
            "customer": 5296,
            "contact": 4148,
            "service_location": 5633,
            "employee": len(employees_raw),
            "job": len(jobs_raw),
            "appointment": len(all_appointment_rows),
            "estimate": len(estimates_raw),
            "invoice": len(invoices_raw),
            "payment": sum(len(row.get("payments", [])) for row in invoices_raw),
            "note": len(notes_raw),
            "hold": len(holds),
            "unlinked_estimate": len(unlinked_commands),
        }
        persisted = {
            "customer": 5296,
            "contact": 4148,
            "service_location": 5339,
            "employee": 6,
            "job": len(job_report.records),
            "appointment": len(appointment_report.records),
            "estimate": len(estimate_report.records),
            "invoice": len(invoice_report.records),
            "payment": len(payment_report.records),
            "note": 0,
            "hold": len(holds),
            "unlinked_estimate": len(unlinked_commands),
        }
        exceptions = {
            "service_location": 294,
            "job": len(job_parent_exceptions),
            "appointment": len(appointment_parent_exceptions),
            "estimate": len(unlinked_commands)
            + linked_relationship_exceptions
            + len(estimate_identity_exceptions),
            "invoice": len(invoice_source_exceptions),
            "note": len(notes_raw),
        }
        non_applicable = {
            "employee": 1,
            "appointment": len(all_appointment_rows) - len(appointment_rows),
            "estimate": len(estimates_raw)
            - len(estimate_report.records)
            - len(unlinked_commands)
            - linked_relationship_exceptions
            - len(estimate_identity_exceptions),
            "invoice": len(invoices_raw)
            - len(invoice_report.records)
            - len(financial_hold_ids)
            - len(invoice_source_exceptions),
            "payment": source_counts["payment"] - len(payment_report.records),
        }
        outcome_commands: list[PlanOutcomeCommand] = []

        def add_outcome(
            entity: str,
            native_id: str,
            outcome: str,
            reason: str,
            evidence: object,
            version: str,
        ) -> None:
            outcome_commands.append(
                PlanOutcomeCommand(
                    entity_kind=entity,
                    native_identity_sha256=hashlib.sha256(
                        native_id.encode()
                    ).hexdigest(),
                    outcome=outcome,
                    reason_code=reason,
                    evidence_digest=canonical_sha256(evidence),
                    transformation_version=version,
                )
            )

        for row in jobs_raw:
            address = row.get("address")
            if row["id"] not in held_jobs and (
                not isinstance(address, Mapping)
                or not str(address.get("id", "")).startswith("adr_")
            ):
                add_outcome(
                    "job",
                    str(row["id"]),
                    "EXPLICIT_EXCEPTION",
                    "authoritative_service_location_identity_unavailable",
                    row,
                    "hcp_source4_jobs_api_v1",
                )
        accepted_appointment_ids = {
            item.source_id for item in appointment_report.records
        }
        for row in all_appointment_rows:
            if row["id"] in accepted_appointment_ids:
                continue
            outcome = (
                "INTENTIONALLY_NON_APPLICABLE"
                if row["_source_job_id"] in held_jobs
                else "EXPLICIT_EXCEPTION"
            )
            reason = (
                "held_job_parent"
                if outcome == "INTENTIONALLY_NON_APPLICABLE"
                else "authoritative_service_location_identity_unavailable"
            )
            add_outcome(
                "appointment",
                str(row["id"]),
                outcome,
                reason,
                row,
                "hcp_source4_job_appointments_api_v1",
            )
        accepted_estimate_ids = {item.source_id for item in estimate_report.records}
        for row in estimates_raw:
            identity = str(row["id"])
            if identity in accepted_estimate_ids:
                continue
            if identity in unlinked_ids:
                outcome = "EXPLICIT_EXCEPTION"
                reason = "unlinked_non_operational_estimate"
            elif identity in open_linked:
                outcome = "EXPLICIT_EXCEPTION"
                reason = (
                    "multiple_authoritative_open_job_links"
                    if len(open_linked[identity]) > 1
                    else "selected_option_native_identity_unsupported"
                )
            else:
                outcome = "INTENTIONALLY_NON_APPLICABLE"
                reason = "outside_authorized_operational_estimate_scope"
            add_outcome(
                "estimate",
                identity,
                outcome,
                reason,
                row,
                "hcp_source4_estimate_options_api_v1",
            )
        accepted_invoice_ids = {item.source_id for item in invoice_report.records}
        ordered_invoice_rows = sorted(invoice_rows, key=lambda value: str(value["id"]))
        invoice_exception_ids = {
            str(ordered_invoice_rows[item.row_number - 1]["id"])
            for item in invoice_source_exceptions
            if item.row_number is not None
        }
        for row in invoices_raw:
            identity = str(row["id"])
            if identity in accepted_invoice_ids or identity in financial_hold_ids:
                continue
            is_exception = identity in invoice_exception_ids
            add_outcome(
                "invoice",
                identity,
                "EXPLICIT_EXCEPTION"
                if is_exception
                else "INTENTIONALLY_NON_APPLICABLE",
                "source_invoice_contract_exception"
                if is_exception
                else "held_or_unavailable_job_parent",
                row,
                "hcp_source4_invoices_api_v1",
            )
        accepted_payment_ids = {item.source_id for item in payment_report.records}
        for invoice in invoices_raw:
            for payment in invoice.get("payments", []):
                if (
                    isinstance(payment, Mapping)
                    and payment.get("id") not in accepted_payment_ids
                ):
                    add_outcome(
                        "payment",
                        str(payment["id"]),
                        "INTENTIONALLY_NON_APPLICABLE",
                        "invoice_assertion_not_admitted",
                        payment,
                        "hcp_source4_invoice_payments_api_v1",
                    )
        for row in notes_raw:
            add_outcome(
                "note",
                str(row["id"]),
                "EXPLICIT_EXCEPTION",
                "authoritative_note_timestamp_unavailable",
                row,
                "hcp_source4_job_notes_partial_api_v1",
            )
        plan_outcomes = tuple(
            sorted(
                outcome_commands,
                key=lambda item: (item.entity_kind, item.native_identity_sha256),
            )
        )
        for outcome_command in plan_outcomes:
            outcome_command.validate()
        hold_counts = {"job": 296, "hold": 0}
        # Invoice source subjects are accounted as HOLD; durable hold rows are their own persisted entity.
        hold_counts["invoice"] = 298
        requirements = CompletionRequirements(
            customer_lineage=5296,
            location_identities=5339,
            location_exceptions=294,
            employee_crosswalks=7,
            employee_candidates=6,
            employee_excluded=1,
            note_outcomes={
                "persisted": 0,
                "duplicate": 0,
                "exception": len(notes_raw),
                "rejected": 0,
            },
            holds_by_code={
                "CANCELED_JOB_BALANCE_RECONCILIATION": 296,
                "UNRESOLVED_FINANCIAL_BALANCE": 298,
            },
            hold_counts=hold_counts,
            unlinked_estimates=len(unlinked_commands),
            transformed_counts={key: value for key, value in persisted.items()},
            persisted_counts=persisted,
            exception_counts=exceptions,
            rejection_counts={},
            unresolved_counts={},
            non_applicable_counts=non_applicable,
        )
        requirements.validate_reconciliation(source_counts)
        collection = _safe_json(self.package_root / "collection-manifest.json")
        if not isinstance(collection, Mapping):
            raise SafeEvidenceError("collection_manifest_shape_invalid", "7" * 64)
        contracts: dict[str, object] = {
            "hybrid_customer_admission_digest": customers.admission.digest,
            "customer_parent_closure_digest": customers.parent_closure.digest,
            "builder_version": BUILDER_VERSION,
            "job": "hcp_source4_jobs_api_v1",
            "appointment": "hcp_source4_job_appointments_api_v1",
            "estimate": "hcp_source4_estimate_options_api_v1",
            "invoice": "hcp_source4_invoices_api_v1",
            "payment": "hcp_source4_invoice_payments_api_v1",
            "note": "hcp_source4_job_notes_partial_api_v1",
        }
        command_identities = {
            "employees": [_command_digest(asdict(item)) for item in employees],
            "jobs": [_command_digest(asdict(item)) for item in job_report.records],
            "appointments": [
                _command_digest(asdict(item)) for item in appointment_report.records
            ],
            "estimates": [
                _command_digest(asdict(item)) for item in estimate_report.records
            ],
            "unlinked_estimates": sorted(
                item.evidence_digest for item in unlinked_commands
            ),
            "invoices": [
                _command_digest(asdict(item)) for item in invoice_report.records
            ],
            "payments": [
                _command_digest(asdict(item)) for item in payment_report.records
            ],
            "notes": [],
            "holds": [item.hold_digest for item in holds],
            "plan_outcomes": [item.outcome_digest for item in plan_outcomes],
        }
        plan_payload = {
            "builder": BUILDER_VERSION,
            "package": customers.package_digest,
            "collection": collection.get("manifest_sha256"),
            "receipts": receipts,
            "hybrid": customers.admission.digest,
            "closure": customers.parent_closure.digest,
            "company": str(company_id),
            "branch": str(branch_id),
            "actor": str(actor_id),
            "commands": command_identities,
            "source_counts": source_counts,
            "requirements": asdict(requirements),
        }
        plan_digest = canonical_sha256(plan_payload)
        plan_id = uuid5(PLAN_NAMESPACE, plan_digest)
        master = MasterRunCommand(
            package_digest=customers.package_digest,
            collection_digests={
                "manifest": collection.get("manifest_sha256"),
                "plan_digest": plan_digest,
            },
            transformation_contracts=contracts,
            owner_receipts=dict(receipts),
            schema_head=SCHEMA_HEAD,
            implementation_version=ORCHESTRATOR_VERSION,
            supported_entities=tuple(
                sorted(
                    {
                        "customer",
                        "contact",
                        "service_location",
                        "employee",
                        "job",
                        "appointment",
                        "estimate",
                        "invoice",
                        "payment",
                        "note",
                    }
                )
            ),
            baseline_counts=dict(sorted(baseline_counts.items())),
            source_counts=source_counts,
        )
        master.validate()
        plan = HcpMigration2ExecutionPlan(
            master=master,
            customers=customers,
            employees=employees,
            jobs=_typed(
                job_report,
                __import__(
                    "app.operational_migration.service", fromlist=["JobMigrationRecord"]
                ).JobMigrationRecord,
            ),
            appointments=_typed(
                appointment_report,
                __import__(
                    "app.operational_migration.service",
                    fromlist=["AppointmentMigrationRecord"],
                ).AppointmentMigrationRecord,
            ),
            estimates=_typed(
                estimate_report,
                __import__(
                    "app.operational_migration.financial",
                    fromlist=["EstimateMigrationRecord"],
                ).EstimateMigrationRecord,
            ),
            unlinked_estimates=tuple(
                sorted(unlinked_commands, key=lambda item: item.native_estimate_id)
            ),
            invoices=_typed(
                invoice_report,
                __import__(
                    "app.operational_migration.financial",
                    fromlist=["InvoiceMigrationRecord"],
                ).InvoiceMigrationRecord,
            ),
            payments=_typed(
                payment_report,
                __import__(
                    "app.operational_migration.financial",
                    fromlist=["PaymentMigrationRecord"],
                ).PaymentMigrationRecord,
            ),
            notes=(),
            holds=holds,
            plan_outcomes=plan_outcomes,
            completion=requirements,
            verified_owner_receipts=receipts,
            plan_id=plan_id,
            plan_digest=plan_digest,
            builder_version=BUILDER_VERSION,
        )
        plan.validate()
        summary = HcpMigration2PlanSummary(
            plan_id,
            plan_digest,
            BUILDER_VERSION,
            source_counts,
            {
                key: len(value)
                for key, value in {
                    "employees": employees,
                    "jobs": plan.jobs,
                    "appointments": plan.appointments,
                    "estimates": plan.estimates,
                    "unlinked_estimates": plan.unlinked_estimates,
                    "invoices": plan.invoices,
                    "payments": plan.payments,
                    "notes": plan.notes,
                    "holds": holds,
                    "plan_outcomes": plan_outcomes,
                }.items()
            },
            {
                "persisted": persisted,
                "held": hold_counts,
                "exceptions": exceptions,
                "non_applicable": non_applicable,
            },
        )
        return plan, summary

    def build_child_repair_plan(
        self,
        *,
        original: HcpMigration2ExecutionPlan,
        persisted_customer_ids: frozenset[str],
        persisted_location_ids: frozenset[str],
    ) -> ChildRepairPlan:
        """Requalify an immutable plan against its durably admitted parents."""
        original.validate()
        created_at_by_job: dict[str, datetime | None] = {}
        for row in self._pages("jobs"):
            identity = str(row.get("id", ""))
            value = row.get("created_at")
            try:
                created_at_by_job[identity] = (
                    datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    if value
                    else None
                )
            except (TypeError, ValueError) as error:
                raise SafeEvidenceError(
                    "job_created_timestamp_invalid",
                    canonical_sha256(identity),
                ) from error
        operational = requalify_operational_commands(
            jobs=original.jobs,
            appointments=original.appointments,
            created_at_by_job=created_at_by_job,
            persisted_customer_ids=persisted_customer_ids,
            persisted_location_ids=persisted_location_ids,
        )
        financial = requalify_financial_commands(
            estimates=original.estimates,
            invoices=original.invoices,
            payments=original.payments,
            admitted_job_ids=frozenset(item.source_id for item in operational.jobs),
        )
        return ChildRepairPlan.build(
            original_plan_id=original.plan_id,
            original_plan_digest=original.plan_digest,
            operational=operational,
            financial=financial,
            original_persisted_counts=original.completion.persisted_counts,
            original_exception_counts=original.completion.exception_counts,
        )

    def build_appointment_correction_plan(
        self,
        *,
        master_id: UUID,
        repair_id: UUID,
        repair: ChildRepairPlan,
        retained: Sequence[RetainedAppointmentProjection],
        accepted_job_count: int,
    ) -> tuple[
        AppointmentSequencePlan,
        AppointmentCorrectionCheckpoint,
        SupersedingAppointmentRepairPlan,
    ]:
        """Build the sanctioned generation-2 checkpoint without mutating targets."""
        sequence = build_appointment_sequence_plan(repair.operational.appointments)
        checkpoint = qualify_retained_checkpoint(
            plan=sequence,
            retained=retained,
            accepted_job_count=accepted_job_count,
        )
        superseding = SupersedingAppointmentRepairPlan.build(
            master_id=master_id,
            repair_id=repair_id,
            original_repair_plan_digest=repair.repair_plan_digest,
            sequence_plan=sequence,
            checkpoint=checkpoint,
        )
        return sequence, checkpoint, superseding


class HcpMigration2Application:
    """Sanctioned no-manual-plan entry point for SOURCE.4 rehearsal execution."""

    def __init__(
        self,
        *,
        builder: HcpMigration2ExecutionPlanBuilder,
        runner: HcpMigration2Runner | None = None,
    ) -> None:
        self.builder = builder
        self.runner = runner or HcpMigration2Runner()

    @staticmethod
    async def _count(session: AsyncSession, model: type[object]) -> int:
        value = await session.scalar(select(func.count()).select_from(model))
        return int(value or 0)

    @staticmethod
    def classify_master_admission(
        masters: Sequence[HcpMigrationMasterRun],
    ) -> RehearsalAdmissionState:
        if not masters:
            return RehearsalAdmissionState.NO_MASTER
        if len(masters) > 1:
            return RehearsalAdmissionState.MULTIPLE_UNEXPECTED_MASTERS
        if masters[0].status == "completed":
            return RehearsalAdmissionState.COMPLETED_MASTER
        if masters[0].status in {"prepared", "running", "interrupted"}:
            return RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER
        return RehearsalAdmissionState.CONTRADICTORY_MASTER

    @classmethod
    def classify_application_admission(
        cls,
        masters: Sequence[HcpMigrationMasterRun],
        *,
        repair_authority: HcpMigration2RepairAuthority | None,
    ) -> RehearsalAdmissionState:
        state = cls.classify_master_admission(masters)
        if (
            state == RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER
            and repair_authority is not None
        ):
            return RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER_WITH_ACCEPTED_REPAIR_PLAN
        return state

    @staticmethod
    def _expected_master_attestation(
        master: HcpMigrationMasterRun, payload: dict[str, object]
    ) -> str:
        if master.status in {"prepared", "running"}:
            return canonical_sha256({"input": payload, "status": "prepared"})
        if master.status != "interrupted":
            raise SafeEvidenceError(
                "resume_master_attestation_state_invalid", master.input_digest
            )
        outcome = {
            "transformed_counts": master.transformed_counts,
            "persisted_counts": master.persisted_counts,
            "hold_counts": master.hold_counts,
            "exception_counts": master.exception_counts,
            "rejection_counts": master.rejection_counts,
            "unresolved_counts": master.unresolved_counts,
            "non_applicable_counts": master.non_applicable_counts,
            "child_run_ids": master.child_run_ids,
            "replay_state": master.replay_state,
            "resume_state": master.resume_state,
            "status": master.status,
        }
        reconciliation = canonical_sha256(
            {"input_digest": master.input_digest, "outcome": outcome}
        )
        return canonical_sha256(
            {
                "contract": MASTER_CONTRACT,
                "run_id": str(master.id),
                "input_digest": master.input_digest,
                "reconciliation_digest": reconciliation,
                "outcome": outcome,
            }
        )

    async def prepare(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
    ) -> tuple[HcpMigration2ExecutionPlan, HcpMigration2PlanSummary]:
        existing_master: HcpMigrationMasterRun | None = None
        async with factory() as session:
            await self.runner.orchestrator.qualify_target(
                session, context=context, target=target
            )
            counts = {
                "customers": await self._count(session, Customer),
                "contacts": await self._count(session, CustomerContact),
                "locations": await self._count(session, ServiceLocation),
                "employees": await self._count(session, Employee),
                "jobs": await self._count(session, Job),
                "appointments": await self._count(session, Appointment),
                "estimates": await self._count(session, Estimate),
                "invoices": await self._count(session, Invoice),
                "payments": await self._count(session, Payment),
                "masters": await self._count(session, HcpMigrationMasterRun),
                "customer_runs": await self._count(session, CustomerMigrationRun),
                "operational_runs": await self._count(session, OperationalMigrationRun),
            }
            masters = tuple(
                (await session.scalars(select(HcpMigrationMasterRun))).all()
            )
        admission_state = self.classify_master_admission(masters)
        if admission_state == RehearsalAdmissionState.MULTIPLE_UNEXPECTED_MASTERS:
            raise SafeEvidenceError(
                "multiple_unexpected_masters", canonical_sha256({"count": len(masters)})
            )
        if admission_state == RehearsalAdmissionState.NO_MASTER:
            if any(counts.values()):
                raise SafeEvidenceError(
                    "rehearsal_target_baseline_not_pristine", canonical_sha256(counts)
                )
            baseline = counts
        else:
            existing_master = masters[0]
            if admission_state == RehearsalAdmissionState.COMPLETED_MASTER:
                raise SafeEvidenceError(
                    "completed_master_requires_replay_path",
                    existing_master.input_digest,
                )
            if admission_state == RehearsalAdmissionState.CONTRADICTORY_MASTER:
                raise SafeEvidenceError(
                    "contradictory_master_state", existing_master.input_digest
                )
            baseline = dict(existing_master.baseline_counts)

        plan, summary = self.builder.build(baseline_counts=baseline)
        if existing_master is not None:
            await self._qualify_incomplete_resume(
                factory,
                context=context,
                master=existing_master,
                plan=plan,
            )
        return plan, summary

    async def _qualify_incomplete_resume(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        master: HcpMigrationMasterRun,
        plan: HcpMigration2ExecutionPlan,
    ) -> None:
        if context.active_branch is None:
            raise SafeEvidenceError("resume_scope_invalid", master.input_digest)
        payload = plan.master.input_payload(
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            actor_id=context.user.id,
        )
        input_digest = canonical_sha256(payload)
        expected_master_id = uuid5(MASTER_NAMESPACE, input_digest)
        expected_attestation = self._expected_master_attestation(master, payload)
        immutable_match = all(
            (
                master.id == expected_master_id,
                master.input_digest == input_digest,
                master.attestation_digest == expected_attestation,
                master.package_digest == plan.master.package_digest,
                master.collection_digests == plan.master.collection_digests,
                master.transformation_contracts == plan.master.transformation_contracts,
                master.owner_receipts == plan.master.owner_receipts,
                master.company_id == context.company.id,
                master.branch_id == context.active_branch.id,
                master.actor_user_id == context.user.id,
                master.schema_head == plan.master.schema_head,
                master.implementation_version == plan.master.implementation_version,
                master.supported_entities == sorted(plan.master.supported_entities),
                master.baseline_counts == plan.master.baseline_counts,
                master.source_counts == plan.master.source_counts,
                master.collection_digests.get("plan_digest") == plan.plan_digest,
                master.transformation_contracts.get("builder_version")
                == plan.builder_version,
            )
        )
        if not immutable_match:
            raise SafeEvidenceError("incomplete_master_resume_conflict", input_digest)

        staging_counts = {
            "customers": len(plan.customers.reviewed.aggregates),
            "contacts": sum(
                item.contact_json is not None
                for item in plan.customers.reviewed.aggregates
            ),
            "locations": sum(
                len(item.service_location_json)
                for item in plan.customers.reviewed.aggregates
            ),
            "child_exceptions": sum(
                len(item.location_exception_ids)
                for item in plan.customers.admission.candidates
            ),
        }
        staging_digest = canonical_sha256(
            {
                "contract": "hcp-source4-master-bound-customer-staging/v1",
                "master_run_id": str(master.id),
                "package_digest": master.package_digest,
                "hybrid_admission_digest": plan.customers.admission.digest,
                "review_digest": plan.customers.reviewed.review_sha256,
                "transformation_digest": (
                    plan.customers.reviewed.transformation_sha256
                ),
                "company_id": str(context.company.id),
                "branch_id": str(context.active_branch.id),
                "actor_id": str(context.user.id),
                "counts": staging_counts,
            }
        )
        artifact_id = uuid5(STAGING_NAMESPACE, staging_digest)
        async with factory() as session:
            artifacts = tuple(
                (
                    await session.scalars(
                        select(CustomerMigrationSourceArtifact).where(
                            CustomerMigrationSourceArtifact.master_run_id == master.id
                        )
                    )
                ).all()
            )
            if len(artifacts) != 1:
                raise SafeEvidenceError(
                    "resume_staging_cardinality_invalid", staging_digest
                )
            artifact = artifacts[0]
            staged_rows = await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceRow)
                .where(CustomerMigrationSourceRow.artifact_id == artifact_id)
            )
            staged_candidates = await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationCandidate)
                .join(CustomerMigrationSourceRow)
                .where(CustomerMigrationSourceRow.artifact_id == artifact_id)
            )
            staged_exceptions = await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationChildException)
                .join(CustomerMigrationSourceRow)
                .where(CustomerMigrationSourceRow.artifact_id == artifact_id)
            )
        if (
            artifact.id != artifact_id
            or artifact.staging_digest != staging_digest
            or artifact.source_sha256 != plan.customers.admission.digest
            or artifact.row_count != staging_counts["customers"]
            or staged_rows != staging_counts["customers"]
            or staged_candidates
            != staging_counts["customers"]
            + staging_counts["contacts"]
            + staging_counts["locations"]
            or staged_exceptions != staging_counts["child_exceptions"]
        ):
            raise SafeEvidenceError("resume_staging_evidence_conflict", staging_digest)

    async def _prepare_repair(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
        authority: HcpMigration2RepairAuthority,
    ) -> tuple[
        HcpMigration2ExecutionPlan,
        ChildRepairPlan,
        HcpMigrationMasterRun,
        CustomerMigrationRun,
        OperationalMigrationRun,
        OperationalMigrationRun,
        OperationalMigrationRun,
    ]:
        plan, _ = await self.prepare(factory, context=context, target=target)
        if context.active_branch is None:
            raise SafeEvidenceError(
                "repair_scope_invalid", authority.repair_plan_digest
            )
        async with factory() as session:
            master = await session.get(HcpMigrationMasterRun, authority.master_run_id)
            customer = await session.get(
                CustomerMigrationRun, authority.customer_child_run_id
            )
            operational = await session.get(
                OperationalMigrationRun, authority.operational_child_run_id
            )
            financial = await session.get(
                OperationalMigrationRun, authority.financial_child_run_id
            )
            history = await session.get(
                OperationalMigrationRun, authority.history_child_run_id
            )
            customer_ids = frozenset(
                (
                    await session.scalars(
                        select(CustomerSourceIdentity.source_customer_id)
                        .join(
                            CustomerMigrationRun,
                            CustomerMigrationRun.id
                            == CustomerSourceIdentity.first_run_id,
                        )
                        .where(
                            CustomerSourceIdentity.source_system
                            == "housecall_pro_source4",
                            CustomerSourceIdentity.company_id == context.company.id,
                            CustomerMigrationRun.master_run_id
                            == authority.master_run_id,
                        )
                    )
                ).all()
            )
            location_ids = frozenset(
                (
                    await session.scalars(
                        select(ServiceLocationSourceIdentity.source_location_id).where(
                            ServiceLocationSourceIdentity.source_system
                            == "housecall_pro_source4",
                            ServiceLocationSourceIdentity.company_id
                            == context.company.id,
                            ServiceLocationSourceIdentity.branch_id
                            == context.active_branch.id,
                            ServiceLocationSourceIdentity.master_run_id
                            == authority.master_run_id,
                        )
                    )
                ).all()
            )
        if (
            master is None
            or customer is None
            or operational is None
            or financial is None
            or history is None
        ):
            raise SafeEvidenceError(
                "repair_authoritative_run_missing", authority.repair_plan_digest
            )
        if (
            master.status not in {"running", "interrupted"}
            or plan.plan_id != authority.original_plan_id
            or plan.plan_digest != authority.original_plan_digest
            or customer.master_run_id != master.id
            or operational.master_run_id != master.id
            or financial.master_run_id != master.id
            or history.master_run_id != master.id
            or operational.master_domain != "operational"
            or financial.master_domain != "financial"
            or history.master_domain != "history"
            or customer.status != "completed"
            or customer.accepted_count != customer.source_count
            or operational.status != "completed"
            or financial.status != "completed"
            or history.status != "completed"
            or operational.accepted_count == operational.source_count
            or financial.accepted_count == financial.source_count
        ):
            raise SafeEvidenceError(
                "repair_original_child_authority_conflict",
                authority.repair_plan_digest,
            )
        repair = self.builder.build_child_repair_plan(
            original=plan,
            persisted_customer_ids=customer_ids,
            persisted_location_ids=location_ids,
        )
        if repair.repair_plan_digest != authority.repair_plan_digest:
            raise SafeEvidenceError(
                "repair_plan_digest_mismatch", repair.repair_plan_digest
            )
        return plan, repair, master, customer, operational, financial, history

    @staticmethod
    def _run_counts(
        run: CustomerMigrationRun | OperationalMigrationRun,
    ) -> ChildOutcomeCounts:
        return ChildOutcomeCounts(
            source=run.source_count,
            accepted=run.accepted_count,
            rejected=run.rejected_count,
            duplicate=run.duplicate_count,
            unresolved=run.unresolved_count,
        )

    @staticmethod
    def _requalified_completion_authority(
        *,
        plan: HcpMigration2ExecutionPlan,
        repair: ChildRepairPlan,
        requirements: CompletionRequirements,
        original_operational_run_id: UUID,
        original_financial_run_id: UUID,
        repaired_operational_run_id: UUID,
        repaired_financial_run_id: UUID,
    ) -> dict[str, object]:
        return {
            "contract": "hcp-migration-2j-requalified-completion/v1",
            "original_plan_id": str(plan.plan_id),
            "original_plan_digest": plan.plan_digest,
            "repair_plan_digest": repair.repair_plan_digest,
            "repair_generation": 1,
            "original_children": {
                "operational": str(original_operational_run_id),
                "financial": str(original_financial_run_id),
            },
            "admitted_repair_children": {
                "operational": str(repaired_operational_run_id),
                "financial": str(repaired_financial_run_id),
            },
            "requirements_digest": canonical_sha256(asdict(requirements)),
        }

    async def execute_repair(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
        authority: HcpMigration2RepairAuthority,
    ) -> dict[str, object]:
        (
            plan,
            repair,
            master,
            customer,
            original_operational,
            original_financial,
            history,
        ) = await self._prepare_repair(
            factory, context=context, target=target, authority=authority
        )
        original_operational_expected = ChildOutcomeCounts(
            len(plan.jobs) + len(plan.appointments),
            len(plan.jobs) + len(plan.appointments),
            0,
            0,
            0,
        )
        original_financial_expected = ChildOutcomeCounts(
            len(plan.estimates) + len(plan.invoices) + len(plan.payments),
            len(plan.estimates) + len(plan.invoices) + len(plan.payments),
            0,
            0,
            0,
        )
        async with factory() as session, session.begin():
            await self.runner.orchestrator.admit_child_outcome(
                session,
                context=context,
                master_run_id=master.id,
                child_run_id=customer.id,
                domain="customer",
                plan_digest=plan.plan_digest,
                execution_status=customer.status,
                expected=self._run_counts(customer),
                actual=self._run_counts(customer),
                reason_code="existing_customer_child_reused",
            )
            await self.runner.orchestrator.admit_child_outcome(
                session,
                context=context,
                master_run_id=master.id,
                child_run_id=history.id,
                domain="history",
                plan_digest=plan.plan_digest,
                execution_status=history.status,
                expected=self._run_counts(history),
                actual=self._run_counts(history),
                reason_code="existing_history_child_reused",
            )
            await self.runner.orchestrator.admit_child_outcome(
                session,
                context=context,
                master_run_id=master.id,
                child_run_id=original_operational.id,
                domain="operational",
                plan_digest=plan.plan_digest,
                execution_status=original_operational.status,
                expected=original_operational_expected,
                actual=self._run_counts(original_operational),
                reason_code="original_child_plan_nonconforming",
            )
            await self.runner.orchestrator.admit_child_outcome(
                session,
                context=context,
                master_run_id=master.id,
                child_run_id=original_financial.id,
                domain="financial",
                plan_digest=plan.plan_digest,
                execution_status=original_financial.status,
                expected=original_financial_expected,
                actual=self._run_counts(original_financial),
                reason_code="original_child_plan_nonconforming",
            )
            operational_repair = await self.runner.orchestrator.qualify_child_repair(
                session,
                context=context,
                master_run_id=master.id,
                original_child_run_id=original_operational.id,
                domain="operational",
                original_plan_digest=plan.plan_digest,
                repair_plan_digest=repair.repair_plan_digest,
                immutable_input_digest=master.input_digest,
                reason_code="operational_child_outcome_requalification",
            )
            financial_repair = await self.runner.orchestrator.qualify_child_repair(
                session,
                context=context,
                master_run_id=master.id,
                original_child_run_id=original_financial.id,
                domain="financial",
                original_plan_digest=plan.plan_digest,
                repair_plan_digest=repair.repair_plan_digest,
                immutable_input_digest=master.input_digest,
                reason_code="financial_parent_eligibility_requalification",
            )
        operational_report = await self.runner.orchestrator.run_operational_repair(
            factory,
            context=context,
            repair_id=operational_repair.id,
            jobs=repair.operational.jobs,
            appointments=repair.operational.appointments,
        )
        operational_expected = ChildOutcomeCounts(
            len(repair.operational.jobs) + len(repair.operational.appointments),
            len(repair.operational.jobs) + len(repair.operational.appointments),
            0,
            0,
            0,
        )
        operational_actual = ChildOutcomeCounts(
            operational_report.source,
            operational_report.accepted,
            operational_report.rejected,
            operational_report.duplicate,
            operational_report.unresolved,
        )
        async with factory() as session, session.begin():
            operational_admission = await self.runner.orchestrator.admit_child_outcome(
                session,
                context=context,
                master_run_id=master.id,
                child_run_id=operational_report.run_id,
                domain="operational",
                plan_digest=repair.repair_plan_digest,
                execution_status="completed",
                expected=operational_expected,
                actual=operational_actual,
                reason_code="requalified_operational_child",
            )
            if operational_admission.conformance != "PLAN_CONFORMING":
                raise SafeEvidenceError(
                    "operational_repair_nonconforming", repair.repair_plan_digest
                )
        financial_report = await self.runner.orchestrator.run_financial_repair(
            factory,
            context=context,
            repair_id=financial_repair.id,
            estimates=repair.financial.estimates,
            invoices=repair.financial.invoices,
            payments=repair.financial.payments,
        )
        financial_expected = ChildOutcomeCounts(
            len(repair.financial.estimates)
            + len(repair.financial.invoices)
            + len(repair.financial.payments),
            len(repair.financial.estimates)
            + len(repair.financial.invoices)
            + len(repair.financial.payments),
            0,
            0,
            0,
        )
        financial_actual = ChildOutcomeCounts(
            financial_report.source,
            financial_report.accepted,
            financial_report.rejected,
            financial_report.duplicate,
            financial_report.unresolved,
        )
        requirements = replace(
            plan.completion,
            transformed_counts=repair.persisted_counts,
            persisted_counts=repair.persisted_counts,
            exception_counts=repair.exception_counts,
        )
        requirements.validate_reconciliation(plan.master.source_counts)
        async with factory() as session, session.begin():
            financial_admission = await self.runner.orchestrator.admit_child_outcome(
                session,
                context=context,
                master_run_id=master.id,
                child_run_id=financial_report.run_id,
                domain="financial",
                plan_digest=repair.repair_plan_digest,
                execution_status="completed",
                expected=financial_expected,
                actual=financial_actual,
                reason_code="requalified_financial_child",
            )
            if financial_admission.conformance != "PLAN_CONFORMING":
                raise SafeEvidenceError(
                    "financial_repair_nonconforming", repair.repair_plan_digest
                )
            for hold in plan.holds:
                await self.runner.orchestrator.persist_held_subject(
                    session,
                    context=context,
                    master_run_id=master.id,
                    command=hold,
                )
            for outcome in (*plan.plan_outcomes, *repair.additional_plan_outcomes):
                await self.runner.orchestrator.persist_plan_outcome(
                    session,
                    context=context,
                    master_run_id=master.id,
                    command=outcome,
                )
            requalified_authority = self._requalified_completion_authority(
                plan=plan,
                repair=repair,
                requirements=requirements,
                original_operational_run_id=original_operational.id,
                original_financial_run_id=original_financial.id,
                repaired_operational_run_id=operational_report.run_id,
                repaired_financial_run_id=financial_report.run_id,
            )
            completed = await self.runner.orchestrator.complete(
                session,
                context=context,
                master_run_id=master.id,
                expected_input_digest=master.input_digest,
                requirements=requirements,
                requalified_authority=requalified_authority,
            )
        return HcpMigration2RepairResult(
            state="REPAIR_COMPLETED",
            master_run_id=completed.id,
            master_status=completed.status,
            repair_plan_digest=repair.repair_plan_digest,
            operational_repair_run_id=operational_report.run_id,
            financial_repair_run_id=financial_report.run_id,
            reconciliation_digest=completed.reconciliation_digest,
        ).safe_output()

    async def replay_completed(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
        authority: HcpMigration2RepairAuthority,
    ) -> dict[str, object]:
        async with factory() as session:
            await self.runner.orchestrator.qualify_target(
                session, context=context, target=target
            )
            master = await session.get(HcpMigrationMasterRun, authority.master_run_id)
            if master is None or master.status != "completed":
                raise SafeEvidenceError(
                    "completed_master_replay_state_invalid",
                    authority.repair_plan_digest,
                )
            plan, _ = self.builder.build(baseline_counts=dict(master.baseline_counts))
            customer_ids = frozenset(
                (
                    await session.scalars(
                        select(CustomerSourceIdentity.source_customer_id)
                        .join(
                            CustomerMigrationRun,
                            CustomerMigrationRun.id
                            == CustomerSourceIdentity.first_run_id,
                        )
                        .where(
                            CustomerSourceIdentity.source_system
                            == "housecall_pro_source4",
                            CustomerSourceIdentity.company_id == master.company_id,
                            CustomerMigrationRun.master_run_id == master.id,
                        )
                    )
                ).all()
            )
            location_ids = frozenset(
                (
                    await session.scalars(
                        select(ServiceLocationSourceIdentity.source_location_id).where(
                            ServiceLocationSourceIdentity.source_system
                            == "housecall_pro_source4",
                            ServiceLocationSourceIdentity.company_id
                            == master.company_id,
                            ServiceLocationSourceIdentity.branch_id == master.branch_id,
                            ServiceLocationSourceIdentity.master_run_id == master.id,
                        )
                    )
                ).all()
            )
            repairs = tuple(
                (
                    await session.scalars(
                        select(HcpMigrationChildRepair).where(
                            HcpMigrationChildRepair.master_run_id == master.id
                        )
                    )
                ).all()
            )
            admissions = tuple(
                (
                    await session.scalars(
                        select(HcpMigrationChildAdmission).where(
                            HcpMigrationChildAdmission.master_run_id == master.id,
                            HcpMigrationChildAdmission.conformance == "PLAN_CONFORMING",
                        )
                    )
                ).all()
            )
            hold_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(HcpMigrationHold)
                    .where(HcpMigrationHold.master_run_id == master.id)
                )
                or 0
            )
            outcome_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(HcpMigrationPlanOutcome)
                    .where(HcpMigrationPlanOutcome.master_run_id == master.id)
                )
                or 0
            )
        repair = self.builder.build_child_repair_plan(
            original=plan,
            persisted_customer_ids=customer_ids,
            persisted_location_ids=location_ids,
        )
        replay_authority = master.replay_state.get("requalified_completion")
        repaired_children = {item.domain: item.repair_child_run_id for item in repairs}
        repairs_by_domain = {item.domain: item for item in repairs}
        admissions_by_domain = {item.domain: item for item in admissions}
        repaired_operational_id = repaired_children.get("operational")
        repaired_financial_id = repaired_children.get("financial")
        if repaired_operational_id is None or repaired_financial_id is None:
            raise SafeEvidenceError(
                "completed_master_repair_child_missing",
                authority.repair_plan_digest,
            )
        expected_replay_authority = self._requalified_completion_authority(
            plan=plan,
            repair=repair,
            requirements=replace(
                plan.completion,
                transformed_counts=repair.persisted_counts,
                persisted_counts=repair.persisted_counts,
                exception_counts=repair.exception_counts,
            ),
            original_operational_run_id=authority.operational_child_run_id,
            original_financial_run_id=authority.financial_child_run_id,
            repaired_operational_run_id=repaired_operational_id,
            repaired_financial_run_id=repaired_financial_id,
        )
        if (
            plan.plan_id != authority.original_plan_id
            or plan.plan_digest != authority.original_plan_digest
            or repair.repair_plan_digest != authority.repair_plan_digest
            or len(repairs) != 2
            or {item.domain for item in repairs} != {"operational", "financial"}
            or any(item.status != "completed" for item in repairs)
            or repairs_by_domain["operational"].original_child_run_id
            != authority.operational_child_run_id
            or repairs_by_domain["financial"].original_child_run_id
            != authority.financial_child_run_id
            or any(
                item.original_plan_digest != plan.plan_digest
                or item.repair_plan_digest != repair.repair_plan_digest
                or item.immutable_input_digest != master.input_digest
                for item in repairs
            )
            or {item.domain for item in admissions}
            != {"customer", "operational", "financial", "history"}
            or admissions_by_domain["customer"].child_run_id
            != authority.customer_child_run_id
            or admissions_by_domain["history"].child_run_id
            != authority.history_child_run_id
            or admissions_by_domain["operational"].child_run_id
            != repaired_operational_id
            or admissions_by_domain["financial"].child_run_id != repaired_financial_id
            or admissions_by_domain["customer"].plan_digest != plan.plan_digest
            or admissions_by_domain["history"].plan_digest != plan.plan_digest
            or admissions_by_domain["operational"].plan_digest
            != repair.repair_plan_digest
            or admissions_by_domain["financial"].plan_digest
            != repair.repair_plan_digest
            or master.package_digest != plan.master.package_digest
            or master.collection_digests != plan.master.collection_digests
            or master.owner_receipts != plan.master.owner_receipts
            or master.company_id != context.company.id
            or context.active_branch is None
            or master.branch_id != context.active_branch.id
            or master.actor_user_id != context.user.id
            or hold_count != len(plan.holds)
            or outcome_count
            != len(plan.plan_outcomes) + len(repair.additional_plan_outcomes)
            or master.reconciliation_digest is None
            or replay_authority != expected_replay_authority
        ):
            raise SafeEvidenceError(
                "completed_master_replay_conflict", authority.repair_plan_digest
            )
        return {
            "state": "COMPLETED_REPLAY_VERIFIED",
            "master_run_id": str(master.id),
            "master_status": master.status,
            "repair_plan_digest": repair.repair_plan_digest,
            "reconciliation_digest": master.reconciliation_digest,
        }

    async def execute(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
        repair_authority: HcpMigration2RepairAuthority | None = None,
    ) -> dict[str, object]:
        async with factory() as session:
            masters = tuple(
                (await session.scalars(select(HcpMigrationMasterRun))).all()
            )
        state = self.classify_application_admission(
            masters, repair_authority=repair_authority
        )
        if state == RehearsalAdmissionState.COMPLETED_MASTER:
            if repair_authority is None:
                raise SafeEvidenceError(
                    "completed_master_repair_authority_required",
                    masters[0].input_digest,
                )
            return await self.replay_completed(
                factory,
                context=context,
                target=target,
                authority=repair_authority,
            )
        if (
            state
            == RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER_WITH_ACCEPTED_REPAIR_PLAN
        ):
            assert repair_authority is not None
            return await self.execute_repair(
                factory,
                context=context,
                target=target,
                authority=repair_authority,
            )
        if repair_authority is not None:
            raise SafeEvidenceError(
                "repair_application_state_invalid",
                repair_authority.repair_plan_digest,
            )
        plan, summary = await self.prepare(factory, context=context, target=target)
        result = await self.runner.execute(
            factory, context=context, target=target, plan=plan
        )
        return {"plan": summary.safe_output(), "run": result}
