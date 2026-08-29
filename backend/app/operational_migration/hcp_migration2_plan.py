"""Deterministic protected SOURCE.4 execution-plan construction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.models import CustomerMigrationRun
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
    HoldCommand,
    MasterRunCommand,
    PlanOutcomeCommand,
)
from app.operational_migration.hcp_migration2c import (
    ORCHESTRATOR_VERSION,
    CompletionRequirements,
    EmployeeCandidateCommand,
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
    HcpMigrationMasterRun,
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
                "duplicate_native_identity", hashlib.sha256(identity.encode()).hexdigest()
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
        raise SafeEvidenceError("transformation_record_type_invalid", report.transformation_sha256)
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
        manifest = _safe_json(self.package_root / "relationship-appointments-manifest.json")
        if not isinstance(manifest, Mapping) or not isinstance(manifest.get("artifacts"), list):
            raise SafeEvidenceError("appointment_manifest_layout_invalid", "3" * 64)
        by_hash = {hashlib.sha256(identity.encode()).hexdigest(): row for identity, row in jobs.items()}
        files: dict[str, Path] = {}
        for folder in ("job-appointments-2023-plus", "job-appointments-retry"):
            for path in (self.package_root / "raw" / folder).glob("*.json"):
                files[_file_sha256(path)] = path
        result: list[dict[str, Any]] = []
        for artifact in manifest["artifacts"]:
            if not isinstance(artifact, Mapping) or artifact.get("http_status") != 200:
                continue
            job = by_hash.get(str(artifact.get("job_identity_sha256")))
            digest = artifact.get("effective_retry_sha256") or artifact.get("response_sha256")
            selected_path = files.get(str(digest))
            if job is None or selected_path is None:
                raise SafeEvidenceError("appointment_parent_evidence_missing", canonical_sha256(artifact))
            customer = job.get("customer")
            address = job.get("address")
            if not isinstance(customer, Mapping) or not isinstance(address, Mapping):
                raise SafeEvidenceError("appointment_parent_layout_invalid", canonical_sha256(job))
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

        crosswalk = _safe_json(self.package_root / "reconciliation" / "job-native-control-crosswalk.json")
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
            for row in representative[
                "HCP1A.RECENT_ZERO_BALANCE_CANCELED_JOBS.V1"
            ]
            if isinstance(row, Mapping)
        }
        if len(held_jobs) != 296 or len(history_jobs) != 3:
            raise SafeEvidenceError("job_owner_disposition_accounting_mismatch", canonical_sha256([len(held_jobs), len(history_jobs)]))
        job_rows: list[dict[str, Any]] = []
        for source in jobs_raw:
            if source["id"] in held_jobs:
                continue
            disposition = "MIGRATE_CANCELED_HISTORY_ONLY" if source["id"] in history_jobs else "MIGRATE_SOURCE_REPORTED"
            job_rows.append({**source, "_source_digest": canonical_sha256(source), "_owner_disposition": disposition})
        job_report = _report(entity="job", version="hcp_source4_jobs_api_v1", columns=JOB_COLUMNS, rows=job_rows)
        job_parent_exceptions = tuple(
            item
            for item in job_report.rejections
            if item.code == "native_identity_invalid" and item.fields == ("address.id",)
        )
        if job_report.duplicate or len(job_parent_exceptions) != job_report.rejected:
            raise SafeEvidenceError("job_transformation_incomplete", job_report.transformation_sha256)

        all_appointment_rows = self._appointments(jobs_by_id)
        appointment_rows = [
            row for row in all_appointment_rows if row["_source_job_id"] not in held_jobs
        ]
        appointment_report = _report(entity="appointment", version="hcp_source4_job_appointments_api_v1", columns=APPOINTMENT_COLUMNS, rows=appointment_rows)
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
            raise SafeEvidenceError("appointment_transformation_incomplete", appointment_report.transformation_sha256)

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
            str(jobs_by_id[identity]["customer"]["id"])
            for identity in open_job_ids
        }
        continuity_estimates = {
            str(item["id"]): item
            for item in estimates_raw
            if item["id"] in day_one_ids
            and isinstance(item.get("customer"), Mapping)
            and item["customer"].get("id") in open_customer_ids
        }
        if len(continuity_estimates) != 89:
            raise SafeEvidenceError("estimate_continuity_scope_mismatch", canonical_sha256(len(continuity_estimates)))
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
            raise SafeEvidenceError("open_linked_estimate_count_mismatch", canonical_sha256(len(open_linked)))
        unlinked_binding = bindings["HCP1A.UNLINKED_DAY1_ESTIMATES.V1"]
        unlinked_ids = set(unlinked_binding.get("native_estimate_ids", []))
        estimate_rows: list[dict[str, Any]] = []
        unlinked_commands: list[UnlinkedEstimateEvidenceCommand] = []
        linked_relationship_exceptions = 0
        for source in estimates_raw:
            raw_options = source.get("options")
            options: list[object] = raw_options if isinstance(raw_options, list) else []
            if source["id"] in unlinked_ids:
                unlinked_commands.append(UnlinkedEstimateEvidenceCommand(
                    native_estimate_id=str(source["id"]), source_digest=canonical_sha256(source),
                    package_digest=customers.package_digest,
                    owner_binding_digest=receipts["HCP1A.UNLINKED_DAY1_ESTIMATES.V1"],
                    native_customer_id=str(source.get("customer", {}).get("id")) if isinstance(source.get("customer"), Mapping) else None,
                    native_service_location_id=str(source.get("address", {}).get("id")) if isinstance(source.get("address"), Mapping) else None,
                    source_status=str(source.get("work_status")), option_evidence=tuple(dict(item) for item in options if isinstance(item, Mapping)),
                    source_timestamps={"created_at": source.get("created_at"), "updated_at": source.get("updated_at")},
                    source_context={"provider": "housecall_pro", "authoritative_job_link": False},
                ))
            elif source["id"] in open_linked and len(open_linked[str(source["id"])]) == 1:
                job_id, selected = next(iter(open_linked[str(source["id"])]))
                if job_id not in held_jobs:
                    estimate_rows.append({**source, "_source_digest": canonical_sha256(source), "_source_job_id": job_id, "_selected_option_id": selected, "_owner_disposition": "MIGRATE_AUTHORITATIVE_JOB_LINK"})
            elif source["id"] in open_linked:
                linked_relationship_exceptions += 1
        if len(unlinked_commands) != 24:
            raise SafeEvidenceError("unlinked_estimate_accounting_mismatch", canonical_sha256(len(unlinked_commands)))
        estimate_report = _report(entity="estimate", version="hcp_source4_estimate_options_api_v1", columns=ESTIMATE_COLUMNS, rows=estimate_rows)
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
            raise SafeEvidenceError("estimate_transformation_incomplete", estimate_report.transformation_sha256)

        financial_hold_ids = {str(row["id"]) for row in invoices_raw if row.get("due_amount") not in {0, "0", None}}
        if len(financial_hold_ids) != 298:
            raise SafeEvidenceError("financial_hold_accounting_mismatch", canonical_sha256(len(financial_hold_ids)))
        invoice_rows: list[dict[str, Any]] = []
        payment_rows: list[dict[str, Any]] = []
        for source in invoices_raw:
            if source["id"] in financial_hold_ids or source.get("job_id") in held_jobs:
                continue
            invoice_rows.append({**source, "_source_digest": canonical_sha256(source), "_owner_disposition": "PRESERVE_SOURCE_FINANCIAL_ASSERTION"})
            for payment in source.get("payments", []):
                if isinstance(payment, Mapping):
                    payment_rows.append({**payment, "_source_digest": canonical_sha256(payment), "_source_invoice_id": source["id"], "_owner_disposition": "SOURCE_ASSERTION_ONLY"})
        _unique(payment_rows, "invpay_")
        invoice_report = _report(entity="invoice", version="hcp_source4_invoices_api_v1", columns=INVOICE_COLUMNS, rows=invoice_rows)
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
        payment_report = _report(entity="payment", version="hcp_source4_invoice_payments_api_v1", columns=PAYMENT_COLUMNS, rows=payment_rows)
        if payment_report.rejected or payment_report.duplicate:
            raise SafeEvidenceError("financial_transformation_incomplete", canonical_sha256([invoice_report.transformation_sha256, payment_report.transformation_sha256]))

        notes_raw: list[dict[str, Any]] = []
        for job in jobs_raw:
            for note in job.get("notes", []):
                if isinstance(note, Mapping):
                    notes_raw.append({**note, "_source_digest": canonical_sha256(note), "_source_job_id": job["id"], "_occurred_at": None, "_owner_disposition": "PRESERVE_PARTIAL_PROVENANCE"})
        note_report = _report(entity="note", version="hcp_source4_job_notes_partial_api_v1", columns=NOTE_COLUMNS, rows=notes_raw)
        if note_report.accepted or note_report.duplicate or note_report.rejected != len(notes_raw):
            raise SafeEvidenceError("note_partial_provenance_accounting_mismatch", note_report.transformation_sha256)

        employee_binding = bindings["HCP1A.EMPLOYEE_CROSSWALK.V1"]
        dispositions = {str(item["native_id"]): str(item["selected_alternative"]) for item in employee_binding.get("record_dispositions", []) if isinstance(item, Mapping)}
        if set(dispositions) != {str(row["id"]) for row in employees_raw}:
            raise SafeEvidenceError("employee_disposition_identity_mismatch", canonical_sha256(dispositions))
        employees = tuple(EmployeeCandidateCommand(
            native_employee_id=str(row["id"]), disposition=dispositions[str(row["id"])],
            source_digest=canonical_sha256(row), owner_receipt_digest=receipts["HCP1A.EMPLOYEE_CROSSWALK.V1"],
            first_name=str(row.get("first_name") or "").strip() or None if dispositions[str(row["id"])] == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE" else None,
            last_name=str(row.get("last_name") or "").strip() or None if dispositions[str(row["id"])] == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE" else None,
            display_name=(f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or None) if dispositions[str(row["id"])] == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE" else None,
            job_title=str(row.get("role") or "").strip() or None if dispositions[str(row["id"])] == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE" else None,
        ) for row in sorted(employees_raw, key=lambda item: str(item["id"])))
        for item in employees: item.validate()
        if sum(item.disposition == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE" for item in employees) != 6:
            raise SafeEvidenceError("employee_create_count_mismatch", "6" * 64)

        holds = tuple(sorted((
            *(
                HoldCommand(entity_kind="job", native_id=identity, hold_code="CANCELED_JOB_BALANCE_RECONCILIATION", evidence_digest=canonical_sha256(jobs_by_id[identity]), reconciliation_key=canonical_sha256(["job", identity]), owner_disposition="HOLD_OPERATIONAL_RECONCILE_BALANCE")
                for identity in held_jobs
            ),
            *(
                HoldCommand(entity_kind="invoice", native_id=identity, hold_code="UNRESOLVED_FINANCIAL_BALANCE", evidence_digest=canonical_sha256(next(row for row in invoices_raw if row["id"] == identity)), reconciliation_key=canonical_sha256(["invoice", identity]))
                for identity in financial_hold_ids
            ),
        ), key=lambda item: (item.entity_kind, item.native_id)))

        source_counts = {
            "customer": 5296, "contact": 4148, "service_location": 5633,
            "employee": len(employees_raw), "job": len(jobs_raw),
            "appointment": len(all_appointment_rows), "estimate": len(estimates_raw),
            "invoice": len(invoices_raw), "payment": sum(len(row.get("payments", [])) for row in invoices_raw),
            "note": len(notes_raw), "hold": len(holds), "unlinked_estimate": len(unlinked_commands),
        }
        persisted = {
            "customer": 5296, "contact": 4148, "service_location": 5339, "employee": 6,
            "job": len(job_report.records), "appointment": len(appointment_report.records),
            "estimate": len(estimate_report.records), "invoice": len(invoice_report.records),
            "payment": len(payment_report.records), "note": 0, "hold": len(holds),
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
                    native_identity_sha256=hashlib.sha256(native_id.encode()).hexdigest(),
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
        accepted_appointment_ids = {item.source_id for item in appointment_report.records}
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
                "EXPLICIT_EXCEPTION" if is_exception else "INTENTIONALLY_NON_APPLICABLE",
                "source_invoice_contract_exception" if is_exception else "held_or_unavailable_job_parent",
                row,
                "hcp_source4_invoices_api_v1",
            )
        accepted_payment_ids = {item.source_id for item in payment_report.records}
        for invoice in invoices_raw:
            for payment in invoice.get("payments", []):
                if isinstance(payment, Mapping) and payment.get("id") not in accepted_payment_ids:
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
            customer_lineage=5296, location_identities=5339, location_exceptions=294,
            employee_crosswalks=7, employee_candidates=6, employee_excluded=1,
            note_outcomes={
                "persisted": 0,
                "duplicate": 0,
                "exception": len(notes_raw),
                "rejected": 0,
            },
            holds_by_code={"CANCELED_JOB_BALANCE_RECONCILIATION": 296, "UNRESOLVED_FINANCIAL_BALANCE": 298},
            hold_counts=hold_counts, unlinked_estimates=len(unlinked_commands),
            transformed_counts={key: value for key, value in persisted.items()},
            persisted_counts=persisted, exception_counts=exceptions, rejection_counts={},
            unresolved_counts={}, non_applicable_counts=non_applicable,
        )
        requirements.validate_reconciliation(source_counts)
        collection = _safe_json(self.package_root / "collection-manifest.json")
        if not isinstance(collection, Mapping):
            raise SafeEvidenceError("collection_manifest_shape_invalid", "7" * 64)
        contracts: dict[str, object] = {
            "hybrid_customer_admission_digest": customers.admission.digest,
            "customer_parent_closure_digest": customers.parent_closure.digest,
            "builder_version": BUILDER_VERSION,
            "job": "hcp_source4_jobs_api_v1", "appointment": "hcp_source4_job_appointments_api_v1",
            "estimate": "hcp_source4_estimate_options_api_v1", "invoice": "hcp_source4_invoices_api_v1",
            "payment": "hcp_source4_invoice_payments_api_v1", "note": "hcp_source4_job_notes_partial_api_v1",
        }
        command_identities = {
            "employees": [_command_digest(asdict(item)) for item in employees],
            "jobs": [_command_digest(asdict(item)) for item in job_report.records],
            "appointments": [_command_digest(asdict(item)) for item in appointment_report.records],
            "estimates": [_command_digest(asdict(item)) for item in estimate_report.records],
            "unlinked_estimates": sorted(
                item.evidence_digest for item in unlinked_commands
            ),
            "invoices": [_command_digest(asdict(item)) for item in invoice_report.records],
            "payments": [_command_digest(asdict(item)) for item in payment_report.records],
            "notes": [], "holds": [item.hold_digest for item in holds],
            "plan_outcomes": [item.outcome_digest for item in plan_outcomes],
        }
        plan_payload = {
            "builder": BUILDER_VERSION, "package": customers.package_digest,
            "collection": collection.get("manifest_sha256"), "receipts": receipts,
            "hybrid": customers.admission.digest, "closure": customers.parent_closure.digest,
            "company": str(company_id), "branch": str(branch_id), "actor": str(actor_id),
            "commands": command_identities, "source_counts": source_counts,
            "requirements": asdict(requirements),
        }
        plan_digest = canonical_sha256(plan_payload)
        plan_id = uuid5(PLAN_NAMESPACE, plan_digest)
        master = MasterRunCommand(
            package_digest=customers.package_digest,
            collection_digests={"manifest": collection.get("manifest_sha256"), "plan_digest": plan_digest},
            transformation_contracts=contracts,
            owner_receipts=dict(receipts),
            schema_head=SCHEMA_HEAD, implementation_version=ORCHESTRATOR_VERSION,
            supported_entities=tuple(sorted({"customer", "contact", "service_location", "employee", "job", "appointment", "estimate", "invoice", "payment", "note"})),
            baseline_counts=dict(sorted(baseline_counts.items())), source_counts=source_counts,
        )
        master.validate()
        plan = HcpMigration2ExecutionPlan(
            master=master, customers=customers, employees=employees,
            jobs=_typed(job_report, __import__('app.operational_migration.service', fromlist=['JobMigrationRecord']).JobMigrationRecord),
            appointments=_typed(appointment_report, __import__('app.operational_migration.service', fromlist=['AppointmentMigrationRecord']).AppointmentMigrationRecord),
            estimates=_typed(estimate_report, __import__('app.operational_migration.financial', fromlist=['EstimateMigrationRecord']).EstimateMigrationRecord),
            unlinked_estimates=tuple(sorted(unlinked_commands, key=lambda item: item.native_estimate_id)),
            invoices=_typed(invoice_report, __import__('app.operational_migration.financial', fromlist=['InvoiceMigrationRecord']).InvoiceMigrationRecord),
            payments=_typed(payment_report, __import__('app.operational_migration.financial', fromlist=['PaymentMigrationRecord']).PaymentMigrationRecord),
            notes=(), holds=holds, plan_outcomes=plan_outcomes,
            completion=requirements, verified_owner_receipts=receipts,
            plan_id=plan_id, plan_digest=plan_digest, builder_version=BUILDER_VERSION,
        )
        plan.validate()
        summary = HcpMigration2PlanSummary(
            plan_id, plan_digest, BUILDER_VERSION, source_counts,
            {key: len(value) for key, value in {
                "employees": employees, "jobs": plan.jobs, "appointments": plan.appointments,
                "estimates": plan.estimates, "unlinked_estimates": plan.unlinked_estimates,
                "invoices": plan.invoices, "payments": plan.payments,
                "notes": plan.notes, "holds": holds,
                "plan_outcomes": plan_outcomes,
            }.items()},
            {"persisted": persisted, "held": hold_counts, "exceptions": exceptions, "non_applicable": non_applicable},
        )
        return plan, summary


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

    async def prepare(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
    ) -> tuple[HcpMigration2ExecutionPlan, HcpMigration2PlanSummary]:
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
        if any(counts.values()):
            raise SafeEvidenceError(
                "rehearsal_target_baseline_not_pristine", canonical_sha256(counts)
            )
        return self.builder.build(baseline_counts=counts)

    async def execute(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
    ) -> dict[str, object]:
        plan, summary = await self.prepare(
            factory, context=context, target=target
        )
        result = await self.runner.execute(
            factory, context=context, target=target, plan=plan
        )
        return {"plan": summary.safe_output(), "run": result}
