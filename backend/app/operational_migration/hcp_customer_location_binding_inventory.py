"""Read-only Customer/Location binding evidence for broad SOURCE.4 history."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

CONTRACT: Final = "hcp-customer-location-binding-inventory/v1"
SOURCES: Final = ("housecall_pro", "housecall_pro_source4")


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize(rows: Iterable[RowMapping]) -> list[dict[str, object]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in rows
    ]


async def build_customer_location_binding_inventory(
    session: AsyncSession,
    *,
    company_id: UUID,
    branch_id: UUID,
    observed_at: datetime,
) -> dict[str, object]:
    """Export exact source/native bindings without matching or mutation."""
    await session.execute(text("SET TRANSACTION READ ONLY"))
    scope = {
        "company_id": company_id,
        "branch_id": branch_id,
        "legacy_source": SOURCES[0],
        "source4": SOURCES[1],
    }
    customers = _serialize(
        (
            await session.execute(
                text(
                    """
                    SELECT i.source_system, i.source_customer_id,
                           i.customer_id, i.branch_id, i.first_run_id,
                           i.created_at,
                           (c.id IS NOT NULL) AS native_exists,
                           (c.company_id = i.company_id) AS company_scope_matches
                    FROM customer_source_identities i
                    LEFT JOIN customers c ON c.id = i.customer_id
                    WHERE i.company_id = :company_id
                      AND (i.branch_id = :branch_id OR
                           (i.source_system = :legacy_source AND i.branch_id IS NULL))
                      AND i.source_system IN (:legacy_source, :source4)
                    ORDER BY i.source_system, i.source_customer_id
                    """
                ),
                scope,
            )
        ).mappings()
    )
    locations = _serialize(
        (
            await session.execute(
                text(
                    """
                    SELECT i.source_system, i.source_location_id,
                           i.service_location_id, i.customer_id,
                           csi.source_system AS parent_source_system,
                           csi.source_customer_id AS parent_source_customer_id,
                           i.branch_id, i.first_run_id, i.master_run_id,
                           i.source_digest, i.package_digest,
                           i.transformation_version, i.transformation_digest,
                           i.created_at,
                           (l.id IS NOT NULL) AS native_exists,
                           (l.customer_id = i.customer_id) AS native_parent_matches,
                           (owner.company_id = i.company_id) AS company_scope_matches
                    FROM service_location_source_identities i
                    JOIN customer_source_identities csi
                      ON csi.id = i.customer_source_identity_id
                     AND csi.company_id = i.company_id
                     AND csi.customer_id = i.customer_id
                    LEFT JOIN service_locations l
                      ON l.id = i.service_location_id
                    LEFT JOIN customers owner
                      ON owner.id = i.customer_id
                    WHERE i.company_id = :company_id
                      AND i.branch_id = :branch_id
                      AND i.source_system IN (:legacy_source, :source4)
                    ORDER BY i.source_system, i.source_location_id
                    """
                ),
                scope,
            )
        ).mappings()
    )
    holds = _serialize(
        (
            await session.execute(
                text(
                    """
                    SELECT entity_kind, native_id AS source_record_id,
                           hold_code AS reason_code, state,
                           package_digest AS source_digest, evidence_digest
                    FROM hcp_migration_holds
                    WHERE company_id = :company_id
                      AND branch_id = :branch_id
                      AND state = 'HELD'
                      AND entity_kind IN ('customer', 'location', 'service_location')
                    ORDER BY entity_kind, native_id
                    """
                ),
                scope,
            )
        ).mappings()
    )
    document: dict[str, Any] = {
        "contract": CONTRACT,
        "source_systems": list(SOURCES),
        "company_id": str(company_id),
        "branch_id": str(branch_id),
        "observed_at": observed_at.isoformat(),
        "mutation_authority": "none",
        "identity_method": "exact_persisted_source_identity_only",
        "customers": customers,
        "locations": locations,
        "holds": holds,
        "counts": {
            "customers": len(customers),
            "locations": len(locations),
            "holds": len(holds),
        },
        "limitations": [
            "source_acquired_population_requires_sealed_package_reconciliation",
            "absence_of_binding_does_not_prove_absence_of_native_business_record",
            "no_address_name_phone_or_other_natural_key_matching_performed",
        ],
    }
    document["digest"] = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return document
