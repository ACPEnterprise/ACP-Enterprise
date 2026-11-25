import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    BACKEND_ROOT
    / "alembic/versions/x3y5z7a9c1e4_add_identity_bound_branch_discovery.py"
)


def test_identity_branch_discovery_migration_is_chained_from_discovery_head() -> None:
    tree = ast.parse(MIGRATION.read_text())
    values = {}
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"revision", "down_revision"}
        ):
            values[node.target.id] = ast.literal_eval(node.value)

    assert values == {
        "revision": "x3y5z7a9c1e4",
        "down_revision": "w2x4z6a8c0e3",
    }


def test_identity_branch_discovery_is_user_bound_and_select_only() -> None:
    source = MIGRATION.read_text()

    assert "CREATE POLICY acp_membership_branch_discovery" in source
    assert "FOR SELECT" in source
    assert "discovery_membership.user_id = acp_rls_user_id()" in source
    assert "discovery_membership.status = 'active'" in source
