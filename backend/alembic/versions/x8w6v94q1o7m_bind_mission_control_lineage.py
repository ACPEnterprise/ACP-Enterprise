"""Bind Mission Control roadmap and external-adoption lineage.

Revision ID: x8w6v94q1o7m
Revises: w7v5u83p0n6l
"""

from collections.abc import Sequence

from alembic import op

revision: str = "x8w6v94q1o7m"
down_revision: str | Sequence[str] | None = "w7v5u83p0n6l"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_engineering_roadmaps_company_id",
        "engineering_roadmaps",
        ["company_id", "id"],
    )
    op.create_unique_constraint(
        "uq_engineering_milestones_roadmap_scope",
        "engineering_milestones",
        ["company_id", "roadmap_id", "id"],
    )
    op.create_unique_constraint(
        "uq_engineering_milestones_company_id",
        "engineering_milestones",
        ["company_id", "id"],
    )
    op.create_unique_constraint(
        "uq_external_adoptions_company_id",
        "engineering_external_milestone_adoptions",
        ["company_id", "id"],
    )

    op.drop_constraint(
        "engineering_milestones_roadmap_id_fkey",
        "engineering_milestones",
        type_="foreignkey",
    )
    op.drop_constraint(
        "engineering_milestones_command_id_fkey",
        "engineering_milestones",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_engineering_milestones_roadmap_company",
        "engineering_milestones",
        "engineering_roadmaps",
        ["company_id", "roadmap_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_engineering_milestones_command_company",
        "engineering_milestones",
        "engineering_commands",
        ["company_id", "command_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )

    for name in (
        "engineering_milestone_events_roadmap_id_fkey",
        "engineering_milestone_events_milestone_id_fkey",
    ):
        op.drop_constraint(name, "engineering_milestone_events", type_="foreignkey")
    op.create_foreign_key(
        "fk_engineering_milestone_events_scope",
        "engineering_milestone_events",
        "engineering_milestones",
        ["company_id", "roadmap_id", "milestone_id"],
        ["company_id", "roadmap_id", "id"],
        ondelete="RESTRICT",
    )

    for name in (
        "engineering_external_milestone_adoptions_roadmap_id_fkey",
        "engineering_external_milestone_adoptions_milestone_id_fkey",
    ):
        op.drop_constraint(
            name, "engineering_external_milestone_adoptions", type_="foreignkey"
        )
    op.create_foreign_key(
        "fk_external_adoptions_milestone_scope",
        "engineering_external_milestone_adoptions",
        "engineering_milestones",
        ["company_id", "roadmap_id", "milestone_id"],
        ["company_id", "roadmap_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "engineering_external_milestone_evidence_adoption_id_fkey",
        "engineering_external_milestone_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_external_evidence_adoption_company",
        "engineering_external_milestone_evidence",
        "engineering_external_milestone_adoptions",
        ["company_id", "adoption_id"],
        ["company_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_external_evidence_adoption_company",
        "engineering_external_milestone_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "engineering_external_milestone_evidence_adoption_id_fkey",
        "engineering_external_milestone_evidence",
        "engineering_external_milestone_adoptions",
        ["adoption_id"],
        ["id"],
    )

    op.drop_constraint(
        "fk_external_adoptions_milestone_scope",
        "engineering_external_milestone_adoptions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "engineering_external_milestone_adoptions_roadmap_id_fkey",
        "engineering_external_milestone_adoptions",
        "engineering_roadmaps",
        ["roadmap_id"],
        ["id"],
    )
    op.create_foreign_key(
        "engineering_external_milestone_adoptions_milestone_id_fkey",
        "engineering_external_milestone_adoptions",
        "engineering_milestones",
        ["milestone_id"],
        ["id"],
    )

    op.drop_constraint(
        "fk_engineering_milestone_events_scope",
        "engineering_milestone_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "engineering_milestone_events_roadmap_id_fkey",
        "engineering_milestone_events",
        "engineering_roadmaps",
        ["roadmap_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "engineering_milestone_events_milestone_id_fkey",
        "engineering_milestone_events",
        "engineering_milestones",
        ["milestone_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "fk_engineering_milestones_command_company",
        "engineering_milestones",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_engineering_milestones_roadmap_company",
        "engineering_milestones",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "engineering_milestones_command_id_fkey",
        "engineering_milestones",
        "engineering_commands",
        ["command_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "engineering_milestones_roadmap_id_fkey",
        "engineering_milestones",
        "engineering_roadmaps",
        ["roadmap_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    for name, table in (
        ("uq_external_adoptions_company_id", "engineering_external_milestone_adoptions"),
        ("uq_engineering_milestones_company_id", "engineering_milestones"),
        ("uq_engineering_milestones_roadmap_scope", "engineering_milestones"),
        ("uq_engineering_roadmaps_company_id", "engineering_roadmaps"),
    ):
        op.drop_constraint(name, table, type_="unique")
