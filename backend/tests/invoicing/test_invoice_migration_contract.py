import ast
from pathlib import Path

MIGRATION = Path(
    "alembic/versions/w8m0i2k4n619_create_invoice_accounts_receivable_.py"
)


def test_invoice_migration_remains_on_the_authoritative_accounting_parent() -> None:
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
        "revision": "w8m0i2k4n619",
        "down_revision": "w8m0i2e4f619",
        "depends_on": None,
    }


def test_legacy_number_exception_requires_immutable_source_provenance() -> None:
    migration = MIGRATION.read_text()
    assert (
        "identity_origin = 'native' AND invoice_number ~ '^INV-[0-9]{6,}$'"
        in migration
    )
    assert "identity_origin = 'grandfathered_legacy'" in migration
    assert "operational_migration_invoice_source_identities" in migration
    assert (
        "grandfathered Invoice requires authoritative migration source provenance"
        in migration
    )
    assert "invoice identity provenance is immutable" in migration
    assert "DEFERRABLE INITIALLY DEFERRED" in migration
