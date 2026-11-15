"""Reconcile Clean-Beta historical workforce provenance without granting access."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from uuid import UUID

COMPANY_ID = UUID("3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd")
MAIN_BRANCH_ID = UUID("887f413a-70dc-4ab1-98aa-8e84f4e7efd0")


def _historical_rows(native: dict[str, UUID]) -> tuple[dict[str, object], ...]:
    return (
        {
            "source_system": "HCP",
            "source_identity": "pro_622e39dd3a544e4cb4fb8782ac767287",
            "display_name": "Michael Fouse",
            "source_status": "ACTIVE",
            "lifecycle_state": "VERIFIED",
            "native_employee_id": native["Michael Fouse"],
            "provenance_reference": "hcp-workforce-source-authority/v1; sealed-November-crosswalk",
            "evidence_digest": "e023c0bb63597966ceea4bff89fd9fb9424f2cee7bdd5cd4113375bc474819f0",
            "unresolved_reason": None,
            "evidence_metadata": {"owner_disposition": "SAFE_CREATE"},
        },
        {
            "source_system": "HCP",
            "source_identity": "pro_10853bfb63874a0b9d17cab14d1da20b",
            "display_name": "Alex Donahue",
            "source_status": "ACTIVE",
            "lifecycle_state": "VERIFIED",
            "native_employee_id": native["Alex Donahue"],
            "provenance_reference": "hcp-workforce-source-authority/v1; sealed-November-crosswalk",
            "evidence_digest": "b39b926208ae0769850ffb7580fa4826563462c53f6a5b7a42b417dd3c8ed51f",
            "unresolved_reason": None,
            "evidence_metadata": {"owner_disposition": "OWNER_IDENTITY_DECISION_REQUIRED"},
        },
        {
            "source_system": "HCP",
            "source_identity": "pro_6b2b2b7177a54187a690cb198a6dbda5",
            "display_name": "Jason Calci",
            "source_status": "ACTIVE",
            "lifecycle_state": "VERIFIED",
            "native_employee_id": native["Jason Calci"],
            "provenance_reference": "hcp-workforce-source-authority/v1; sealed-November-crosswalk",
            "evidence_digest": "482fab84509dd7d8eeaf72f42d17f856a47c9a7b9a932d98263f4e2d0d217339",
            "unresolved_reason": None,
            "evidence_metadata": {"owner_disposition": "SAFE_CREATE"},
        },
        {
            "source_system": "HCP",
            "source_identity": "pro_23be6c33b14a4127bd737529180a56a1",
            "display_name": "Melvin Santiago",
            "source_status": "ACTIVE",
            "lifecycle_state": "PARTIAL",
            "native_employee_id": native["Melvin Santiago"],
            "provenance_reference": "hcp-workforce-source-authority/v1",
            "evidence_digest": "4b242926ddc2e6c01a2c5c963b2f1405eb3dc6f2c2a0b40cff077ee0331a9015",
            "unresolved_reason": "Known source identity has no retained November source body or native crosswalk.",
            "evidence_metadata": {"source_body_available": False},
        },
        {
            "source_system": "HCP",
            "source_identity": "pro_0ff2024a6baa4475a883f76d6cbcc58b",
            "display_name": "Dakota Wilcox",
            "source_status": "ACTIVE_AT_SOURCE",
            "lifecycle_state": "QUARANTINED",
            "native_employee_id": native["Dakota Wilcox"],
            "provenance_reference": "hcp-workforce-source-authority/v1; qualified-November-gate-packet",
            "evidence_digest": "7ecff113548b1d1a14d6293c49af276c198d1edfbbf5ba611e0adeb99209fb1b",
            "unresolved_reason": "Same provider identity is held in the sealed November packet; source classification and owner identity mapping conflict.",
            "evidence_metadata": {"native_dispatch_history_preserved": True},
        },
        {
            "source_system": "HCP",
            "source_identity": "pro_2edf25dd14494b1885a50fa134b44fd8",
            "display_name": "Dareis Montgomery",
            "source_status": "ACTIVE_AT_SOURCE",
            "lifecycle_state": "UNRESOLVED",
            "native_employee_id": None,
            "provenance_reference": "hcp-workforce-source-authority/v1",
            "evidence_digest": "c9f09f51f4bce541a03cb04d208f0a892d50337c36c4fda86e3dc3cbc48a7335",
            "unresolved_reason": "Known repository source identity is absent from the retained November bundle and has no native historical identity.",
            "evidence_metadata": {"owner_roster_state": "historical_inactive"},
        },
        {
            "source_system": "HCP",
            "source_identity": "pro_4f1d81e3d31b4ffa9072dd6a32906586",
            "display_name": "Adam Mari",
            "source_status": "TERMINATED",
            "lifecycle_state": "PARTIAL",
            "native_employee_id": None,
            "provenance_reference": "hcp-workforce-source-authority/v1",
            "evidence_digest": "cf4f845ffca5cfd07218689c38f3621210695e85c6ef6d1ffd06ff7e5ebf2880",
            "unresolved_reason": "Terminated source identity is preserved in authority metadata but has no native historical identity or retained current-bundle body.",
            "evidence_metadata": {"status_effective_at": "2026-09-18T00:00:00-04:00"},
        },
        {
            "source_system": "HCP",
            "source_identity": "pro_8646a77e7dc649ba96259ce8ef68acb2",
            "display_name": "Unidentified HCP employee",
            "source_status": "UNKNOWN",
            "lifecycle_state": "QUARANTINED",
            "native_employee_id": None,
            "provenance_reference": "qualified-November-gate-packet; hcp_migration_holds",
            "evidence_digest": "3a1ae01003503166e5a0b0f99be2add841245b8d89ad1557cf088cd3e8589d95",
            "unresolved_reason": "Source identity is held but the retained evidence does not prove the person-level name.",
            "evidence_metadata": {"operational_effects_enabled": False, "financial_truth_accepted": False},
        },
        {
            "source_system": "ACP_NATIVE",
            "source_identity": "employee:afa0fcc5-683d-4723-9e1b-f65ba574a4c8",
            "display_name": "Alex Donahue (stale inactive duplicate)",
            "source_status": "INACTIVE",
            "lifecycle_state": "QUARANTINED",
            "native_employee_id": native["Alex Donahue (stale)"],
            "provenance_reference": "clean-Beta employees table; duplicate identity audit",
            "evidence_digest": None,
            "unresolved_reason": "Same-name native row is not merged because deterministic source equivalence is not proven.",
            "evidence_metadata": {"excluded_from_active_selectors": True},
        },
        {
            "source_system": "OWNER_ROSTER",
            "source_identity": "name:kamen-wilmington",
            "display_name": "Kamen Wilmington",
            "source_status": "HISTORICAL_INACTIVE",
            "lifecycle_state": "UNRESOLVED",
            "native_employee_id": None,
            "provenance_reference": "owner canonical workforce roster",
            "evidence_digest": None,
            "unresolved_reason": "No exact HCP or QBO source identity is retained; name-only identity is not source proof.",
            "evidence_metadata": {"source_identity_status": "not_found"},
        },
    )


async def reconcile() -> dict[str, int]:
    from sqlalchemy import select

    from app.database.session import AsyncSessionFactory
    from app.platform.company.membership_models import Membership
    from app.platform.employees.models import Employee
    from app.platform.permissions.models import MembershipRole
    from app.platform.users.models import User, UserCredential
    from app.workforce.models import HistoricalWorkforceIdentity

    async with AsyncSessionFactory() as session:
        async with session.begin():
            employee_rows = (
                await session.scalars(
                    select(Employee).where(Employee.company_id == COMPANY_ID)
                )
            ).all()
            active_alex = [
                employee for employee in employee_rows
                if employee.display_name == "Alex Donahue" and employee.status == "active"
            ]
            stale_alex = [
                employee for employee in employee_rows
                if employee.display_name == "Alex Donahue" and employee.status == "inactive"
            ]
            if len(active_alex) != 1 or len(stale_alex) != 1:
                raise RuntimeError("expected exactly one active and one inactive Alex row")
            employees = {
                employee.display_name: employee
                for employee in employee_rows
                if employee.display_name != "Alex Donahue"
            }
            employees["Alex Donahue"] = active_alex[0]
            employees["Alex Donahue (stale)"] = stale_alex[0]
            required = {
                "Michael Fouse",
                "Alex Donahue",
                "Melvin Santiago",
                "Dakota Wilcox",
                "Jason Calci",
                "Alex Donahue (stale)",
            }
            native = {
                "Michael Fouse": employees["Michael Fouse"].id,
                "Alex Donahue": employees["Alex Donahue"].id,
                "Melvin Santiago": employees["Melvin Santiago"].id,
                "Dakota Wilcox": employees["Dakota Wilcox"].id,
                "Jason Calci": employees["Jason Calci"].id,
                "Alex Donahue (stale)": employees["Alex Donahue (stale)"].id,
            }
            if not required.issubset(set(employees) | {"Alex Donahue (stale)"}):
                raise RuntimeError("canonical native employee set is incomplete")

            # Correct display/job metadata without changing access profiles.
            employees["Lianne Hernandez"].job_title = "Office Manager"
            employees["Malcolm Calci"].job_title = "Helper"

            rows = _historical_rows(native)
            created = 0
            updated = 0
            for values in rows:
                row = await session.scalar(
                    select(HistoricalWorkforceIdentity).where(
                        HistoricalWorkforceIdentity.company_id == COMPANY_ID,
                        HistoricalWorkforceIdentity.source_system == values["source_system"],
                        HistoricalWorkforceIdentity.source_identity == values["source_identity"],
                    )
                )
                if row is None:
                    row = HistoricalWorkforceIdentity(
                        company_id=COMPANY_ID,
                        operational_access_enabled=False,
                        **values,
                    )
                    session.add(row)
                    created += 1
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
                    row.operational_access_enabled = False
                    updated += 1

            # The disposable onboarding fixture is identified exactly and is
            # deactivated, never deleted, so its acceptance receipt remains.
            disposable = (
                await session.scalars(
                    select(Employee).where(
                        Employee.company_id == COMPANY_ID,
                        Employee.employee_number == "EMP-0005",
                        Employee.display_name.like("Disposable Beta%"),
                    )
                )
            ).all()
            if len(disposable) != 1:
                raise RuntimeError("expected exactly one disposable Beta employee")
            fixture = disposable[0]
            fixture.status = "inactive"
            fixture.archived_at = datetime.now(timezone.utc)
            membership = await session.scalar(
                select(Membership).where(Membership.id == fixture.membership_id)
            )
            if membership is not None:
                membership.status = "revoked"
                membership.revoked_at = datetime.now(timezone.utc)
            user = await session.scalar(
                select(User).where(User.id == membership.user_id)
            ) if membership is not None else None
            if user is not None:
                user.status = "locked"
                user.disabled_at = datetime.now(timezone.utc)
                user.authorization_version += 1
                credential = await session.scalar(
                    select(UserCredential).where(UserCredential.user_id == user.id)
                )
                if credential is not None:
                    credential.credential_version += 1
            if membership is not None:
                role_rows = (
                    await session.scalars(
                        select(MembershipRole).where(
                            MembershipRole.membership_id == membership.id,
                            MembershipRole.revoked_at.is_(None),
                        )
                    )
                ).all()
                for role in role_rows:
                    role.revoked_at = datetime.now(timezone.utc)
                    role.revocation_reason = "disposable_beta_acceptance_fixture_retired"

        return {"historical_created": created, "historical_updated": updated, "disposable_retired": 1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", default=str(COMPANY_ID))
    args = parser.parse_args()
    if UUID(args.company_id) != COMPANY_ID:
        raise SystemExit("only the approved Clean-Beta company is supported")
    print(asyncio.run(reconcile()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
