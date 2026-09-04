from uuid import UUID

import pytest
from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2ExecutionPlanBuilder,
)
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError


def test_preview_authority_may_supply_nonhistorical_scoped_ids() -> None:
    builder = object.__new__(HcpMigration2ExecutionPlanBuilder)

    class StopAfterScopeCheck(RuntimeError):
        pass

    class Loader:
        def load_customers(self) -> None:
            raise StopAfterScopeCheck

    builder.loader = Loader()  # type: ignore[attr-defined]

    with pytest.raises(StopAfterScopeCheck):
        builder.build(
            baseline_counts={},
            company_id=UUID("a56fc415-563b-459c-913f-2e6183109119"),
            branch_id=UUID("4d6929eb-6941-446c-8667-97892ded14c4"),
            actor_id=UUID("55868185-8c70-494e-8958-38faa9cccfdb"),
        )


def test_preview_authority_rejects_nil_scope() -> None:
    builder = object.__new__(HcpMigration2ExecutionPlanBuilder)

    with pytest.raises(SafeEvidenceError, match="sanctioned_scope_mismatch"):
        builder.build(
            baseline_counts={},
            company_id=UUID(int=0),
            branch_id=UUID("4d6929eb-6941-446c-8667-97892ded14c4"),
            actor_id=UUID("55868185-8c70-494e-8958-38faa9cccfdb"),
        )
