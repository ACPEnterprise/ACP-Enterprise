from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import Settings, settings

from .contracts import AcquisitionRequest, EntityKind, SnapshotIdentity
from .evidence import ProtectedFilesystemEvidenceStore, RunPageObserver
from .intuit import (
    IntuitEnvironment,
    IntuitHttpTransport,
    IntuitOAuthClient,
    IntuitReadOnlyAdapter,
    RealmBinding,
    SerializedTokenManager,
)
from .runner import (
    CATALOG_VERSION,
    OPTIONAL_PROVIDER_DEPENDENT,
    AcquisitionResult,
    AcquisitionRunner,
)
from .runtime import (
    ProtectedSandboxCompanyBinding,
    SandboxConnectionRegistry,
    SandboxRuntimeError,
    _production_runtime_root,
)
from .secrets import ProtectedProductionSecretProvider

PRODUCTION_ACQUISITION_SCOPE = tuple(EntityKind)


@dataclass(frozen=True)
class ProductionAcquisitionCommand:
    run_id: str
    cutoff: date
    cutoff_timezone: str = "America/New_York"
    page_size: int = 1000


async def execute_production_acquisition(
    command: ProductionAcquisitionCommand,
    configuration: Settings = settings,
) -> AcquisitionResult:
    """Execute one sealed GET-only real-company snapshot after owner authorization."""
    if not configuration.qbo_production_enabled:
        raise SandboxRuntimeError("production_acquisition_disabled")
    root = _production_runtime_root(configuration)
    repository = Path(configuration.qbo_repository_root).resolve()
    provider = ProtectedProductionSecretProvider(
        root=root / "secrets", repository_root=repository
    )
    registry = SandboxConnectionRegistry(root / "connections", environment="production")
    marker = _read_verified_marker(registry)
    expected_name = ProtectedSandboxCompanyBinding(root / "configuration").read()
    if marker.get("company_name") != expected_name or not marker.get(
        "acquisition_eligible"
    ):
        raise SandboxRuntimeError("production_company_not_verified")
    realm_id = marker.get("realm_id")
    if not isinstance(realm_id, str) or not realm_id:
        raise SandboxRuntimeError("production_realm_not_verified")
    evidence_root = Path(str(configuration.qbo_production_evidence_root)).resolve()
    store = ProtectedFilesystemEvidenceStore(
        root=evidence_root, repository_root=repository, bounded_snapshot=True
    )
    transport = IntuitHttpTransport()
    oauth = IntuitOAuthClient(
        environment=IntuitEnvironment.PRODUCTION,
        transport=transport,
        secrets=provider,
        credential_reference=provider.CLIENT_REFERENCE,
    )
    binding = RealmBinding(
        environment=IntuitEnvironment.PRODUCTION,
        realm_id=realm_id,
        expected_company_name=expected_name,
        credential_reference=provider.CLIENT_REFERENCE,
        token_reference=provider.TOKEN_REFERENCE,
    )
    adapter = IntuitReadOnlyAdapter(
        binding=binding,
        token_manager=SerializedTokenManager(
            oauth=oauth, secrets=provider, binding=binding
        ),
        transport=transport,
        page_observer=RunPageObserver(store=store, run_id=command.run_id),
        optional_provider_dependent=frozenset(
            EntityKind(value) for value in OPTIONAL_PROVIDER_DEPENDENT
        ),
        catalog_version=CATALOG_VERSION,
    )
    requested_snapshot = SnapshotIdentity(
        snapshot_id=command.run_id,
        realm_id=realm_id,
        environment="production",
        accounting_date_cutoff=command.cutoff,
        cutoff_timezone=command.cutoff_timezone,
        started_at=datetime.now(ZoneInfo(command.cutoff_timezone)).astimezone(
            timezone.utc
        ),
        api_minor_version=configuration.qbo_production_api_minor_version,
    )
    stored_snapshot = store.stored_snapshot(run_id=command.run_id)
    if stored_snapshot is not None:
        if (
            stored_snapshot.snapshot_id != requested_snapshot.snapshot_id
            or stored_snapshot.realm_id != requested_snapshot.realm_id
            or stored_snapshot.environment != requested_snapshot.environment
            or stored_snapshot.accounting_date_cutoff
            != requested_snapshot.accounting_date_cutoff
            or stored_snapshot.cutoff_timezone != requested_snapshot.cutoff_timezone
            or stored_snapshot.api_minor_version != requested_snapshot.api_minor_version
        ):
            raise SandboxRuntimeError("production_acquisition_resume_conflict")
        snapshot = stored_snapshot
    else:
        snapshot = requested_snapshot
    request = AcquisitionRequest(
        snapshot=snapshot,
        entity_kinds=PRODUCTION_ACQUISITION_SCOPE,
        page_size=command.page_size,
    )
    return await AcquisitionRunner(provider=adapter, evidence_store=store).run(
        run_id=command.run_id, request=request, company_name=expected_name
    )


def _read_verified_marker(registry: SandboxConnectionRegistry) -> dict[str, object]:
    try:
        value = json.loads(registry.verified_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise SandboxRuntimeError("production_connection_not_verified") from error
    if not isinstance(value, dict) or value.get("environment") != "production":
        raise SandboxRuntimeError("production_connection_not_verified")
    return value


def run(command: ProductionAcquisitionCommand) -> AcquisitionResult:
    return asyncio.run(execute_production_acquisition(command))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seal one authorized QBO read-only snapshot"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cutoff", required=True, type=date.fromisoformat)
    arguments = parser.parse_args()
    result = run(ProductionAcquisitionCommand(arguments.run_id, arguments.cutoff))
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "state": result.state.value,
                "envelope_count": result.envelope_count,
                "manifest_sha256": result.manifest_sha256,
                "failure_code": result.failure_code,
                "bounded_snapshot": result.bounded_snapshot,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
