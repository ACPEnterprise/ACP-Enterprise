"""Bind immutable Economics result lineage to Branch authority.

Revision ID: n2l1j60i7g3e
Revises: m1k0i59h6f2d
"""

from collections.abc import Sequence

from alembic import op

revision: str = "n2l1j60i7g3e"
down_revision: str | Sequence[str] | None = "m1k0i59h6f2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _install_validator(*, include_branch: bool) -> None:
    branch_comparison = (
        "predecessor.branch_id, " if include_branch else ""
    )
    successor_branch_comparison = (
        "successor.branch_id, " if include_branch else ""
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION acp_validate_economics_result_supersession()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE predecessor economics_profitability_results%ROWTYPE;
        DECLARE successor economics_profitability_results%ROWTYPE;
        BEGIN
          SELECT * INTO STRICT predecessor FROM economics_profitability_results
            WHERE company_id = NEW.company_id AND id = NEW.predecessor_result_id;
          SELECT * INTO STRICT successor FROM economics_profitability_results
            WHERE company_id = NEW.company_id AND id = NEW.successor_result_id;
          IF ({branch_comparison}predecessor.subject_id, predecessor.subject_kind,
              predecessor.scope, predecessor.basis, predecessor.period_start,
              predecessor.period_end, predecessor.currency)
             IS DISTINCT FROM
             ({successor_branch_comparison}successor.subject_id,
              successor.subject_kind, successor.scope, successor.basis,
              successor.period_start, successor.period_end, successor.currency) THEN
            RAISE EXCEPTION 'economics successor belongs to a different lineage'
              USING ERRCODE = '23514';
          END IF;
          IF (NEW.subject_id, NEW.subject_kind, NEW.scope, NEW.basis,
              NEW.period_start, NEW.period_end, NEW.currency,
              NEW.predecessor_digest, NEW.successor_digest,
              NEW.predecessor_package_digest, NEW.successor_package_digest,
              NEW.predecessor_computation_digest, NEW.successor_computation_digest)
             IS DISTINCT FROM
             (predecessor.subject_id, predecessor.subject_kind, predecessor.scope,
              predecessor.basis, predecessor.period_start, predecessor.period_end,
              predecessor.currency, predecessor.result_digest, successor.result_digest,
              predecessor.package_digest, successor.package_digest,
              predecessor.computation_digest, successor.computation_digest) THEN
            RAISE EXCEPTION 'economics supersession evidence contradicts results'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )


def upgrade() -> None:
    _install_validator(include_branch=True)


def downgrade() -> None:
    _install_validator(include_branch=False)
