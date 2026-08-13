import ast
from pathlib import Path

MIGRATION = Path("alembic/versions/w8m0i2e4f619_create_internal_accounting_core.py")


def test_migration_is_single_revision_on_authoritative_parent() -> None:
    tree = ast.parse(MIGRATION.read_text())
    values: dict[str, object] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"revision", "down_revision", "depends_on"}
        ):
            values[node.target.id] = ast.literal_eval(node.value)
    assert values == {
        "revision": "w8m0i2e4f619",
        "down_revision": "u6k8f0h2j497",
        "depends_on": None,
    }


def test_migration_contains_posted_evidence_guards() -> None:
    migration = MIGRATION.read_text()
    assert "trg_accounting_journal_immutable" in migration
    assert "trg_accounting_line_immutable" in migration
    assert "posted accounting journals are immutable" in migration
    assert "ck_accounting_journal_posted_balanced" in migration
    assert "ck_accounting_line_one_side" in migration
