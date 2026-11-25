from datetime import datetime, timezone
from uuid import UUID

import pytest
from app.communications.historical_readback import (
    HistoricalCommunicationDisposition,
    SourceHistoricalCommunication,
    read_historical_communications,
    reconcile_historical_communications,
)
from app.communications.types import CommunicationChannel

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
OTHER_COMPANY = UUID("10000000-0000-0000-0000-000000000002")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
OTHER_BRANCH = UUID("20000000-0000-0000-0000-000000000002")
CUSTOMER = UUID("30000000-0000-0000-0000-000000000001")
OTHER_CUSTOMER = UUID("30000000-0000-0000-0000-000000000002")


def source(
    source_id: str,
    *,
    company_id: UUID = COMPANY,
    branch_id: UUID = BRANCH,
    customer_id: UUID = CUSTOMER,
    digest: str = "a" * 64,
    hour: int = 1,
) -> SourceHistoricalCommunication:
    return SourceHistoricalCommunication(
        "housecall_pro",
        source_id,
        company_id,
        branch_id,
        customer_id,
        datetime(2026, 1, 1, hour, tzinfo=timezone.utc),
        CommunicationChannel.SMS,
        "outbound",
        f"Historical message {source_id}",
        digest,
    )


def test_reconciliation_is_idempotent_and_readback_is_newest_first() -> None:
    first = source("m1", hour=1)
    second = source("m2", hour=2, digest="b" * 64)
    result = reconcile_historical_communications((second, first, first))
    assert result == reconcile_historical_communications((first, second))
    readback = read_historical_communications(
        result, company_id=COMPANY, accessible_branch_ids=frozenset({BRANCH})
    )
    assert [item.source_key for item in readback] == [
        "housecall_pro:m2",
        "housecall_pro:m1",
    ]


def test_conflicting_source_identity_is_held_without_display_projection() -> None:
    result = reconcile_historical_communications(
        (source("m1"), source("m1", digest="b" * 64))
    )
    item = result.records[0]
    assert item.disposition is HistoricalCommunicationDisposition.HELD_CONFLICT
    assert item.display is None
    assert not read_historical_communications(
        result, company_id=COMPANY, accessible_branch_ids=frozenset({BRANCH})
    )


def test_tenant_branch_and_customer_scope_are_enforced() -> None:
    result = reconcile_historical_communications(
        (
            source("visible"),
            source("other-customer", customer_id=OTHER_CUSTOMER, digest="b" * 64),
            source("other-branch", branch_id=OTHER_BRANCH, digest="c" * 64),
            source("other-company", company_id=OTHER_COMPANY, digest="d" * 64),
        )
    )
    readback = read_historical_communications(
        result,
        company_id=COMPANY,
        accessible_branch_ids=frozenset({BRANCH}),
        customer_id=CUSTOMER,
    )
    assert [item.source_key for item in readback] == ["housecall_pro:visible"]
    with pytest.raises(PermissionError, match="branch access denied"):
        read_historical_communications(
            result,
            company_id=COMPANY,
            accessible_branch_ids=frozenset({BRANCH}),
            branch_id=OTHER_BRANCH,
        )


def test_contract_has_no_provider_write_or_delivery_operation() -> None:
    import app.communications.historical_readback as contract

    public_names = {name for name in vars(contract) if not name.startswith("_")}
    assert not public_names & {"send", "deliver", "write_provider", "initiate_oauth"}
