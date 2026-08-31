from pathlib import Path

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.engineering_execution.controlled.models import (
    ControlledExecutionOfferModel,
    ControlledExecutionResultModel,
)


def test_controlled_offer_foreign_identities_are_company_bound() -> None:
    bindings = {
        (
            tuple(column.name for column in constraint.columns),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in ControlledExecutionOfferModel.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }

    assert (
        ("company_id", "command_id"),
        ("engineering_commands.company_id", "engineering_commands.id"),
    ) in bindings
    assert (
        ("company_id", "execution_id"),
        ("engineering_executions.company_id", "engineering_executions.id"),
    ) in bindings
    assert (
        ("company_id", "lease_id"),
        ("engineering_worker_leases.company_id", "engineering_worker_leases.id"),
    ) in bindings
    assert (
        ("company_id", "worker_id"),
        ("engineering_workers.company_id", "engineering_workers.id"),
    ) in bindings
    assert (
        ("company_id", "session_id"),
        (
            "engineering_worker_transport_sessions.company_id",
            "engineering_worker_transport_sessions.id",
        ),
    ) in bindings
    assert not any(local == ("command_id",) for local, _ in bindings)


def test_company_binding_migration_is_on_the_authoritative_head() -> None:
    source = Path(
        "alembic/versions/o3m2n71j8h4f_bind_controlled_offers_to_company.py"
    ).read_text()

    assert 'down_revision: str | Sequence[str] | None = "n2l1j60i7g3e"' in source
    for constraint in (
        "fk_controlled_offers_command",
        "fk_controlled_offers_lease",
        "fk_controlled_offers_worker",
        "fk_controlled_offers_session",
    ):
        assert constraint in source


def test_controlled_result_is_bound_to_the_exact_parent_offer() -> None:
    result_binding = next(
        constraint
        for constraint in ControlledExecutionResultModel.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_controlled_results_offer"
    )
    offer_binding = next(
        constraint
        for constraint in ControlledExecutionOfferModel.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_controlled_offers_result_binding"
    )
    expected_offer_columns = (
        "company_id",
        "id",
        "command_id",
        "execution_id",
        "lease_id",
        "worker_id",
        "session_id",
    )

    assert tuple(column.name for column in offer_binding.columns) == expected_offer_columns
    assert tuple(column.name for column in result_binding.columns) == (
        "company_id",
        "offer_id",
        *expected_offer_columns[2:],
    )
    assert tuple(
        element.target_fullname for element in result_binding.elements
    ) == tuple(
        f"engineering_controlled_execution_offers.{column}"
        for column in expected_offer_columns
    )


def test_result_binding_migration_advances_the_authoritative_head() -> None:
    source = Path(
        "alembic/versions/p4n3o82k9i5g_bind_controlled_results_to_offer.py"
    ).read_text()

    assert 'down_revision: str | Sequence[str] | None = "o3m2n71j8h4f"' in source
    assert "uq_controlled_offers_result_binding" in source
    assert "fk_controlled_results_offer" in source
