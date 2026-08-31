from pathlib import Path

from sqlalchemy import ForeignKeyConstraint

from app.engineering_execution.controlled.models import ControlledExecutionOfferModel


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
