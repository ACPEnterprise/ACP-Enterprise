from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path


def module():
    path = Path(__file__).parents[3] / "scripts/migration-candidate-sweep"
    loader = SourceFileLoader("migration_candidate_sweep", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_downgrade_cleanup_is_not_reported_as_upgrade_destruction() -> None:
    content = """
def upgrade():
    op.create_table("safe")

def downgrade():
    op.drop_table("safe")
"""
    assert module().destructive_upgrade_operations(content) == []


def test_destructive_upgrade_operations_are_reported() -> None:
    content = """
def upgrade():
    op.drop_column("jobs", "legacy")
    op.alter_column("jobs", "code", nullable=False)
    op.execute("DELETE FROM jobs WHERE archived = true")
"""
    assert module().destructive_upgrade_operations(content) == [
        "op.alter_column(nullable=False)",
        "op.drop_column",
        "op.execute(DELETE)",
    ]


def test_created_objects_ignore_downgrade_recreation() -> None:
    content = """
def upgrade():
    op.create_table("jobs")
    op.create_index("ix_jobs_status", "jobs", ["status"])

def downgrade():
    op.create_table("legacy_jobs")
"""
    assert module().created_schema_objects(content) == [
        "index:ix_jobs_status",
        "table:jobs",
    ]
