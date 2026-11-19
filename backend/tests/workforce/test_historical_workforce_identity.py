from app.workforce.models import HistoricalWorkforceIdentity


def test_historical_identity_is_explicitly_non_operational() -> None:
    assert HistoricalWorkforceIdentity.__table__.c.operational_access_enabled.server_default
    assert any(
        constraint.name == "ck_historical_workforce_non_operational"
        for constraint in HistoricalWorkforceIdentity.__table__.constraints
    )


def test_historical_identity_scope_is_company_source_unique() -> None:
    unique = next(
        constraint
        for constraint in HistoricalWorkforceIdentity.__table__.constraints
        if constraint.name == "uq_historical_workforce_source_identity"
    )
    assert {column.name for column in unique.columns} == {
        "company_id",
        "source_system",
        "source_identity",
    }
