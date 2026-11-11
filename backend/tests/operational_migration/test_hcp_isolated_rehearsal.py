from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest


def _load_exporter():
    path = Path(__file__).parents[2] / "scripts" / "export_hcp_isolated_native_observations.py"
    spec = importlib.util.spec_from_file_location("hcp_isolated_exporter", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_restore():
    path = Path(__file__).parents[3] / "scripts" / "hcp-isolated-restore.py"
    spec = importlib.util.spec_from_file_location("hcp_isolated_restore", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def exporter():
    return _load_exporter()


@pytest.fixture
def restore():
    return _load_restore()


def observation(exporter, source_id: str = "hcp-1"):
    return exporter.Observation(
        domain="customer",
        source_id=source_id,
        native_id=f"00000000-0000-0000-0000-{source_id[-1]}".ljust(36, "0"),
        source_digest="a" * 64,
        applied_at="2026-11-10T15:48:00+00:00",
        binding_digest="b" * 64,
        package_digest="c" * 64,
        overlay_manifest_digest="d" * 64,
        overlay_receipt_digest="e" * 64,
    )


def test_preview_and_production_database_urls_are_rejected(exporter) -> None:
    for url in (
        "postgresql+asyncpg://u:p@preview.example/acp_preview",
        "postgresql+asyncpg://u:p@production.example/acp_prod",
        "postgresql+asyncpg://u:p@localhost/acp_hcp_rehearsal_import",
    ):
        with pytest.raises(ValueError):
            exporter.reject_database_url(url)


def test_wrong_repository_sha_is_rejected(exporter) -> None:
    with pytest.raises(ValueError, match="repository SHA"):
        exporter.verify_repository_sha("a" * 40, "b" * 40)


def test_wrong_schema_is_rejected(exporter) -> None:
    with pytest.raises(ValueError, match="Alembic head"):
        exporter.verify_schema_head(["wrong"])


def test_missing_and_ambiguous_lineage_are_rejected(exporter) -> None:
    with pytest.raises(ValueError, match="missing durable"):
        exporter.resolve_lineage(
            domain="customer", source_id="hcp-1", native_id="native-1", candidates=[]
        )
    candidate = {
        "domain": "customer",
        "source_id": "hcp-1",
        "native_id": "native-1",
        "source_digest": "a" * 64,
        "applied_at": "2026-11-10T15:48:00+00:00",
    }
    with pytest.raises(ValueError, match="ambiguous durable"):
        exporter.resolve_lineage(
            domain="customer",
            source_id="hcp-1",
            native_id="native-1",
            candidates=[candidate, candidate],
        )


def test_duplicate_bindings_are_rejected(exporter) -> None:
    with pytest.raises(ValueError, match="duplicate HCP source"):
        exporter.validate_observations([observation(exporter), observation(exporter)])


def test_export_is_deterministic(exporter) -> None:
    first = exporter.build_export_document(
        repository_sha="a" * 40,
        schema_head=exporter.EXPECTED_SCHEMA_HEAD,
        company_id="company",
        branch_id="branch",
        database=exporter.EXPECTED_DATABASE,
        database_user="acp_hcp_rehearsal",
        observations=[observation(exporter, "hcp-2"), observation(exporter, "hcp-1")],
    )
    second = exporter.build_export_document(
        repository_sha="a" * 40,
        schema_head=exporter.EXPECTED_SCHEMA_HEAD,
        company_id="company",
        branch_id="branch",
        database=exporter.EXPECTED_DATABASE,
        database_user="acp_hcp_rehearsal",
        observations=[observation(exporter, "hcp-1"), observation(exporter, "hcp-2")],
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.asyncio
async def test_read_only_transaction_is_enforced(exporter) -> None:
    statements = []

    class Connection:
        async def execute(self, statement):
            statements.append(str(statement))

    await exporter.set_read_only_transaction(Connection())
    assert statements == [exporter.READ_ONLY_TRANSACTION]


def test_export_file_permissions_are_0600(exporter, tmp_path: Path) -> None:
    path = tmp_path / "observations.json"
    exporter.write_private_json(path, {"contract": exporter.EXPORT_CONTRACT})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_successful_isolated_rehearsal_export_document(exporter) -> None:
    document = exporter.build_export_document(
        repository_sha="a" * 40,
        schema_head=exporter.EXPECTED_SCHEMA_HEAD,
        company_id="company",
        branch_id="branch",
        database=exporter.EXPECTED_DATABASE,
        database_user="acp_hcp_rehearsal",
        observations=[observation(exporter)],
    )
    assert document["environment"] == exporter.EXPECTED_ENVIRONMENT
    assert document["observations"][0]["source_id"] == "hcp-1"


def test_rehearsal_compose_has_no_published_port(restore) -> None:
    compose = {
        "services": {
            "postgres": {
                "labels": {
                    "acp.environment": "migration_rehearsal",
                    "acp.production_access": "false",
                    "acp.preview_access": "false",
                },
                "networks": {"migration_rehearsal": {}},
            },
            "exporter": {},
        },
        "networks": {"migration_rehearsal": {"internal": True}},
    }
    restore.validate_compose_config(compose)
    compose["services"]["postgres"]["ports"] = ["127.0.0.1:55432:5432"]
    with pytest.raises(ValueError, match="published"):
        restore.validate_compose_config(compose)
