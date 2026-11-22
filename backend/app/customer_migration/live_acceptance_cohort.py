"""Transaction-read-only verification of a sealed Customer acceptance cohort."""

from __future__ import annotations

import hashlib
import stat
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.acceptance_cohort import (
    AcceptanceCohortIdentity,
    CustomerAcceptanceCohort,
)
from app.customer_migration.models import CustomerSourceIdentity
from app.customers.models import Customer
from app.events.models import BusinessEvent
from app.platform.branch.models import Branch
from app.platform.company.models import Company

LIVE_VERIFICATION_CONTRACT: Final = "customer-acceptance-cohort-live-verification/v1"
READ_ONLY_TRANSACTION: Final = "SET TRANSACTION READ ONLY"


@dataclass(frozen=True)
class _Binding:
    identity: CustomerSourceIdentity
    customer: Customer | None


def load_private_acceptance_cohort(
    path: Path,
    *,
    expected_source_sha256: str,
    expected_migration_release_sha: str,
) -> CustomerAcceptanceCohort:
    """Load a mode-0600 regular artifact and enforce its external bindings."""
    details = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(details.st_mode):
        raise ValueError("acceptance cohort artifact must be a regular file")
    if stat.S_IMODE(details.st_mode) != 0o600:
        raise ValueError("acceptance cohort artifact must have mode 0600")
    artifact = CustomerAcceptanceCohort.model_validate_json(path.read_bytes())
    if artifact.source_sha256 != expected_source_sha256:
        raise ValueError("acceptance cohort source binding mismatch")
    if artifact.migration_release_sha != expected_migration_release_sha:
        raise ValueError("acceptance cohort release binding mismatch")
    return artifact


def _opaque_uuid(value: UUID) -> dict[str, str]:
    rendered = str(value)
    return {
        "id": rendered,
        "id_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
    }


def _member_result(
    member: AcceptanceCohortIdentity,
    *,
    bindings: tuple[_Binding, ...],
    company_id: UUID,
    branch_id: UUID,
    native_change_source_ids: set[str],
) -> dict[str, object]:
    tenant_bindings = tuple(
        binding for binding in bindings if binding.identity.company_id == company_id
    )
    result: dict[str, object] = {
        "source_identity_sha256": member.source_identity_sha256,
        "source_row_sha256": member.source_row_sha256,
        "native_customer": None,
        "native_change_hold": False,
    }
    if not tenant_bindings:
        result["outcome"] = "cross_tenant_identity" if bindings else "missing_identity"
        return result
    if len(tenant_bindings) != 1:
        result["outcome"] = "duplicate_identity"
        return result

    binding = tenant_bindings[0]
    if binding.identity.branch_id != branch_id:
        result["outcome"] = "branch_authority_mismatch"
        return result
    if binding.customer is None:
        result["outcome"] = "missing_native_customer"
        return result
    if binding.customer.company_id != company_id:
        result["outcome"] = "cross_tenant_native_customer"
        return result

    customer_id = binding.customer.id
    result["outcome"] = "verified"
    result["native_customer"] = _opaque_uuid(customer_id)
    result["native_change_hold"] = member.source_identity in native_change_source_ids
    return result


def _member_results(
    members: tuple[AcceptanceCohortIdentity, ...],
    *,
    bindings_by_source: dict[str, tuple[_Binding, ...]],
    company_id: UUID,
    branch_id: UUID,
    native_change_source_ids: set[str],
) -> list[dict[str, object]]:
    return [
        {
            "ordinal": ordinal,
            **_member_result(
                member,
                bindings=bindings_by_source.get(member.source_identity, ()),
                company_id=company_id,
                branch_id=branch_id,
                native_change_source_ids=native_change_source_ids,
            ),
        }
        for ordinal, member in enumerate(members, start=1)
    ]


def _mark_duplicate_native_customers(
    *result_sets: list[dict[str, object]],
) -> None:
    verified_customers: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for results in result_sets:
        for result in results:
            native = result["native_customer"]
            if result["outcome"] == "verified" and isinstance(native, dict):
                verified_customers[str(native["id"])].append(result)
    for duplicates in verified_customers.values():
        if len(duplicates) > 1:
            for result in duplicates:
                result["outcome"] = "duplicate_native_customer"


def _section(results: list[dict[str, object]]) -> dict[str, object]:
    outcomes = Counter(str(result["outcome"]) for result in results)
    hold_count = sum(bool(result["native_change_hold"]) for result in results)
    return {
        "requested": len(results),
        "verified": outcomes["verified"],
        "native_change_holds": hold_count,
        "outcomes": dict(sorted(outcomes.items())),
        "members": results,
    }


