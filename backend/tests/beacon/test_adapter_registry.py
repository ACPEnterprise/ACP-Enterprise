from app.beacon.adapter_registry import (
    CROSS_DOMAIN_ADAPTER_REGISTRY,
    AdapterStatus,
)


def test_cross_domain_registry_is_explicit_and_non_mutating() -> None:
    by_family = {item.family: item for item in CROSS_DOMAIN_ADAPTER_REGISTRY}

    assert len(by_family) == 14
    assert {
        "migration_source_completeness",
        "workforce",
        "timekeeping",
        "payroll_readiness",
        "accounting_controls",
        "economics_luminary",
        "price_book",
        "estimates",
        "inventory_purchasing",
        "capacity",
        "marketing_readiness",
    }.issubset(by_family)
    assert all(item.clearing_condition for item in by_family.values())
    assert all(item.source_authority for item in by_family.values())
    assert sum(item.status is AdapterStatus.ACTIVE for item in by_family.values()) == 4
    assert by_family["marketing_readiness"].status is AdapterStatus.ACTIVE
    assert (
        by_family["migration_source_completeness"].status is AdapterStatus.ADAPTER_GATED
    )
    assert by_family["price_book"].status is AdapterStatus.POLICY_GATED
