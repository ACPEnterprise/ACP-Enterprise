from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayKey,
    OverlayRecord,
    OverlaySourceState,
)
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_bundle import (
    NovemberQualificationAuthority,
    qualification_digest,
)
from app.operational_migration.hcp_november_executor import (
    NovemberBoundedExecutor,
    NovemberExecutionEnvelope,
    NovemberExecutionPacket,
    PACKET_CONTRACT,
    ENVELOPE_CONTRACT,
    _packet_inventory,
    require_execution_authorization,
    validate_runtime_boundary,
    _digest,
)


BUNDLE = "a" * 64
POLICY = "b" * 64
RECONCILIATION = "c" * 64
BACKUP = "d" * 64
SHA = "e" * 40
SCHEMA = "yp8r0t2v4x6z"
COMPANY = "3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd"
BRANCH = "887f413a-70dc-4ab1-98aa-8e84f4e7efd0"
ACTOR = "c427ebd1-7583-4c0d-9c54-55a0c1214174"
PROVIDER = "aba4de03-d1b7-4c4e-8fb6-32a3fca713f5"
ACQUIRED = "2026-11-11T12:00:00+00:00"


class MemoryRepository:
    def __init__(self, *, fail_source: str | None = None) -> None:
        self.states: dict[OverlayKey, OverlaySourceState] = {}
        self.receipts: dict[str, object] = {}
        self.assertions: list[object] = []
        self.fail_source = fail_source

    @asynccontextmanager
    async def transaction(self):
        states = deepcopy(self.states)
        receipts = deepcopy(self.receipts)
        assertions = deepcopy(self.assertions)
        try:
            yield
        except Exception:
            self.states = states
            self.receipts = receipts
            self.assertions = assertions
            raise

    async def prior_receipt(self, manifest_digest: str):
        return self.receipts.get(manifest_digest)

    async def source_state(self, key: OverlayKey):
        return self.states.get(key)

    async def source_exists(self, key: OverlayKey) -> bool:
        return key in self.states

    async def fingerprint_owners(self, domain: str, fingerprint: str):
        return ()

    async def create(self, record):
        if record.source_id == self.fail_source:
            raise RuntimeError("synthetic partial failure")
        state = OverlaySourceState(record.source_digest, f"native-{record.source_id}", record.payload)
        self.states[record.key] = state
        return state

    async def update(self, state, record):
        updated = OverlaySourceState(record.source_digest, state.native_id, record.payload)
        self.states[record.key] = updated
        return updated

    async def record_non_mutating_assertion(self, record):
        self.assertions.append(record)

    async def persist_receipt(self, receipt):
        self.receipts[receipt.manifest_digest] = receipt


def _hold_records() -> tuple[list[dict], dict[str, tuple[str, ...]]]:
    records: list[dict] = []
    hold_ids = {
        "locationless_open_jobs": tuple(f"job-{i}" for i in range(22)),
        "legacy_duplicate_risk_appointments": tuple(f"appt-dup-{i}" for i in range(13)),
        "unresolved_technician_identities": ("tech-0", "tech-1"),
        "unassigned_appointments": ("appt-unassigned",),
    }
    for category, ids in hold_ids.items():
        disposition = "HOLD_QUARANTINE" if category == "locationless_open_jobs" else "HOLD"
        for source_id in ids:
            records.append(
                {
                "domain": (
                    "job"
                    if category == "locationless_open_jobs"
                    else "technician_reference"
                    if category == "unresolved_technician_identities"
                    else "appointment"
                ),
                    "source_id": source_id,
                    "assertion": "hold",
                    "source_digest": BUNDLE,
                    "acquired_at": ACQUIRED,
                    "payload": {},
                    "parent_keys": [],
                    "disposition": disposition,
                }
            )
    return records, hold_ids


