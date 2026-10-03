"""Read-only SOURCE.4 native continuity snapshot for real-world acceptance."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CONTRACT: Final = "hcp-source4-realworld-acceptance-snapshot/v1"
SOURCE: Final = "housecall_pro_source4"

_FAMILIES: Final = {
    "customers": (
        "customer_source_identities",
        "customers",
        "customer_id",
        "n.company_id = i.company_id",
    ),
    "locations": (
        "service_location_source_identities",
        "service_locations",
        "service_location_id",
        (
            "EXISTS (SELECT 1 FROM customers owner "
            "WHERE owner.id = n.customer_id AND owner.company_id = i.company_id)"
        ),
    ),
    "jobs": (
        "operational_migration_job_source_identities",
        "jobs",
        "job_id",
        "n.company_id = i.company_id",
    ),
    "appointments": (
        "operational_migration_appointment_source_identities",
        "appointments",
        "appointment_id",
        "n.company_id = i.company_id",
    ),
    "estimates": (
        "operational_migration_estimate_source_identities",
        "estimates",
        "estimate_id",
        "n.company_id = i.company_id",
    ),
    "invoices": (
        "operational_migration_invoice_source_identities",
        "invoices",
        "invoice_id",
        "n.company_id = i.company_id",
    ),
    "payments": (
        "operational_migration_payment_source_identities",
        "payments",
        "payment_id",
        "n.company_id = i.company_id",
    ),
}


async def build_realworld_snapshot(
    session: AsyncSession,
    *,
    company_id: UUID,
    branch_id: UUID,
    observed_at: datetime,
) -> dict[str, object]:
    """Account for persisted SOURCE.4 identities without taking write locks."""
    await session.execute(text("SET TRANSACTION READ ONLY"))
    scope = {"company_id": company_id, "branch_id": branch_id, "source": SOURCE}
    families: dict[str, object] = {}
    for family, (
        identity_table,
        native_table,
        target_column,
        native_scope,
    ) in _FAMILIES.items():
        branch_filter = "AND i.branch_id = :branch_id" if family != "customers" else ""
        row = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT count(*) AS admitted,
                           count(n.id) AS projected
                    FROM {identity_table} i
                    LEFT JOIN {native_table} n
                      ON n.id = i.{target_column}
                     AND {native_scope}
                    WHERE i.company_id = :company_id
                      AND i.source_system = :source
                      {branch_filter}
                    """
                    ),
                    scope,
                )
            )
            .mappings()
            .one()
        )
        families[family] = {
            "admitted": int(row["admitted"]),
            "projected": int(row["projected"]),
            "missing_native_projection": int(row["admitted"] - row["projected"]),
        }

    invoice_parity = (
        (
            await session.execute(
                text(
                    """
                    SELECT count(DISTINCT isi.id) AS invoices,
                           count(DISTINCT isi.id) FILTER (
                             WHERE isi.customer_id IS NOT NULL
                               AND isi.job_id IS NOT NULL
                           ) AS customer_job_linked,
                           (SELECT count(*)
                              FROM operational_migration_invoice_line_item_source_identities ilsi
                              JOIN operational_migration_invoice_source_identities parent
                                ON parent.id = ilsi.invoice_source_identity_id
                             WHERE parent.company_id = :company_id
                               AND parent.branch_id = :branch_id
                               AND parent.source_system = :source
                           ) AS source_line_items,
                           count(DISTINCT i.id) FILTER (
                             WHERE i.open_amount > 0
                           ) AS open_ar_invoices,
                           coalesce(sum(i.open_amount) FILTER (
                             WHERE i.open_amount > 0
                           ), 0) AS open_ar_amount,
                           count(DISTINCT i.id) FILTER (
                             WHERE i.status = 'paid'
                           ) AS paid,
                           count(DISTINCT i.id) FILTER (
                             WHERE i.status IN ('issued','partially_paid','adjusted')
                           ) AS open_status
                    FROM operational_migration_invoice_source_identities isi
                    JOIN invoices i ON i.id = isi.invoice_id
                    WHERE isi.company_id = :company_id
                      AND isi.branch_id = :branch_id
                      AND isi.source_system = :source
                    """
                ),
                scope,
            )
        )
        .mappings()
        .one()
    )
    payment_parity = (
        (
            await session.execute(
                text(
                    """
                    SELECT count(DISTINCT psi.id) AS payment_assertions,
                           count(DISTINCT psi.id) FILTER (
                             WHERE isi.id IS NOT NULL
                           ) AS invoice_linked,
                           count(DISTINCT psi.id) FILTER (
                             WHERE psi.source_status = 'succeeded'
                           ) AS succeeded,
                           count(DISTINCT psi.id) FILTER (
                             WHERE psi.source_status <> 'succeeded'
                           ) AS non_succeeded
                    FROM operational_migration_payment_source_identities psi
                    LEFT JOIN operational_migration_invoice_source_identities isi
                      ON isi.id = psi.invoice_source_identity_id
                     AND isi.company_id = psi.company_id
                    WHERE psi.company_id = :company_id
                      AND psi.branch_id = :branch_id
                      AND psi.source_system = :source
                    """
                ),
                scope,
            )
        )
        .mappings()
        .one()
    )
    attachment_rows = (
        await session.execute(
            text(
                """
                SELECT parent_type, count(*) AS registered,
                       count(*) FILTER (
                         WHERE transfer_state = 'transferred'
                           AND validation_state = 'valid'
                       ) AS available,
                       count(*) FILTER (
                         WHERE transfer_state = 'failed'
                       ) AS failed,
                       count(*) FILTER (
                         WHERE retry_eligible
                       ) AS retryable
                FROM operational_migration_artifacts
                WHERE company_id = :company_id AND branch_id = :branch_id
                  AND source_system = :source
                GROUP BY parent_type ORDER BY parent_type
                """
            ),
            scope,
        )
    ).mappings()
    history_rows = (
        await session.execute(
            text(
                """
                SELECT parent_type, entry_type, count(*) AS admitted,
                       count(*) FILTER (
                         WHERE attribution_status = 'unresolved'
                       ) AS unresolved_employee
                FROM operational_migration_history_entries
                WHERE company_id = :company_id AND branch_id = :branch_id
                  AND source_system = :source
                GROUP BY parent_type, entry_type
                ORDER BY parent_type, entry_type
                """
            ),
            scope,
        )
    ).mappings()
    employee_parity = (
        (
            await session.execute(
                text(
                    """
                    WITH latest AS (
                      SELECT DISTINCT ON (native_employee_id)
                             native_employee_id, disposition, employee_id
                      FROM hcp_employee_source_crosswalks
                      WHERE company_id = :company_id AND branch_id = :branch_id
                      ORDER BY native_employee_id, evidence_version DESC
                    )
                    SELECT count(*) AS source_identities,
                           count(*) FILTER (
                             WHERE employee_id IS NOT NULL
                           ) AS canonical_bound,
                           count(*) FILTER (
                             WHERE disposition = 'EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS'
                           ) AS terminated_or_excluded,
                           count(*) FILTER (
                             WHERE disposition = 'CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE'
                               AND employee_id IS NULL
                           ) AS unresolved
                    FROM latest
                    """
                ),
                scope,
            )
        )
        .mappings()
        .one()
    )

    hold_rows = (
        await session.execute(
            text(
                """
                SELECT entity_kind, count(*) AS count
                FROM hcp_migration_holds
                WHERE company_id = :company_id AND branch_id = :branch_id
                  AND state = 'HELD'
                GROUP BY entity_kind ORDER BY entity_kind
                """
            ),
            scope,
        )
    ).mappings()
    holds = {str(row["entity_kind"]): int(row["count"]) for row in hold_rows}

    operations = (
        (
            await session.execute(
                text(
                    """
                SELECT
                  count(DISTINCT jsi.source_job_id) FILTER (
                    WHERE j.status IN ('ready','in_progress','paused')
                  ) AS open_jobs,
                  count(DISTINCT asi.source_appointment_id) FILTER (
                    WHERE a.status IN ('scheduled','confirmed')
                      AND a.arrival_window_start_at >= :observed_at
                  ) AS future_appointments,
                  count(DISTINCT asi.source_appointment_id) FILTER (
                    WHERE a.status IN ('scheduled','confirmed')
                      AND a.arrival_window_start_at >= :observed_at
                      AND j.id IS NOT NULL AND c.id IS NOT NULL AND l.id IS NOT NULL
                  ) AS dispatch_graph_complete
                FROM operational_migration_job_source_identities jsi
                JOIN jobs j ON j.id = jsi.job_id
                LEFT JOIN operational_migration_appointment_source_identities asi
                  ON asi.job_id = j.id AND asi.source_system = :source
                LEFT JOIN appointments a ON a.id = asi.appointment_id
                LEFT JOIN customers c ON c.id = j.customer_id
                LEFT JOIN service_locations l ON l.id = j.service_location_id
                WHERE jsi.company_id = :company_id
                  AND jsi.branch_id = :branch_id
                  AND jsi.source_system = :source
                """
                ),
                {**scope, "observed_at": observed_at},
            )
        )
        .mappings()
        .one()
    )

    journeys = list(
        (
            await session.execute(
                text(
                    """
                    SELECT csi.source_customer_id, c.id AS customer_id,
                           c.customer_number, c.display_name,
                           count(DISTINCT lsi.service_location_id) AS locations,
                           count(DISTINCT jsi.job_id) AS jobs,
                           count(DISTINCT asi.appointment_id) AS appointments,
                           count(DISTINCT esi.estimate_id) AS estimates,
                           count(DISTINCT isi.invoice_id) AS invoices,
                           count(DISTINCT psi.payment_id) AS payments
                    FROM customer_source_identities csi
                    JOIN customers c ON c.id = csi.customer_id
                    LEFT JOIN service_location_source_identities lsi
                      ON lsi.customer_id = c.id AND lsi.source_system = :source
                    LEFT JOIN operational_migration_job_source_identities jsi
                      ON jsi.customer_id = c.id AND jsi.source_system = :source
                    LEFT JOIN operational_migration_appointment_source_identities asi
                      ON asi.customer_id = c.id AND asi.source_system = :source
                    LEFT JOIN operational_migration_estimate_source_identities esi
                      ON esi.customer_id = c.id AND esi.source_system = :source
                    LEFT JOIN operational_migration_invoice_source_identities isi
                      ON isi.customer_id = c.id AND isi.source_system = :source
                    LEFT JOIN operational_migration_payment_source_identities psi
                      ON psi.customer_id = c.id AND psi.source_system = :source
                    WHERE csi.company_id = :company_id
                      AND csi.branch_id = :branch_id
                      AND csi.source_system = :source
                    GROUP BY csi.source_customer_id, c.id, c.customer_number,
                             c.display_name
                    ORDER BY count(DISTINCT jsi.job_id) DESC,
                             count(DISTINCT isi.invoice_id) DESC,
                             csi.source_customer_id
                    LIMIT 5
                    """
                ),
                scope,
            )
        ).mappings()
    )
    document: dict[str, Any] = {
        "contract": CONTRACT,
        "source_system": SOURCE,
        "company_id": str(company_id),
        "branch_id": str(branch_id),
        "observed_at": observed_at.isoformat(),
        "mutation_authority": "none",
        "families": families,
        "invoice_parity": {
            key: str(value) if key == "open_ar_amount" else int(value or 0)
            for key, value in invoice_parity.items()
        },
        "payment_parity": {
            **{key: int(value or 0) for key, value in payment_parity.items()},
            "refund_credit_authority": "SOURCE_PACKAGE_RECONCILIATION_REQUIRED",
        },
        "attachment_parity": {
            "by_parent_type": {
                str(row["parent_type"]): {
                    key: int(row[key] or 0)
                    for key in ("registered", "available", "failed", "retryable")
                }
                for row in attachment_rows
            },
            "source_acquisition": "HCP_UI_OR_SUPPORT_EXPORT_REQUIRED",
            "absence_is_authoritative": False,
        },
        "employee_source_parity": {
            key: int(value or 0) for key, value in employee_parity.items()
        },
        "history_parity": {
            "by_parent_and_type": {
                f"{row['parent_type']}:{row['entry_type']}": {
                    "admitted": int(row["admitted"] or 0),
                    "unresolved_employee": int(row["unresolved_employee"] or 0),
                }
                for row in history_rows
            },
            "source_scope": "SOURCE_REPORTED_PARTIAL_API",
        },
        "held_by_entity_kind": holds,
        "current_operations": {
            key: int(value or 0) for key, value in operations.items()
        },
        "historical_customer_journeys": [
            {
                key: str(value) if isinstance(value, UUID) else value
                for key, value in row.items()
            }
            for row in journeys
        ],
        "limitations": [
            "attachment_source_acquisition_requires_hcp_ui_or_support_export",
            "refund_credit_source_counts_require_sealed_package_reconciliation",
            "source_acquired_and_legacy_only_counts_require_sealed_package_reconciliation",
            "calendar_lane_membership_requires_deployed_schedule_acceptance",
        ],
    }
    document["digest"] = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return document
