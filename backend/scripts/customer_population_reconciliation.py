"""Run exact-provider Customer population reconciliation inside ACP runtime.

This is an authenticated Enterprise operator command.  It is intentionally not
an HTTP route and accepts no Customer names or other fuzzy identity inputs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Standalone commands must register the complete SQLAlchemy model graph before
# authorization resolution or migration-owned persistence is used.
from app import main as application_model_registry  # noqa: F401
from app.customer_migration.population_reconciliation import (
    HCP_SOURCE_SYSTEM,
    CustomerPopulationReconciliationError,
    CustomerPopulationReconciliationService,
    ExactCustomerAdmissionCommand,
    customer_population_reconciliation_service,
)
from app.database.session import AsyncSessionFactory, engine
from app.platform.auth.errors import AuthenticationError
from app.platform.auth.services import access_token_service, authentication_service
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationError,
    authorization_service,
)


async def authorized_context(
    *, token: str, company_id: UUID, branch_id: UUID
) -> AuthorizationContext:
    if not token:
        raise AuthenticationError("Authentication required.")
    claims = access_token_service.decode(token)
    async with AsyncSessionFactory() as session:
        authenticated = await authentication_service.validate_access_context(
            session, claims
        )
        context = await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=company_id,
            branch_id=branch_id,
        )
        await session.rollback()
        return context


async def execute_action(
    args: argparse.Namespace,
    *,
    context: AuthorizationContext,
    factory: async_sessionmaker[AsyncSession] = AsyncSessionFactory,
    service: CustomerPopulationReconciliationService = (
        customer_population_reconciliation_service
    ),
) -> dict[str, Any]:
    if args.action == "refresh":
        report = await service.refresh_population(
            factory,
            context=context,
            source_system=args.source_system,
        )
        return {
            "classification": "CUSTOMER_POPULATION_RECONCILED",
            "source_system": report.source_system,
            "counts": {
                "total": report.counts.total,
                "bound": report.counts.bound,
                "held": report.counts.held,
                "ambiguous": report.counts.ambiguous,
                "unexplained": report.counts.unexplained,
            },
            "evidence_digest": report.evidence_digest,
        }
    if args.action == "hold":
        disposition = await service.hold_exact(
            factory,
            context=context,
            source_system=args.source_system,
            source_customer_id=args.provider_customer_id,
            reason_code=args.reason_code,
        )
        return {
            "classification": "CUSTOMER_PROVIDER_ID_HELD",
            "source_system": disposition.source_system,
            "provider_customer_id": disposition.source_customer_id,
            "disposition_id": str(disposition.id),
            "version": disposition.version,
            "evidence_digest": disposition.evidence_digest,
        }
    if args.action == "admit-clean-majority":
        result = await service.admit_clean_majority(
            factory,
            context=context,
            source_system=args.source_system,
            limit=args.limit,
        )
        return {
            "classification": "CUSTOMER_CLEAN_MAJORITY_ADMISSION_COMPLETE",
            "source_system": result.source_system,
            "selected": result.selected,
            "admitted": result.admitted,
            "replayed": result.replayed,
            "quarantined": result.quarantined,
            "remaining_unexplained": result.remaining_unexplained,
            "before_digest": result.before_digest,
            "after_digest": result.after_digest,
        }
    if args.action == "admit":
        result = await service.admit_exact(
            factory,
            context=context,
            command=ExactCustomerAdmissionCommand(
                source_system=args.source_system,
                source_customer_id=args.provider_customer_id,
                source_artifact_id=args.source_artifact_id,
                expected_source_sha256=args.expected_source_sha256,
                expected_source_row_sha256=args.expected_source_row_sha256,
                expected_customers=args.expected_customers,
                expected_contacts=args.expected_contacts,
                expected_service_locations=args.expected_service_locations,
                expected_billing_addresses=args.expected_billing_addresses,
                idempotency_key=args.idempotency_key,
                reason_code=args.reason_code,
            ),
        )
        return {
            "classification": "CUSTOMER_PROVIDER_ID_ADMITTED",
            "customer_id": str(result.customer_id),
            "customer_source_identity_id": str(result.customer_source_identity_id),
            "disposition_id": str(result.disposition_id),
            "counts": {
                "customers": result.customers,
                "contacts": result.contacts,
                "service_locations": result.service_locations,
                "billing_addresses": result.billing_addresses,
            },
            "replayed": result.replayed,
        }
    raise ValueError("unsupported Customer population action")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=("Authenticated exact-provider Customer population reconciliation")
    )
    result.add_argument("--company-id", type=UUID, required=True)
    result.add_argument("--branch-id", type=UUID, required=True)
    actions = result.add_subparsers(dest="action", required=True)

    refresh = actions.add_parser("refresh")
    refresh.add_argument("--source-system", default=HCP_SOURCE_SYSTEM)

    hold = actions.add_parser("hold")
    hold.add_argument("--source-system", default=HCP_SOURCE_SYSTEM)
    hold.add_argument("--provider-customer-id", required=True)
    hold.add_argument("--reason-code", required=True)

    clean_majority = actions.add_parser("admit-clean-majority")
    clean_majority.add_argument("--source-system", default=HCP_SOURCE_SYSTEM)
    clean_majority.add_argument("--limit", type=int, default=5000)

    admit = actions.add_parser("admit")
    admit.add_argument("--source-system", default=HCP_SOURCE_SYSTEM)
    admit.add_argument("--provider-customer-id", required=True)
    admit.add_argument("--source-artifact-id", type=UUID, required=True)
    admit.add_argument("--expected-source-sha256", required=True)
    admit.add_argument("--expected-source-row-sha256", required=True)
    admit.add_argument("--expected-customers", type=int, required=True)
    admit.add_argument("--expected-contacts", type=int, required=True)
    admit.add_argument("--expected-service-locations", type=int, required=True)
    admit.add_argument("--expected-billing-addresses", type=int, required=True)
    admit.add_argument("--idempotency-key", required=True)
    admit.add_argument("--reason-code", required=True)
    return result


async def run(args: argparse.Namespace) -> dict[str, Any]:
    context = await authorized_context(
        token=sys.stdin.read().strip(),
        company_id=args.company_id,
        branch_id=args.branch_id,
    )
    try:
        return await execute_action(args, context=context)
    finally:
        await engine.dispose()


def main() -> None:
    try:
        print(json.dumps(asyncio.run(run(parser().parse_args())), sort_keys=True))
    except (
        AuthenticationError,
        AuthorizationError,
        CustomerPopulationReconciliationError,
        ValueError,
    ) as error:
        print(json.dumps({"classification": "BLOCKED", "reason": str(error)}))
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