def _packet(*, include_clean: bool = True) -> tuple[NovemberExecutionPacket, dict, NovemberQualificationAuthority]:
    records, hold_ids = _hold_records()
    if include_clean:
        records.append(
            {
                "domain": "job",
                "source_id": "clean-job",
                "assertion": "create",
                "source_digest": POLICY,
                "acquired_at": ACQUIRED,
                "payload": {"status": "ready"},
                "parent_keys": [],
                "disposition": "CREATE",
            }
        )
    overlay = CurrentOverlayManifest.build(
        base_source4_digest=BUNDLE,
        delta_digest=POLICY,
        company_id=COMPANY,
        branch_id=BRANCH,
        acquired_at=ACQUIRED,
        records=tuple(
            # Match the packet conversion performed by load().
            OverlayRecord(
                item["domain"], item["source_id"],
                OverlayAssertion(item["assertion"]), item["source_digest"],
                item["acquired_at"], item["payload"],
                parent_keys=tuple(OverlayKey(**parent) for parent in item["parent_keys"]),
            )
            for item in records
        ),
    )
    values = {
        "contract": PACKET_CONTRACT,
        "qualification_digest": "pending",
        "bundle_sha256": BUNDLE,
        "policy_digest": POLICY,
        "reconciliation_digest": RECONCILIATION,
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "actor_id": ACTOR,
        "provider_company_id": PROVIDER,
        "repository_sha": SHA,
        "schema_head": SCHEMA,
        "environment": "preview",
        "records": records,
        "acquired_at": ACQUIRED,
    }
    qualified = {
        "qualification": "PASS",
        "hold_source_ids": hold_ids,
        "unexplained_omissions": 0,
    }
    values["qualification_digest"] = qualification_digest(qualified)
    packet = NovemberExecutionPacket(
        qualification_digest=values["qualification_digest"],
        bundle_sha256=BUNDLE,
        policy_digest=POLICY,
        reconciliation_digest=RECONCILIATION,
        company_id=COMPANY,
        branch_id=BRANCH,
        actor_id=ACTOR,
        provider_company_id=PROVIDER,
        repository_sha=SHA,
        schema_head=SCHEMA,
        environment="preview",
        records=tuple(records),
        digest=_digest(values),
        overlay_manifest=overlay,
    )
    authority = NovemberQualificationAuthority(
        bundle_path=Path("/tmp/bundle"),
        bundle_sha256=BUNDLE,
        expected_repository_sha=SHA,
        expected_schema_head=SCHEMA,
        expected_company_id=COMPANY,
        expected_branch_id=BRANCH,
        expected_actor_id=ACTOR,
        expected_hcp_provider_company_id=PROVIDER,
        expected_environment="preview",
        expected_acquisition_digest="1" * 64,
        expected_reconciliation_digest=RECONCILIATION,
        expected_attachment_custody_digest="2" * 64,
        qualification_status="PASS",
        qualification_digest=values["qualification_digest"],
        rollback_backup_digest=BACKUP,
        expected_policy_digest=POLICY,
    )
    return packet, qualified, authority


def _full_november_packet() -> NovemberExecutionPacket:
    records: list[dict] = []
    domains = ("customer", "service_location", "job", "appointment")
    for disposition, count in (("CREATE", 511), ("UPDATE", 823), ("REPLAY", 3857)):
        for index in range(count):
            records.append(
                {
                    "domain": domains[index % len(domains)],
                    "source_id": f"{disposition.lower()}-{index}",
                    "assertion": "update" if disposition == "UPDATE" else "create",
                    "source_digest": POLICY,
                    "prior_source_digest": BUNDLE if disposition == "UPDATE" else None,
                    "acquired_at": ACQUIRED,
                    "payload": {},
                    "parent_keys": [],
                    "disposition": disposition,
                }
            )
    for index in range(2079):
        if index < 14:
            domain = "appointment"
        elif index < 16:
            domain = "technician_reference"
        elif index == 16:
            domain = "appointment"
        else:
            domain = ("invoice", "note", "attachment", "history")[index % 4]
        records.append(
            {
                "domain": domain,
                "source_id": f"hold-{index}",
                "assertion": "hold",
                "source_digest": BUNDLE,
                "acquired_at": ACQUIRED,
                "payload": {},
                "parent_keys": [],
                "disposition": "HOLD",
            }
        )
    for index in range(23):
        records.append(
            {
                "domain": "job",
                "source_id": f"quarantine-{index}",
                "assertion": "hold",
                "source_digest": BUNDLE,
                "acquired_at": ACQUIRED,
                "payload": {},
                "parent_keys": [],
                "disposition": "HOLD_QUARANTINE",
            }
        )
    values = {
        "contract": PACKET_CONTRACT,
        "qualification_digest": "9" * 64,
        "bundle_sha256": BUNDLE,
        "policy_digest": POLICY,
        "reconciliation_digest": RECONCILIATION,
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "actor_id": ACTOR,
        "provider_company_id": PROVIDER,
        "repository_sha": SHA,
        "schema_head": SCHEMA,
        "environment": "preview",
        "records": records,
        "acquired_at": ACQUIRED,
    }
    return NovemberExecutionPacket(
        qualification_digest=values["qualification_digest"],
        bundle_sha256=BUNDLE,
        policy_digest=POLICY,
        reconciliation_digest=RECONCILIATION,
        company_id=COMPANY,
        branch_id=BRANCH,
        actor_id=ACTOR,
        provider_company_id=PROVIDER,
        repository_sha=SHA,
        schema_head=SCHEMA,
        environment="preview",
        records=tuple(records),
        digest=_digest(values),
        overlay_manifest=CurrentOverlayManifest.build(
            base_source4_digest=BUNDLE,
            delta_digest=POLICY,
            company_id=COMPANY,
            branch_id=BRANCH,
            acquired_at=ACQUIRED,
            records=tuple(
                OverlayRecord(
                    item["domain"],
                    item["source_id"],
                    OverlayAssertion(item["assertion"]),
                    item["source_digest"],
                    item["acquired_at"],
                    item["payload"],
                    prior_source_digest=item.get("prior_source_digest"),
                )
                for item in records
            ),
        ),
    )


