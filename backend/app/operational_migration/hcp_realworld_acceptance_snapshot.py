"""Read-only SOURCE.4 native continuity snapshot for real-world acceptance."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CONTRACT: Final = "hcp-source4-realworld-acceptance-snapshot/v2"
SOURCE: Final = "housecall_pro_source4"
JOURNEY_SAMPLE_SIZE: Final = 20

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
        ).mappings().one()
        families[family] = {
            "admitted": int(row["admitted"]),
            "projected": int(row["projected"]),
            "missing_native_projection": int(row["admitted"] - row["projected"]),
        }

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
    ).mappings().one()

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
                    LIMIT 20
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
        "held_by_entity_kind": holds,
        "current_operations": {key: int(value or 0) for key, value in operations.items()},
        "historical_customer_journeys": [
            _journey(dict(row)) for row in journeys
        ],
        "historical_customer_journey_sample_size": JOURNEY_SAMPLE_SIZE,
        "limitations": [
            "attachments_have_no_native_source_identity_contract",
            "employee_source_identity_is_not_a_customer_graph_family",
            "source_acquired_and_legacy_only_counts_require_sealed_package_reconciliation",
            "calendar_lane_membership_requires_deployed_schedule_acceptance",
        ],
    }
    document["digest"] = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return document


def _journey(row: Mapping[str, Any]) -> dict[str, object]:
    value = {
        key: str(item) if isinstance(item, UUID) else item
        for key, item in row.items()
    }
    required = ("locations", "jobs", "appointments", "estimates", "invoices", "payments")
    missing = [family for family in required if int(value.get(family) or 0) == 0]
    return {
        **value,
        "acceptance": "COMPLETE" if not missing else "SOURCE_EVIDENCE_GAP",
        "missing_families": missing,
    }
