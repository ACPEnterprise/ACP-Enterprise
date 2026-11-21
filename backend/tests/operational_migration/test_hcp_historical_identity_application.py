from uuid import uuid4

import pytest
from app.operational_migration.hcp_historical_identity_application import (
    HistoricalIdentityBridgeApplication,
)
from app.operational_migration.hcp_historical_identity_bridge import (
    BridgeDisposition,
    CustomerBridgeDecision,
    HistoricalIdentityBridgePlan,
    _digest,
)
from app.operational_migration.models import HcpSource4NativeBindingEvidence
from sqlalchemy import func, select

from backend.tests.operational_migration.test_hcp_source4_native_binding import (
    _lineage_and_legacy,
)
from backend.tests.operational_migration.test_hcp_source4_native_binding import (
    binding_database as _binding_database,
)

binding_database = _binding_database


def _plan(source_id: str, native_id: str) -> HistoricalIdentityBridgePlan:
    decision = CustomerBridgeDecision(
        source_id,
        native_id,
        BridgeDisposition.CORROBORATED_EXACT,
        ("address", "phone"),
        (native_id,),
        (),
        "unique deterministic Customer successor",
    )
    payload = {
        "contract": "hcp-historical-identity-bridge/v1",
        "source_count": 1,
        "bridged": 1,
        "quarantined": 0,
        "ambiguous": 0,
        "duplicates_prevented": 0,
        "unexplained": 0,
        "decisions": (decision,),
    }
    return HistoricalIdentityBridgePlan(**payload, digest=_digest(payload))


@pytest.mark.asyncio
async def test_durable_application_is_exactly_idempotent(binding_database) -> None:
    company, branch, lineage, customer, _, _, service = await _lineage_and_legacy(
        binding_database
    )
    source_id = f"cus_{uuid4().hex}"
    application = HistoricalIdentityBridgeApplication(
        company_id=company.id,
        branch_id=branch.id,
        master_run_id=lineage.binding.master_run_id,
        customer_run_id=service.customer_run_id,
        package_digest=service.package_digest,
    )
    plan = _plan(source_id, str(customer.id))
    async with binding_database() as session, session.begin():
        first = await application.apply(session, plan)
    async with binding_database() as session, session.begin():
        second = await application.apply(session, plan)

    assert first.customers.newly_bound == 1
    assert first.customers.unexplained == 0
    assert second.customers.already_bound == 1
    assert second.customers.newly_bound == 0
    async with binding_database() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HcpSource4NativeBindingEvidence)
                .where(HcpSource4NativeBindingEvidence.source4_source_id == source_id)
            )
            == 1
        )