def _write_envelope(tmp_path: Path, packet: NovemberExecutionPacket, authority: NovemberQualificationAuthority) -> tuple[Path, NovemberQualificationAuthority]:
    source_path = tmp_path / "source-packet.json"
    source_payload = {
        "contract": PACKET_CONTRACT,
        "qualification_digest": packet.qualification_digest,
        "bundle_sha256": packet.bundle_sha256,
        "policy_digest": packet.policy_digest,
        "reconciliation_digest": packet.reconciliation_digest,
        "company_id": packet.company_id,
        "branch_id": packet.branch_id,
        "actor_id": packet.actor_id,
        "provider_company_id": packet.provider_company_id,
        "repository_sha": packet.repository_sha,
        "schema_head": packet.schema_head,
        "environment": packet.environment,
        "records": list(packet.records),
        "digest": packet.digest,
        "acquired_at": packet.overlay_manifest.acquired_at,
    }
    source_path.write_text(json.dumps(source_payload, sort_keys=True, separators=(",", ":")))
    source_path.chmod(0o600)
    inventory = _packet_inventory(packet.records)
    envelope = NovemberExecutionEnvelope(
        source_packet_path=source_path,
        source_packet_sha256=__import__("hashlib").sha256(source_path.read_bytes()).hexdigest(),
        source_packet_digest=packet.digest,
        bundle_sha256=BUNDLE,
        policy_digest=POLICY,
        reconciliation_digest=RECONCILIATION,
        company_id=COMPANY,
        branch_id=BRANCH,
        actor_id=ACTOR,
        provider_company_id=PROVIDER,
        repository_sha=SHA,
        schema_head=SCHEMA,
        environment="preview",
        packet_counts=inventory["counts"],
        total_held=inventory["total_held"],
        executable_count=inventory["executable"],
        unexplained_omissions=0,
        lineage_gaps=0,
        ambiguous_lineage=0,
        held_parent_executable_edges=0,
        operational_hold_policy={
            "locationless_open_jobs": 23,
            "duplicate_risk_appointments": 14,
            "unresolved_technician_identities": 2,
            "unassigned_appointments": 1,
        },
        operational_hold_source_ids={
            "locationless_open_jobs": tuple(f"quarantine-{index}" for index in range(23)),
            "duplicate_risk_appointments": tuple(f"hold-{index}" for index in range(14)),
            "unresolved_technician_identities": ("hold-14", "hold-15"),
            "unassigned_appointments": ("hold-16",),
        },
        authority_digest="",
        packet=packet,
    )
    envelope = NovemberExecutionEnvelope(
        **{**envelope.__dict__, "authority_digest": _digest(envelope._authority_payload())}
    )
    envelope_path = tmp_path / "execution-envelope.json"
    envelope_payload = envelope._authority_payload() | {
        "source_packet_path": str(source_path),
        "authority_digest": envelope.authority_digest,
    }
    envelope_path.write_text(json.dumps(envelope_payload, sort_keys=True, separators=(",", ":")))
    envelope_path.chmod(0o600)
    qualified_authority = NovemberQualificationAuthority(
        **{
            **authority.__dict__,
            "execution_packet_path": envelope_path,
            "execution_packet_sha256": __import__("hashlib").sha256(envelope_path.read_bytes()).hexdigest(),
            "execution_packet_digest": envelope.authority_digest,
        }
    )
    return envelope_path, qualified_authority