async def verify_live_acceptance_cohort(
    session: AsyncSession,
    *,
    artifact: CustomerAcceptanceCohort,
    company_id: UUID,
    branch_id: UUID,
) -> dict[str, object]:
    """Verify exact live bindings; the first statement makes the transaction read-only."""
    await session.execute(text(READ_ONLY_TRANSACTION))
    try:
        company = await session.get(Company, company_id)
        branch = await session.get(Branch, branch_id)
        if (
            company is None
            or company.status != "active"
            or company.archived_at is not None
        ):
            raise ValueError("Customer cohort Company authority is unavailable")
        if (
            branch is None
            or branch.company_id != company_id
            or branch.status != "active"
            or branch.archived_at is not None
        ):
            raise ValueError("Customer cohort Branch authority is unavailable")

        members = artifact.selected + artifact.mandatory_anchors
        source_ids = tuple(member.source_identity for member in members)
        rows = (
            await session.execute(
                select(CustomerSourceIdentity, Customer)
                .outerjoin(Customer, Customer.id == CustomerSourceIdentity.customer_id)
                .where(
                    CustomerSourceIdentity.source_system == artifact.source_system,
                    CustomerSourceIdentity.source_customer_id.in_(source_ids),
                )
            )
        ).all()
        bindings_by_source: defaultdict[str, list[_Binding]] = defaultdict(list)
        for identity, customer in rows:
            bindings_by_source[identity.source_customer_id].append(
                _Binding(identity=identity, customer=customer)
            )

        in_scope_bindings = tuple(
            binding
            for bindings in bindings_by_source.values()
            for binding in bindings
            if binding.identity.company_id == company_id
            and binding.identity.branch_id == branch_id
            and binding.customer is not None
            and binding.customer.company_id == company_id
        )
        native_change_source_ids: set[str] = set()
        if in_scope_bindings:
            customer_ids = {
                binding.identity.customer_id for binding in in_scope_bindings
            }
            events = (
                await session.scalars(
                    select(BusinessEvent).where(
                        BusinessEvent.company_id == company_id,
                        BusinessEvent.entity_type == "customer",
                        BusinessEvent.event_type == "customer.updated",
                        BusinessEvent.entity_id.in_(customer_ids),
                    )
                )
            ).all()
            events_by_customer: defaultdict[UUID, list[BusinessEvent]] = defaultdict(
                list
            )
            for event in events:
                if event.entity_id is not None:
                    events_by_customer[event.entity_id].append(event)
            native_change_source_ids = {
                binding.identity.source_customer_id
                for binding in in_scope_bindings
                if any(
                    event.occurred_at > binding.identity.created_at
                    for event in events_by_customer[binding.identity.customer_id]
                )
            }

        immutable_bindings = {
            source_id: tuple(bindings)
            for source_id, bindings in bindings_by_source.items()
        }
        selected_results = _member_results(
            artifact.selected,
            bindings_by_source=immutable_bindings,
            company_id=company_id,
            branch_id=branch_id,
            native_change_source_ids=native_change_source_ids,
        )
        anchor_results = _member_results(
            artifact.mandatory_anchors,
            bindings_by_source=immutable_bindings,
            company_id=company_id,
            branch_id=branch_id,
            native_change_source_ids=native_change_source_ids,
        )
        _mark_duplicate_native_customers(selected_results, anchor_results)
        selected = _section(selected_results)
        anchors = _section(anchor_results)
        defect_count = (
            cast(int, selected["requested"])
            + cast(int, anchors["requested"])
            - cast(int, selected["verified"])
            - cast(int, anchors["verified"])
        )
        native_change_hold_count = cast(int, selected["native_change_holds"]) + cast(
            int, anchors["native_change_holds"]
        )
        return {
            "contract": LIVE_VERIFICATION_CONTRACT,
            "result": "PASS" if defect_count == 0 else "FAIL",
            "database_transaction": "READ ONLY",
            "cohort_binding": {
                "artifact_sha256": artifact.artifact_sha256,
                "source_sha256": artifact.source_sha256,
                "migration_release_sha": artifact.migration_release_sha,
                "source_system": artifact.source_system,
            },
            "authority": {
                "company": _opaque_uuid(company_id),
                "branch": _opaque_uuid(branch_id),
            },
            "selected": selected,
            "mandatory_anchors": anchors,
            "reported_exceptions": {
                "native_change_holds": native_change_hold_count,
            },
            "safe_counts": {
                "requested": len(members),
                "verified": len(members) - defect_count,
                "identity_defects": defect_count,
                "native_change_holds": native_change_hold_count,
            },
        }
    finally:
        await session.rollback()
