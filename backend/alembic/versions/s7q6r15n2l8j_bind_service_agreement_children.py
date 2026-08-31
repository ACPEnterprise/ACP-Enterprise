"""Bind Service Agreement child evidence to tenant and parent authority.

Revision ID: s7q6r15n2l8j
Revises: r6p5q04m1k7i
"""

from collections.abc import Sequence

from alembic import op

revision: str = "s7q6r15n2l8j"
down_revision: str | Sequence[str] | None = "r6p5q04m1k7i"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGREEMENT = "service_agreements"
COVERAGE = "service_agreement_coverage"
ENTITLEMENT = "service_agreement_entitlements"
EVIDENCE = "service_agreement_lifecycle_evidence"
BILLING = "service_agreement_billing_occurrences"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_service_agreements_company_branch_id",
        AGREEMENT,
        ["company_id", "branch_id", "id"],
    )
    op.create_unique_constraint(
        "uq_agreement_entitlements_evidence_binding",
        ENTITLEMENT,
        ["company_id", "branch_id", "id", "agreement_id"],
    )

    op.drop_constraint(
        "service_agreement_coverage_agreement_id_fkey", COVERAGE, type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_agreement_coverage_agreement",
        COVERAGE,
        AGREEMENT,
        ["company_id", "agreement_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "service_agreement_entitlements_agreement_id_fkey",
        ENTITLEMENT,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_agreement_entitlements_agreement",
        ENTITLEMENT,
        AGREEMENT,
        ["company_id", "branch_id", "agreement_id"],
        ["company_id", "branch_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_agreement_entitlements_appointment",
        ENTITLEMENT,
        "appointments",
        ["company_id", "branch_id", "appointment_id"],
        ["company_id", "branch_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_agreement_entitlements_job",
        ENTITLEMENT,
        "jobs",
        ["company_id", "branch_id", "job_id"],
        ["company_id", "branch_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "service_agreement_lifecycle_evidence_agreement_id_fkey",
        EVIDENCE,
        type_="foreignkey",
    )
    op.drop_constraint(
        "service_agreement_lifecycle_evidence_entitlement_id_fkey",
        EVIDENCE,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_agreement_evidence_agreement",
        EVIDENCE,
        AGREEMENT,
        ["company_id", "branch_id", "agreement_id"],
        ["company_id", "branch_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_agreement_evidence_entitlement",
        EVIDENCE,
        ENTITLEMENT,
        ["company_id", "branch_id", "entitlement_id", "agreement_id"],
        ["company_id", "branch_id", "id", "agreement_id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "service_agreement_billing_occurrences_agreement_id_fkey",
        BILLING,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_agreement_billing_agreement",
        BILLING,
        AGREEMENT,
        ["company_id", "branch_id", "agreement_id"],
        ["company_id", "branch_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_agreement_billing_invoice",
        BILLING,
        "invoices",
        ["company_id", "invoice_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        CREATE FUNCTION validate_service_agreement_location_binding()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE agreement_customer uuid;
        DECLARE location_customer uuid;
        BEGIN
          SELECT customer_id INTO agreement_customer
            FROM service_agreements
            WHERE company_id = NEW.company_id AND id = NEW.agreement_id;
          SELECT customer_id INTO location_customer
            FROM service_locations WHERE id = NEW.service_location_id;
          IF agreement_customer IS NULL OR location_customer IS NULL
             OR agreement_customer IS DISTINCT FROM location_customer THEN
            RAISE EXCEPTION 'service agreement location lineage does not match'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    for table in (COVERAGE, ENTITLEMENT):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_location_binding
            BEFORE INSERT OR UPDATE OF company_id, agreement_id, service_location_id
            ON {table}
            FOR EACH ROW EXECUTE FUNCTION validate_service_agreement_location_binding()
            """
        )


def downgrade() -> None:
    for table in (ENTITLEMENT, COVERAGE):
        op.execute(f"DROP TRIGGER trg_{table}_location_binding ON {table}")
    op.execute("DROP FUNCTION validate_service_agreement_location_binding()")

    op.drop_constraint("fk_agreement_billing_invoice", BILLING, type_="foreignkey")
    op.drop_constraint("fk_agreement_billing_agreement", BILLING, type_="foreignkey")
    op.create_foreign_key(
        "service_agreement_billing_occurrences_agreement_id_fkey",
        BILLING,
        AGREEMENT,
        ["agreement_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("fk_agreement_evidence_entitlement", EVIDENCE, type_="foreignkey")
    op.drop_constraint("fk_agreement_evidence_agreement", EVIDENCE, type_="foreignkey")
    op.create_foreign_key(
        "service_agreement_lifecycle_evidence_agreement_id_fkey",
        EVIDENCE,
        AGREEMENT,
        ["agreement_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "service_agreement_lifecycle_evidence_entitlement_id_fkey",
        EVIDENCE,
        ENTITLEMENT,
        ["entitlement_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("fk_agreement_entitlements_job", ENTITLEMENT, type_="foreignkey")
    op.drop_constraint(
        "fk_agreement_entitlements_appointment", ENTITLEMENT, type_="foreignkey"
    )
    op.drop_constraint(
        "fk_agreement_entitlements_agreement", ENTITLEMENT, type_="foreignkey"
    )
    op.create_foreign_key(
        "service_agreement_entitlements_agreement_id_fkey",
        ENTITLEMENT,
        AGREEMENT,
        ["agreement_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("fk_agreement_coverage_agreement", COVERAGE, type_="foreignkey")
    op.create_foreign_key(
        "service_agreement_coverage_agreement_id_fkey",
        COVERAGE,
        AGREEMENT,
        ["agreement_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_agreement_entitlements_evidence_binding", ENTITLEMENT, type_="unique"
    )
    op.drop_constraint(
        "uq_service_agreements_company_branch_id", AGREEMENT, type_="unique"
    )
