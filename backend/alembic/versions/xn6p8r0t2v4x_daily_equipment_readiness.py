"""Create daily field equipment readiness authority.

Revision ID: xn6p8r0t2v4x
Revises: bw8y0a2c4e6g
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "xn6p8r0t2v4x"
down_revision = "bw8y0a2c4e6g"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "equipment_readiness_catalog_items",
        sa.Column("id", UUID, primary_key=True), sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_id", UUID, nullable=False), sa.Column("code", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False), sa.Column("capability_code", sa.String(100), nullable=False),
        sa.Column("item_kind", sa.String(32), nullable=False), sa.Column("serialization_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"), sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "branch_id"], ["branches.company_id", "branches.id"], name="fk_equipment_catalog_branch", ondelete="RESTRICT"),
        sa.CheckConstraint("item_kind IN ('controlled_asset','equipment_set','non_serialized_item')", name="ck_equipment_catalog_kind"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_equipment_catalog_status"),
        sa.UniqueConstraint("company_id", "id", name="uq_equipment_catalog_company_id"), sa.UniqueConstraint("company_id", "code", name="uq_equipment_catalog_company_code"),
        sa.UniqueConstraint("company_id", "branch_id", "id", name="uq_equipment_catalog_scope_id"),
    )
    op.create_index("ix_equipment_catalog_scope", "equipment_readiness_catalog_items", ["company_id", "branch_id", "status"])
    op.create_table(
        "equipment_readiness_set_components",
        sa.Column("id", UUID, primary_key=True), sa.Column("company_id", UUID, nullable=False), sa.Column("catalog_item_id", UUID, nullable=False),
        sa.Column("component_code", sa.String(80), nullable=False), sa.Column("display_name", sa.String(160), nullable=False), sa.Column("required_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "catalog_item_id"], ["equipment_readiness_catalog_items.company_id", "equipment_readiness_catalog_items.id"], name="fk_equipment_component_catalog", ondelete="RESTRICT"),
        sa.CheckConstraint("required_quantity > 0", name="ck_equipment_component_quantity"), sa.UniqueConstraint("company_id", "catalog_item_id", "component_code", name="uq_equipment_component_code"),
    )
    op.create_table(
        "equipment_readiness_placements",
        sa.Column("id", UUID, primary_key=True), sa.Column("company_id", UUID, nullable=False), sa.Column("branch_id", UUID, nullable=False),
        sa.Column("catalog_item_id", UUID, nullable=False), sa.Column("asset_id", UUID), sa.Column("home_kind", sa.String(24), nullable=False), sa.Column("home_entity_id", UUID),
        sa.Column("current_location_kind", sa.String(24), nullable=False), sa.Column("current_location_entity_id", UUID), sa.Column("current_custodian_employee_id", UUID),
        sa.Column("custody_effective_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("readiness_state", sa.String(24), nullable=False, server_default="unknown"), sa.Column("service_state", sa.String(40), nullable=False, server_default="available"),
        sa.Column("missing_components", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "branch_id", "catalog_item_id"], ["equipment_readiness_catalog_items.company_id", "equipment_readiness_catalog_items.branch_id", "equipment_readiness_catalog_items.id"], name="fk_equipment_placement_catalog", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "asset_id"], ["operational_assets.company_id", "operational_assets.id"], name="fk_equipment_placement_asset", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id", "current_custodian_employee_id"], ["employees.company_id", "employees.id"], name="fk_equipment_placement_custodian", ondelete="RESTRICT"),
        sa.CheckConstraint("home_kind IN ('vehicle','shop','warehouse','repair_vendor','other')", name="ck_equipment_home_kind"),
        sa.CheckConstraint("current_location_kind IN ('vehicle','employee','shop','warehouse','repair_vendor','other','unknown')", name="ck_equipment_location_kind"),
        sa.CheckConstraint("readiness_state IN ('ready','unknown','incomplete','out_of_service','missing')", name="ck_equipment_placement_readiness"),
        sa.CheckConstraint("version >= 1", name="ck_equipment_placement_version"), sa.UniqueConstraint("company_id", "id", name="uq_equipment_placement_company_id"),
        sa.UniqueConstraint("company_id", "catalog_item_id", "asset_id", name="uq_equipment_placement_identity"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_equipment_placement_idempotency"),
    )
    op.create_index("ix_equipment_placement_custodian", "equipment_readiness_placements", ["company_id", "current_custodian_employee_id", "readiness_state"])
    op.create_table(
        "equipment_readiness_custody_events",
        sa.Column("id", UUID, primary_key=True), sa.Column("company_id", UUID, nullable=False), sa.Column("branch_id", UUID, nullable=False), sa.Column("placement_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False), sa.Column("from_employee_id", UUID), sa.Column("to_employee_id", UUID), sa.Column("from_location_kind", sa.String(24)),
        sa.Column("to_location_kind", sa.String(24), nullable=False), sa.Column("to_location_entity_id", UUID), sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("source_state", sa.String(24), nullable=False), sa.Column("resulting_state", sa.String(24), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.String(160), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id", "placement_id"], ["equipment_readiness_placements.company_id", "equipment_readiness_placements.id"], name="fk_equipment_custody_placement", ondelete="RESTRICT"),
        sa.CheckConstraint("event_type IN ('assigned','transferred','received','returned','repair','broken','lost','confirmation','correction')", name="ck_equipment_custody_event_type"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_equipment_custody_idempotency"),
    )
    op.create_index("ix_equipment_custody_history", "equipment_readiness_custody_events", ["company_id", "placement_id", "occurred_at"])
    op.create_table(
        "equipment_readiness_daily_confirmations",
        sa.Column("id", UUID, primary_key=True), sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False), sa.Column("branch_id", UUID, nullable=False),
        sa.Column("employee_id", UUID, sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False), sa.Column("catalog_item_id", UUID, sa.ForeignKey("equipment_readiness_catalog_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("placement_id", UUID, sa.ForeignKey("equipment_readiness_placements.id", ondelete="RESTRICT")), sa.Column("work_date", sa.Date(), nullable=False), sa.Column("state", sa.String(36), nullable=False),
        sa.Column("missing_components", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("note", sa.String(500)),
        sa.Column("supersedes_confirmation_id", UUID, sa.ForeignKey("equipment_readiness_daily_confirmations.id", ondelete="RESTRICT")), sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.CheckConstraint("state IN ('present_ready','transferred','left_at_shop','in_repair','missing_or_unknown','incomplete_set','broken_or_out_of_service','other')", name="ck_equipment_confirmation_state"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_equipment_confirmation_idempotency"),
    )
    op.create_index("ix_equipment_confirmation_day", "equipment_readiness_daily_confirmations", ["company_id", "employee_id", "work_date", "catalog_item_id"])
    op.create_table(
        "service_equipment_requirements",
        sa.Column("id", UUID, primary_key=True), sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False), sa.Column("branch_id", UUID, nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False), sa.Column("source_entity_id", UUID, nullable=False), sa.Column("capability_code", sa.String(100), nullable=False),
        sa.Column("requirement_reason", sa.String(500), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_type IN ('price_book_service','job','service_template')", name="ck_service_equipment_source_type"), sa.CheckConstraint("status IN ('active','inactive')", name="ck_service_equipment_status"),
        sa.UniqueConstraint("company_id", "source_type", "source_entity_id", "capability_code", name="uq_service_equipment_requirement"),
    )
    op.create_index("ix_service_equipment_source", "service_equipment_requirements", ["company_id", "source_type", "source_entity_id", "status"])
    op.create_table(
        "equipment_readiness_attention",
        sa.Column("id", UUID, primary_key=True), sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False), sa.Column("branch_id", UUID, nullable=False),
        sa.Column("identity_key", sa.String(200), nullable=False), sa.Column("attention_code", sa.String(80), nullable=False), sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="open"), sa.Column("employee_id", UUID), sa.Column("catalog_item_id", UUID), sa.Column("placement_id", UUID), sa.Column("job_id", UUID), sa.Column("appointment_id", UUID),
        sa.Column("title", sa.String(240), nullable=False), sa.Column("explanation", sa.String(1000), nullable=False), sa.Column("responsibility_code", sa.String(80), nullable=False, server_default="FIELD_OPERATIONS"),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)), sa.Column("resolved_by_user_id", UUID), sa.Column("resolution_note", sa.String(500)), sa.Column("evidence_digest", sa.String(64), nullable=False), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("priority IN ('critical_before_job','needs_attention','information')", name="ck_equipment_attention_priority"), sa.CheckConstraint("state IN ('open','resolved','superseded')", name="ck_equipment_attention_state"),
        sa.UniqueConstraint("company_id", "identity_key", name="uq_equipment_attention_identity"),
    )
    op.create_index("ix_equipment_attention_queue", "equipment_readiness_attention", ["company_id", "branch_id", "state", "priority"])


def downgrade() -> None:
    op.drop_index("ix_equipment_attention_queue", table_name="equipment_readiness_attention"); op.drop_table("equipment_readiness_attention")
    op.drop_index("ix_service_equipment_source", table_name="service_equipment_requirements"); op.drop_table("service_equipment_requirements")
    op.drop_index("ix_equipment_confirmation_day", table_name="equipment_readiness_daily_confirmations"); op.drop_table("equipment_readiness_daily_confirmations")
    op.drop_index("ix_equipment_custody_history", table_name="equipment_readiness_custody_events"); op.drop_table("equipment_readiness_custody_events")
    op.drop_index("ix_equipment_placement_custodian", table_name="equipment_readiness_placements"); op.drop_table("equipment_readiness_placements")
    op.drop_table("equipment_readiness_set_components")
    op.drop_index("ix_equipment_catalog_scope", table_name="equipment_readiness_catalog_items"); op.drop_table("equipment_readiness_catalog_items")
