from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path

from app.core.config import Settings, settings

from .contracts import (
    AcquisitionRequest,
    EntityKind,
    QboSourceEnvelope,
    SnapshotIdentity,
)
from .evidence import ProtectedFilesystemEvidenceStore, RunPageObserver, RunState
from .fixture_reconciliation import reconcile_fixture
from .intuit import (
    IntuitEnvironment,
    IntuitHttpTransport,
    IntuitOAuthClient,
    IntuitReadOnlyAdapter,
    RealmBinding,
    SerializedTokenManager,
)
from .runtime import ProtectedSandboxCompanyBinding, _runtime_root
from .sandbox_fixture import SandboxFixtureError, _read_json
from .secrets import ProtectedSandboxSecretProvider
from .transformation import transform_qbo_envelope

HISTORY_VERSION = "qbo-sandbox-representative-history-acquisition/v1"


async def acquire_and_reconcile(
    *,
    repository_sha: str,
    acquisition_id: str,
    configuration: Settings = settings,
) -> dict[str, object]:
    if not configuration.qbo_sandbox_enabled or configuration.qbo_production_enabled:
        raise SandboxFixtureError("history_environment_not_isolated")
    root = _runtime_root(configuration)
    marker = _read_json(root / "connections" / "verified.json")
    if (
        marker.get("environment") != "sandbox"
        or marker.get("acquisition_eligible") is not True
    ):
        raise SandboxFixtureError("history_connection_not_verified")
    realm_id = str(marker.get("realm_id", ""))
    fixture_roots = sorted((root / "fixtures").glob("*/fixture-manifest.json"))
    if len(fixture_roots) != 1:
        raise SandboxFixtureError("history_fixture_authority_ambiguous")
    fixture_manifest = _read_json(fixture_roots[0])
    expected_manifest = _read_json(fixture_roots[0].with_name("expected-ledger.json"))
    repository = Path(configuration.qbo_repository_root).resolve()
    evidence = ProtectedFilesystemEvidenceStore(
        root=root / "representative-history-evidence", repository_root=repository
    )
    token_manager, binding = _build_provider(configuration, root, realm_id)
    snapshot = SnapshotIdentity(
        snapshot_id=acquisition_id,
        realm_id=realm_id,
        environment="sandbox",
        accounting_date_cutoff=date(2026, 8, 29),
        cutoff_timezone="America/New_York",
        started_at=datetime.now(timezone.utc),
        api_minor_version=configuration.qbo_sandbox_api_minor_version,
    )
    counts: dict[str, int] = {}
    manifests: dict[str, str] = {}
    unavailable: dict[str, str] = {}
    envelopes: dict[tuple[str, str], QboSourceEnvelope] = {}
    candidate_digests: list[str] = []
    for kind in EntityKind:
        run_id = f"{acquisition_id}-{kind.value}"
        request = AcquisitionRequest(
            snapshot=snapshot, entity_kinds=(kind,), page_size=100
        )
        evidence.begin_run(
            run_id=run_id,
            snapshot=snapshot,
            company_name=binding.expected_company_name,
        )
        adapter = IntuitReadOnlyAdapter(
            binding=binding,
            token_manager=token_manager,
            transport=IntuitHttpTransport(),
            page_observer=RunPageObserver(store=evidence, run_id=run_id),
        )
        acquired = 0
        try:
            async for envelope in adapter.acquire(request):
                evidence.store_envelope(run_id=run_id, envelope=envelope)
                envelopes[(envelope.native_entity_type, envelope.native_id)] = envelope
                candidate_digests.append(
                    transform_qbo_envelope(envelope).candidate_sha256
                )
                acquired += 1
            manifests[kind.value] = evidence.finish_run(
                run_id=run_id,
                state=RunState.COMPLETE,
                ended_at=datetime.now(timezone.utc),
            )
            counts[kind.value] = acquired
        except Exception as error:  # noqa: BLE001 - preserve bounded provider outcome
            code = str(getattr(error, "code", "history_acquisition_failed"))
            manifests[kind.value] = evidence.finish_run(
                run_id=run_id,
                state=RunState.PARTIAL,
                ended_at=datetime.now(timezone.utc),
                failure_code=code,
            )
            unavailable[kind.value] = code
            counts[kind.value] = acquired
    fixture_envelopes = {
        (family, native_id): envelopes[(family, native_id)]
        for family, native_id in (
            (str(item["family"]), str(item["native_id"]))
            for item in fixture_manifest.get("objects", [])
            if isinstance(item, Mapping)
        )
    }
    reconciliation = reconcile_fixture(
        fixture_manifest=fixture_manifest,
        expected_manifest=expected_manifest,
        envelopes=fixture_envelopes,
    )
    canonical = {
        "schema_version": HISTORY_VERSION,
        "repository_sha": repository_sha,
        "acquisition_id": acquisition_id,
        "environment": "sandbox",
        "fixture_digest": fixture_manifest["fixture_digest"],
        "counts": dict(sorted(counts.items())),
        "manifests": dict(sorted(manifests.items())),
        "unavailable": dict(sorted(unavailable.items())),
        "candidate_digests": sorted(candidate_digests),
        "reconciliation_sha256": reconciliation.reconciliation_sha256,
    }
    aggregate_digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "state": reconciliation.state,
        "acquisition_id": acquisition_id,
        "aggregate_digest": aggregate_digest,
        "fixture_digest": fixture_manifest["fixture_digest"],
        "expected_ledger_digest": reconciliation.expected_ledger_digest,
        "reconciliation_digest": reconciliation.reconciliation_sha256,
        "counts": dict(sorted(counts.items())),
        "unavailable": dict(sorted(unavailable.items())),
        "zero_deltas": all(
            value == "0.00" or value == "0"
            for value in reconciliation.deltas.values()
        ),
        "invariants": dict(sorted(reconciliation.invariants.items())),
    }


def _build_provider(
    configuration: Settings, root: Path, realm_id: str
) -> tuple[SerializedTokenManager, RealmBinding]:
    expected = ProtectedSandboxCompanyBinding(root / "configuration").read()
    secrets = ProtectedSandboxSecretProvider(
        root=root / "secrets", repository_root=Path(configuration.qbo_repository_root)
    )
    binding = RealmBinding(
        environment=IntuitEnvironment.SANDBOX,
        realm_id=realm_id,
        expected_company_name=expected,
        credential_reference=secrets.CLIENT_REFERENCE,
        token_reference=secrets.TOKEN_REFERENCE,
    )
    oauth = IntuitOAuthClient(
        environment=IntuitEnvironment.SANDBOX,
        transport=IntuitHttpTransport(),
        secrets=secrets,
        credential_reference=secrets.CLIENT_REFERENCE,
    )
    return (
        SerializedTokenManager(oauth=oauth, secrets=secrets, binding=binding),
        binding,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire and reconcile representative QBO sandbox history"
    )
    parser.add_argument("acquire", choices=("acquire",))
    parser.add_argument("--repository-sha", required=True)
    parser.add_argument("--acquisition-id", required=True)
    arguments = parser.parse_args()
    try:
        result = asyncio.run(
            acquire_and_reconcile(
                repository_sha=arguments.repository_sha,
                acquisition_id=arguments.acquisition_id,
            )
        )
        print(json.dumps(result, sort_keys=True))
    except SandboxFixtureError as error:
        print(
            json.dumps(
                {"state": "REJECTED", "error_code": error.code}, sort_keys=True
            )
        )
        raise SystemExit(2) from None
    except Exception:  # noqa: BLE001 - command output must remain source-safe
        print(json.dumps({"state": "REJECTED", "error_code": "history_failed"}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