@pytest.mark.asyncio
async def test_clean_records_execute_and_replay_with_complete_receipt() -> None:
    packet, qualified, authority = _packet()
    repository = MemoryRepository()
    executor = NovemberBoundedExecutor()

    first = await executor.execute(
        repository,
        authority=authority,
        packet=packet,
        qualified_packet=qualified,
        database_identity="acp_enterprise_preview:acp_enterprise",
        schema_head=SCHEMA,
        execution_timestamp="2026-11-11T12:01:00+00:00",
    )
    replay = await executor.execute(
        repository,
        authority=authority,
        packet=packet,
        qualified_packet=qualified,
        database_identity="acp_enterprise_preview:acp_enterprise",
        schema_head=SCHEMA,
        execution_timestamp="2026-11-11T12:02:00+00:00",
    )

    assert first == replay
    assert first.execution_context["counts"] == {
        "CREATE": 1,
        "UPDATE": 0,
        "REPLAY": 0,
        "HOLD": 16,
        "HOLD_QUARANTINE": 22,
    }
    assert first.execution_context["packet_record_count"] == 39
    assert first.execution_context["unaccounted_records"] == 0
    assert len(first.execution_context["affected_source_native_ids"]) == 39
    assert first.execution_context["unexplained_omissions"] == 0


@pytest.mark.asyncio
async def test_held_records_cannot_execute_and_partial_failure_rolls_back() -> None:
    packet, qualified, authority = _packet()
    repository = MemoryRepository(fail_source="clean-job")

    with pytest.raises(RuntimeError, match="partial failure"):
        await NovemberBoundedExecutor().execute(
            repository,
            authority=authority,
            packet=packet,
            qualified_packet=qualified,
            database_identity="acp_enterprise_preview:acp_enterprise",
            schema_head=SCHEMA,
        )

    assert repository.states == {}
    assert len(repository.assertions) == 0


def test_stale_authority_production_target_and_missing_authorization_reject() -> None:
    packet, qualified, authority = _packet()
    stale = NovemberQualificationAuthority(
        **{
            **authority.__dict__,
            "expected_policy_digest": "9" * 64,
        }
    )
    with pytest.raises(SafeEvidenceError, match="hcp_november_execution_authority_mismatch"):
        packet.verify_against(stale, qualified)
    with pytest.raises(SafeEvidenceError, match="preview_runtime_boundary_invalid"):
        validate_runtime_boundary("production", False, True)
    with pytest.raises(SafeEvidenceError, match="explicit_execution_authorization_required"):
        require_execution_authorization(False)


def test_full_november_inventory_and_envelope_preserve_source_packet(
    tmp_path: Path,
) -> None:
    packet = _full_november_packet()
    inventory = _packet_inventory(packet.records)
    assert inventory["counts"] == {
        "CREATE": 511,
        "UPDATE": 823,
        "REPLAY": 3857,
        "HOLD": 2079,
        "HOLD_QUARANTINE": 23,
    }
    assert inventory["total_held"] == 2102
    assert inventory["executable"] == 5191
    assert {item["domain"] for item in packet.records if item["disposition"] in {"HOLD", "HOLD_QUARANTINE"}} >= {
        "invoice",
        "note",
        "attachment",
        "history",
        "technician_reference",
    }
    _, _, authority = _packet()
    envelope_path, envelope_authority = _write_envelope(tmp_path, packet, authority)
    source_bytes_before = (tmp_path / "source-packet.json").read_bytes()
    envelope = NovemberExecutionEnvelope.load(envelope_path)
    envelope.verify_against(envelope_authority)
    assert envelope.packet.digest == packet.digest
    assert Path(envelope.source_packet_path).read_bytes() == source_bytes_before


def test_execution_envelope_authority_mismatch_fails_closed(tmp_path: Path) -> None:
    packet = _full_november_packet()
    _, _, authority = _packet()
    envelope_path, envelope_authority = _write_envelope(tmp_path, packet, authority)
    stale = NovemberQualificationAuthority(
        **{**envelope_authority.__dict__, "expected_repository_sha": "f" * 40}
    )
    envelope = NovemberExecutionEnvelope.load(envelope_path)
    with pytest.raises(SafeEvidenceError, match="hcp_november_execution_authority_mismatch"):
        envelope.verify_against(stale)
