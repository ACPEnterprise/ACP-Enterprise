"""Registered transformations for the sealed HCP.SOURCE.4 acquired layouts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from app.operational_migration.cutover import HistoryMigrationRecord
from app.operational_migration.financial import (
    EstimateMigrationRecord,
    FinancialLineItemRecord,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
)
from app.operational_migration.transformation import (
    SourceField,
    TransformationContract,
    TransformationValidationError,
)

SOURCE4_PACKAGE_DIGEST = (
    "f77e3e09457efcbf6d42137be1af43be6ad0adbea8eab2c12ca320730fd96901"
)
CONTRACT_PREFIX = "hcp_source4"

JOB_COLUMNS = (
    "address",
    "assigned_employees",
    "assigned_route_template_id",
    "canceled_at",
    "company_id",
    "company_name",
    "created_at",
    "customer",
    "deleted_at",
    "description",
    "id",
    "invoice_number",
    "job_fields",
    "lead_source",
    "locked_at",
    "notes",
    "original_estimate_id",
    "original_estimate_uuids",
    "outstanding_balance",
    "recurrence_id",
    "recurrence_number",
    "recurrence_rule",
    "recurrence_status",
    "schedule",
    "subtotal",
    "tags",
    "total_amount",
    "updated_at",
    "work_status",
    "work_timestamps",
    "_source_digest",
    "_owner_disposition",
)

ESTIMATE_COLUMNS = (
    "address",
    "assigned_employees",
    "assigned_route_template_id",
    "company_id",
    "company_name",
    "created_at",
    "customer",
    "estimate_fields",
    "estimate_number",
    "id",
    "lead_source",
    "options",
    "schedule",
    "updated_at",
    "work_status",
    "work_timestamps",
    "_source_digest",
    "_source_job_id",
    "_selected_option_id",
    "_owner_disposition",
)

INVOICE_COLUMNS = (
    "amount",
    "discounts",
    "display_due_concept",
    "due_amount",
    "due_at",
    "due_concept",
    "id",
    "invoice_date",
    "invoice_number",
    "items",
    "job_id",
    "paid_at",
    "payments",
    "refunds",
    "sent_at",
    "service_date",
    "status",
    "subtotal",
    "taxes",
    "_source_digest",
    "_owner_disposition",
)

APPOINTMENT_COLUMNS = (
    "anytime",
    "arrival_window_minutes",
    "dispatched_employees_ids",
    "end_time",
    "id",
    "start_date",
    "start_time",
    "_source_digest",
    "_source_job_id",
    "_source_customer_id",
    "_source_location_id",
    "_job_status",
    "_owner_disposition",
)

PAYMENT_COLUMNS = (
    "amount",
    "category",
    "id",
    "note",
    "paid_at",
    "payment_method",
    "status",
    "surcharge_fee_amount",
    "_source_digest",
    "_source_invoice_id",
    "_owner_disposition",
)

NOTE_COLUMNS = (
    "content",
    "id",
    "_source_digest",
    "_source_job_id",
    "_occurred_at",
    "_owner_disposition",
)

CUSTOMER_KEYS = frozenset(
    {
        "company",
        "company_id",
        "company_name",
        "created_at",
        "email",
        "first_name",
        "home_number",
        "id",
        "kind",
        "last_name",
        "lead_source",
        "mobile_number",
        "notes",
        "notifications_enabled",
        "tags",
        "updated_at",
        "work_number",
    }
)
ADDRESS_KEYS = frozenset(
    {
        "city",
        "country",
        "id",
        "latitude",
        "longitude",
        "state",
        "street",
        "street_line_2",
        "type",
        "zip",
    }
)
EMPLOYEE_KEYS = frozenset(
    {
        "avatar_url",
        "color_hex",
        "company_id",
        "company_name",
        "created_at",
        "email",
        "first_name",
        "id",
        "last_name",
        "mobile_number",
        "permissions",
        "role",
        "tags",
    }
)
SCHEDULE_KEYS = frozenset(
    {
        "appointments",
        "arrival_window",
        "scheduled_end",
        "scheduled_end_local",
        "scheduled_start",
        "scheduled_start_local",
        "time_zone",
    }
)


def _fields(columns: tuple[str, ...]) -> tuple[SourceField, ...]:
    return tuple(SourceField(item, required=False) for item in columns)


def _digest(row: Mapping[str, object]) -> str:
    value = row.get("_source_digest")
    if not isinstance(value, str) or len(value) != 64:
        raise TransformationValidationError(
            "source_digest_missing", fields=("_source_digest",)
        )
    return value


def _metadata(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "provider": "housecall_pro",
        "source_package_digest": SOURCE4_PACKAGE_DIGEST,
        "source_digest": _digest(row),
        "owner_disposition": row["_owner_disposition"],
        "source_reported_state": True,
        "accepted_accounting_truth": False,
    }


def _object(row: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = row[key]
    if not isinstance(value, Mapping):
        raise TransformationValidationError("relationship_invalid", fields=(key,))
    return value


def _exact_object(
    row: Mapping[str, object], key: str, expected: frozenset[str]
) -> Mapping[str, object]:
    value = _object(row, key)
    if set(value) != expected:
        raise TransformationValidationError("changed_nested_layout", fields=(key,))
    return value


def _exact_list(
    row: Mapping[str, object], key: str, expected: frozenset[str]
) -> list[object]:
    value = row[key]
    if not isinstance(value, list):
        raise TransformationValidationError("changed_nested_layout", fields=(key,))
    if any(not isinstance(item, Mapping) or set(item) != expected for item in value):
        raise TransformationValidationError("changed_nested_layout", fields=(key,))
    return value


def _id(value: object, field: str, prefix: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise TransformationValidationError("native_identity_invalid", fields=(field,))
    return value


def _datetime(value: object, field: str, *, required: bool = False) -> datetime | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise TransformationValidationError("timestamp_invalid", fields=(field,))
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TransformationValidationError(
            "timestamp_invalid", fields=(field,)
        ) from error


def _money(value: object, field: str) -> Decimal:
    if value is None:
        raise TransformationValidationError("money_missing", fields=(field,))
    try:
        return (Decimal(str(value)) / Decimal(100)).quantize(Decimal("0.01"))
    except Exception as error:
        raise TransformationValidationError("money_invalid", fields=(field,)) from error


JOB_STATUS = {
    "needs scheduling": "ready",
    "scheduled": "ready",
    "in progress": "in_progress",
    "complete rated": "completed",
    "complete unrated": "completed",
    "pro canceled": "cancelled",
    "user canceled": "cancelled",
}


def build_job(row: Mapping[str, object]) -> JobMigrationRecord:
    status = row["work_status"]
    if status not in JOB_STATUS:
        raise TransformationValidationError(
            "unsupported_job_status", fields=("work_status",)
        )
    customer = _exact_object(row, "customer", CUSTOMER_KEYS)
    address = _exact_object(row, "address", ADDRESS_KEYS)
    timestamps = _exact_object(
        row,
        "work_timestamps",
        frozenset({"completed_at", "on_my_way_at", "started_at"}),
    )
    schedule = _exact_object(row, "schedule", SCHEDULE_KEYS)
    employees = _exact_list(row, "assigned_employees", EMPLOYEE_KEYS)
    _exact_object(row, "job_fields", frozenset({"business_unit", "job_type"}))
    _exact_list(row, "notes", frozenset({"content", "id"}))
    employee_ids = tuple(
        _id(employee.get("id"), "assigned_employees.id", "pro_")
        for employee in employees
        if isinstance(employee, Mapping)
    )
    return JobMigrationRecord(
        source_id=_id(row["id"], "id", "job_"),
        source_customer_id=_id(customer.get("id"), "customer.id", "cus_"),
        source_service_location_id=_id(address.get("id"), "address.id", "adr_"),
        status=JOB_STATUS[str(status)],
        source_job_number=(
            str(row["invoice_number"]) if row["invoice_number"] else None
        ),
        scheduled_start_at=_datetime(
            schedule.get("scheduled_start"), "schedule.scheduled_start"
        ),
        scheduled_end_at=_datetime(
            schedule.get("scheduled_end"), "schedule.scheduled_end"
        ),
        started_at=_datetime(
            timestamps.get("started_at"), "work_timestamps.started_at"
        ),
        completed_at=_datetime(
            timestamps.get("completed_at"), "work_timestamps.completed_at"
        ),
        description=str(row["description"]) if row["description"] else None,
        assigned_technician_source_ids=employee_ids,
        external_metadata={**_metadata(row), "source_status": status},
    )


def build_appointment(row: Mapping[str, object]) -> AppointmentMigrationRecord:
    dispatched = row["dispatched_employees_ids"]
    if not isinstance(dispatched, list):
        raise TransformationValidationError(
            "relationship_invalid", fields=("dispatched_employees_ids",)
        )
    start = _datetime(row["start_time"], "start_time", required=True)
    end = _datetime(row["end_time"], "end_time", required=True)
    assert start is not None and end is not None
    job_status = str(row["_job_status"])
    status = (
        "completed"
        if job_status.startswith("complete")
        else "cancelled"
        if "canceled" in job_status
        else "scheduled"
    )
    return AppointmentMigrationRecord(
        source_id=_id(row["id"], "id", "appt_"),
        source_job_id=_id(row["_source_job_id"], "_source_job_id", "job_"),
        source_customer_id=_id(
            row["_source_customer_id"], "_source_customer_id", "cus_"
        ),
        source_service_location_id=_id(
            row["_source_location_id"], "_source_location_id", "adr_"
        ),
        status=status,
        arrival_window_start_at=start,
        arrival_window_end_at=end,
        duration_minutes=max(0, int((end - start).total_seconds() // 60)),
        assigned_technician_source_ids=tuple(
            _id(value, "dispatched_employees_ids", "pro_") for value in dispatched
        ),
        external_metadata={
            **_metadata(row),
            "transformation_contract": "hcp_source4_job_notes_partial_api_v1",
            "provenance_completeness": "PARTIAL",
            "author_provenance": "UNAVAILABLE",
            "timestamp_provenance": "SOURCE_REPORTED_WHERE_AVAILABLE",
            "attachment_availability": "NOT_ASSERTED",
        },
    )


def build_estimate(row: Mapping[str, object]) -> EstimateMigrationRecord:
    _exact_object(row, "customer", CUSTOMER_KEYS)
    _exact_object(row, "address", ADDRESS_KEYS)
    _exact_object(
        row,
        "work_timestamps",
        frozenset({"completed_at", "on_my_way_at", "started_at"}),
    )
    _exact_object(row, "schedule", SCHEDULE_KEYS)
    _exact_list(row, "assigned_employees", EMPLOYEE_KEYS)
    _exact_object(row, "estimate_fields", frozenset({"business_unit", "job_type"}))
    options = _exact_list(
        row,
        "options",
        frozenset(
            {
                "approval_status",
                "created_at",
                "id",
                "message_from_pro",
                "name",
                "notes",
                "option_number",
                "status",
                "tags",
                "total_amount",
                "updated_at",
            }
        ),
    )
    selected_id = _id(row["_selected_option_id"], "_selected_option_id", "est_")
    selected = next(
        (
            item
            for item in options
            if isinstance(item, Mapping) and item.get("id") == selected_id
        ),
        None,
    )
    if selected is None:
        raise TransformationValidationError(
            "authoritative_estimate_option_missing", fields=("_selected_option_id",)
        )
    approval = str(selected.get("approval_status") or "")
    status = (
        "approved"
        if "approved" in approval
        else "declined"
        if "declined" in approval
        else "presented"
    )
    total = _money(selected.get("total_amount"), "options.total_amount")
    return EstimateMigrationRecord(
        source_id=_id(row["id"], "id", "csr_"),
        source_job_id=_id(row["_source_job_id"], "_source_job_id", "job_"),
        status=status,
        currency="USD",
        subtotal_amount=total,
        tax_amount=Decimal("0.00"),
        total_amount=total,
        line_items=(
            FinancialLineItemRecord(
                selected_id,
                str(selected.get("name") or "HCP estimate option"),
                Decimal(1),
                total,
                total,
            ),
        ),
        presented_at=_datetime(selected.get("created_at"), "options.created_at"),
        external_metadata={
            **_metadata(row),
            "source_status": row["work_status"],
            "option_status": selected.get("status"),
            "approval_status": selected.get("approval_status"),
        },
    )


def build_invoice(row: Mapping[str, object]) -> InvoiceMigrationRecord:
    raw_status = str(row["status"])
    status = {
        "paid": "paid",
        "canceled": "void",
        "voided": "void",
        "draft": "draft",
    }.get(raw_status, "issued")
    subtotal = _money(row["subtotal"], "subtotal")
    total = _money(row["amount"], "amount")
    tax = total - subtotal
    if tax < 0:
        raise TransformationValidationError(
            "invoice_amount_conflict", fields=("amount", "subtotal")
        )
    items = _exact_list(
        row,
        "items",
        frozenset(
            {
                "amount",
                "id",
                "invoiced_amount",
                "name",
                "qty_in_hundredths",
                "type",
                "unit_cost",
                "unit_price",
            }
        ),
    )
    _exact_list(
        row,
        "payments",
        frozenset(
            {
                "amount",
                "category",
                "id",
                "note",
                "paid_at",
                "payment_method",
                "status",
                "surcharge_fee_amount",
            }
        ),
    )
    _exact_list(
        row,
        "refunds",
        frozenset(
            {
                "amount",
                "category",
                "id",
                "payment_method",
                "refunded_at",
                "status",
                "surcharge_fee_amount",
                "tip_amount",
            }
        ),
    )
    _exact_list(row, "discounts", frozenset({"amount", "description", "id", "name"}))
    _exact_list(row, "taxes", frozenset({"amount", "id", "name", "rate"}))
    line_items = tuple(
        FinancialLineItemRecord(
            _id(item.get("id"), "items.id", "invitm_"),
            str(item.get("name") or "HCP invoice item"),
            Decimal(str(item.get("qty_in_hundredths") or 100)) / Decimal(100),
            _money(item.get("unit_price"), "items.unit_price"),
            _money(item.get("amount"), "items.amount"),
        )
        for item in items
        if isinstance(item, Mapping)
    )
    return InvoiceMigrationRecord(
        source_id=_id(row["id"], "id", "invoice_"),
        source_job_id=_id(row["job_id"], "job_id", "job_"),
        status=status,
        currency="USD",
        subtotal_amount=subtotal,
        tax_amount=tax,
        total_amount=total,
        line_items=line_items,
        issued_at=_datetime(row["invoice_date"], "invoice_date"),
        external_metadata={
            **_metadata(row),
            "source_status": raw_status,
            "financial_assertion_only": True,
        },
    )


def build_payment(row: Mapping[str, object]) -> PaymentMigrationRecord:
    raw_status = str(row["status"])
    return PaymentMigrationRecord(
        source_id=_id(row["id"], "id", "invpay_"),
        source_invoice_id=_id(
            row["_source_invoice_id"], "_source_invoice_id", "invoice_"
        ),
        status="succeeded"
        if raw_status == "succeeded"
        else "failed"
        if raw_status == "failed"
        else "pending",
        currency="USD",
        amount=_money(row["amount"], "amount"),
        paid_at=_datetime(row["paid_at"], "paid_at"),
        method=str(row["payment_method"]) if row["payment_method"] else None,
        external_metadata={
            **_metadata(row),
            "source_status": raw_status,
            "payment_application": "UNAVAILABLE",
            "accepted_accounting_truth": False,
        },
    )


def build_note(row: Mapping[str, object]) -> HistoryMigrationRecord:
    occurred_at = _datetime(row["_occurred_at"], "_occurred_at")
    if occurred_at is None:
        raise TransformationValidationError(
            "note_timestamp_unavailable", fields=("_occurred_at",)
        )
    if not isinstance(row["content"], str) or not row["content"].strip():
        raise TransformationValidationError("note_content_missing", fields=("content",))
    return HistoryMigrationRecord(
        source_id=_id(row["id"], "id", "nte_"),
        parent_type="job",
        source_parent_id=_id(row["_source_job_id"], "_source_job_id", "job_"),
        entry_type="note",
        occurred_at=occurred_at,
        summary_text=str(row["content"]),
        activity_category="source_note",
        external_metadata=_metadata(row),
    )


def source4_contracts() -> tuple[TransformationContract, ...]:
    specs = (
        ("job", "hcp_source4_jobs_api_v1", JOB_COLUMNS, build_job),
        (
            "appointment",
            "hcp_source4_job_appointments_api_v1",
            APPOINTMENT_COLUMNS,
            build_appointment,
        ),
        (
            "estimate",
            "hcp_source4_estimate_options_api_v1",
            ESTIMATE_COLUMNS,
            build_estimate,
        ),
        ("invoice", "hcp_source4_invoices_api_v1", INVOICE_COLUMNS, build_invoice),
        (
            "payment",
            "hcp_source4_invoice_payments_api_v1",
            PAYMENT_COLUMNS,
            build_payment,
        ),
        ("note", "hcp_source4_job_notes_partial_api_v1", NOTE_COLUMNS, build_note),
    )
    return tuple(
        TransformationContract(
            provider="housecall_pro",
            entity=entity,  # type: ignore[arg-type]
            version=version,
            fields=_fields(columns),
            builder=builder,
            exact_columns=True,
        )
        for entity, version, columns, builder in specs
    )
