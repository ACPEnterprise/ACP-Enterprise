from urllib.parse import parse_qs, urlparse

import pytest
from app.migration_factory.domain import ProviderKey
from app.migration_factory.normalized import NORMALIZED_CONTRACTS, NormalizedKind
from app.migration_factory.providers import CapabilityState, default_registry
from app.migration_factory.providers.quickbooks import (
    ACCOUNTING_SCOPE,
    QuickBooksAdapter,
)
from app.qbo_source.intuit import (
    ClientCredential,
    IntuitEnvironment,
    IntuitOAuthClient,
    ScopeRegistry,
    compare_scopes,
)


class Secrets:
    async def get_client_credential(self, reference: str) -> ClientCredential:
        return ClientCredential("client", "secret")


class Transport:
    pass


def test_registry_contains_all_first_wave_and_fallback_providers() -> None:
    assert set(default_registry().keys()) == {
        ProviderKey("housecall_pro"),
        ProviderKey("servicetitan"),
        ProviderKey("jobber"),
        ProviderKey("quickbooks"),
        ProviderKey("xero"),
        ProviderKey("sage"),
        ProviderKey("structured_file"),
    }


def test_normalized_contracts_cover_every_required_common_domain() -> None:
    assert len(NORMALIZED_CONTRACTS) == 29
    assert NormalizedKind.PAYROLL_YTD_STATE in NORMALIZED_CONTRACTS
    assert NormalizedKind.DISPATCH_EVENT in NORMALIZED_CONTRACTS


def test_quickbooks_capabilities_do_not_claim_unapproved_payroll() -> None:
    states = {item.domain: item.state for item in QuickBooksAdapter.capabilities}
    assert CapabilityState.REQUIRES_UPGRADE in states.values()
    assert CapabilityState.REQUIRES_APPROVAL in states.values()


def test_scope_comparison_detects_incremental_consent() -> None:
    result = compare_scopes(ACCOUNTING_SCOPE, (ACCOUNTING_SCOPE, "qb.employee.read"))
    assert result.missing == {"qb.employee.read"}
    assert result.reauthorization_required


@pytest.mark.asyncio
async def test_oauth_defaults_to_accounting_and_supports_enabled_scope_list() -> None:
    client = IntuitOAuthClient(
        environment=IntuitEnvironment.PRODUCTION,
        transport=Transport(),
        secrets=Secrets(),
        credential_reference="ref",
        scope_registry=ScopeRegistry(
            frozenset({ACCOUNTING_SCOPE, "payroll.compensation.read"})
        ),
    )
    default_url = await client.build_authorization_url(
        redirect_uri="https://example.test/callback", state="x" * 32
    )
    assert parse_qs(urlparse(default_url).query)["scope"] == [ACCOUNTING_SCOPE]
    expanded_url = await client.build_authorization_url(
        redirect_uri="https://example.test/callback",
        state="y" * 32,
        requested_scopes=(ACCOUNTING_SCOPE, "payroll.compensation.read"),
    )
    assert set(parse_qs(urlparse(expanded_url).query)["scope"][0].split()) == {
        ACCOUNTING_SCOPE,
        "payroll.compensation.read",
    }


@pytest.mark.asyncio
async def test_oauth_refuses_scope_not_enabled_by_deployment() -> None:
    client = IntuitOAuthClient(
        environment=IntuitEnvironment.PRODUCTION,
        transport=Transport(),
        secrets=Secrets(),
        credential_reference="ref",
    )
    with pytest.raises(ValueError, match="not enabled"):
        await client.build_authorization_url(
            redirect_uri="https://example.test/callback",
            state="z" * 32,
            requested_scopes=(ACCOUNTING_SCOPE, "qb.employee.read"),
        )
