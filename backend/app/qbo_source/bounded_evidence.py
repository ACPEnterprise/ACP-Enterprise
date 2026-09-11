from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .contracts import QboSourceEnvelope, SnapshotIdentity

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class BoundedEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class BoundedEvidencePacket:
    root: Path
    manifest_path: Path
    manifest: Mapping[str, object]
    bounded_manifest: Mapping[str, object]

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()


def latest_bounded_evidence(root: Path) -> BoundedEvidencePacket | None:
    """Select the latest complete, digest-bound production financial packet."""
    root = root.expanduser().resolve()
    candidates: list[tuple[str, BoundedEvidencePacket]] = []
    for manifest_path in (root / "runs").glob("*/manifest.json"):
        manifest = _read_json(manifest_path)
        ended_at = manifest.get("ended_at")
        bounded_path = manifest_path.with_name("bounded-manifest.json")
        bounded_digest = manifest.get("bounded_snapshot_sha256")
        if not bounded_path.is_file() and bounded_digest is None:
            # Read probes are valid provider evidence, not financial populations.
            continue
        if manifest.get("state") != "complete" or not isinstance(ended_at, str):
            raise BoundedEvidenceError("bounded_source_manifest_invalid")
        if not bounded_path.is_file() or not isinstance(bounded_digest, str):
            raise BoundedEvidenceError("bounded_source_manifest_invalid")
        bounded_bytes = bounded_path.read_bytes()
        if hashlib.sha256(bounded_bytes).hexdigest() != bounded_digest:
            raise BoundedEvidenceError("bounded_snapshot_digest_conflict")
        bounded = _read_json(bounded_path)
        snapshot = manifest.get("snapshot")
        if (
            isinstance(snapshot, Mapping)
            and snapshot.get("environment") != "production"
        ):
            raise BoundedEvidenceError("non_production_snapshot_rejected")
        if not isinstance(snapshot, Mapping) or (
            bounded.get("state") != "BOUNDED_COMPLETE"
            or bounded.get("source_run_id") != manifest.get("run_id")
            or bounded.get("environment") != snapshot.get("environment")
            or bounded.get("realm_id") != snapshot.get("realm_id")
            or bounded.get("accounting_date_cutoff")
            != snapshot.get("accounting_date_cutoff")
            or bounded.get("snapshot_policy_version")
            != manifest.get("snapshot_policy_version")
        ):
            raise BoundedEvidenceError("bounded_snapshot_identity_conflict")
        candidates.append(
            (
                ended_at,
                BoundedEvidencePacket(root, manifest_path, manifest, bounded),
            )
        )
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def load_bounded_raw_rows(
    packet: BoundedEvidencePacket, *, maximum_per_family: int
) -> tuple[dict[str, list[dict[str, object]]], bool]:
    rows: dict[str, list[dict[str, object]]] = {}
    truncated = False
    for record in _included_records(packet):
        kind = _required_text(record, "entity_kind")
        family = rows.setdefault(kind, [])
        if len(family) >= maximum_per_family:
            truncated = True
            continue
        family.append(_raw_payload(packet, record))
    return rows, truncated


def load_bounded_envelopes(
    packet: BoundedEvidencePacket,
) -> tuple[tuple[str, QboSourceEnvelope], ...]:
    result = []
    for record in _included_records(packet):
        envelope_digest = _required_digest(record, "envelope_sha256")
        envelope_path = packet.root / "envelopes" / f"{envelope_digest}.json"
        envelope_bytes = envelope_path.read_bytes()
        if hashlib.sha256(envelope_bytes).hexdigest() != envelope_digest:
            raise BoundedEvidenceError("source_envelope_digest_conflict")
        document = _read_json(envelope_path)
        payload = _raw_payload(packet, record)
        envelope = _envelope(document, payload)
        kind = _required_text(record, "entity_kind")
        identity = _required_digest(record, "source_identity_digest")
        expected_identity = hashlib.sha256(
            f"{kind}:{envelope.native_id}".encode()
        ).hexdigest()
        if (
            envelope.native_entity_type != kind
            or envelope.raw_sha256 != record.get("raw_sha256")
            or identity != expected_identity
        ):
            raise BoundedEvidenceError("bounded_envelope_identity_conflict")
        result.append((envelope_digest, envelope))
    return tuple(result)


def _included_records(packet: BoundedEvidencePacket) -> list[Mapping[str, object]]:
    records = packet.bounded_manifest.get("included_entities")
    if not isinstance(records, list) or any(
        not isinstance(record, Mapping) for record in records
    ):
        raise BoundedEvidenceError("bounded_entities_invalid")
    return records


def _raw_payload(
    packet: BoundedEvidencePacket, record: Mapping[str, object]
) -> dict[str, object]:
    digest = _required_digest(record, "raw_sha256")
    path = packet.root / "blobs" / digest[:2] / digest
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise BoundedEvidenceError("source_blob_digest_conflict")
    return _read_json(path)


def _envelope(
    document: Mapping[str, object], payload: Mapping[str, object]
) -> QboSourceEnvelope:
    snapshot = document.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise BoundedEvidenceError("source_envelope_snapshot_invalid")
    try:
        return QboSourceEnvelope(
            schema_version=_required_text(document, "schema_version"),
            provider=_required_text(document, "provider"),
            snapshot=SnapshotIdentity(
                snapshot_id=_required_text(snapshot, "snapshot_id"),
                realm_id=_required_text(snapshot, "realm_id"),
                environment=_required_text(snapshot, "environment"),
                accounting_date_cutoff=date.fromisoformat(
                    _required_text(snapshot, "accounting_date_cutoff")
                ),
                cutoff_timezone=_required_text(snapshot, "cutoff_timezone"),
                started_at=datetime.fromisoformat(
                    _required_text(snapshot, "started_at")
                ),
                api_minor_version=int(snapshot["api_minor_version"]),
            ),
            native_entity_type=_required_text(document, "native_entity_type"),
            native_id=_required_text(document, "native_id"),
            sync_token=_optional_text(document.get("sync_token")),
            source_created_at=_optional_datetime(document.get("source_created_at")),
            source_updated_at=_optional_datetime(document.get("source_updated_at")),
            acquired_at=datetime.fromisoformat(_required_text(document, "acquired_at")),
            raw_sha256=_required_digest(document, "raw_sha256"),
            relationship_ids=tuple(_text_list(document.get("relationship_ids"))),
            currency=_optional_text(document.get("currency")),
            source_status=_optional_text(document.get("source_status")),
            source_accounting_meaning=_mapping(
                document.get("source_accounting_meaning")
            ),
            raw_payload=payload,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BoundedEvidenceError("source_envelope_invalid") from error


def _required_text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise BoundedEvidenceError("protected_evidence_invalid")
    return result


def _required_digest(value: Mapping[str, object], key: str) -> str:
    result = _required_text(value, key)
    if not _SHA256.fullmatch(result):
        raise BoundedEvidenceError("protected_evidence_invalid")
    return result


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BoundedEvidenceError("protected_evidence_invalid")
    return value


def _optional_datetime(value: object) -> datetime | None:
    text = _optional_text(value)
    return datetime.fromisoformat(text) if text is not None else None


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise BoundedEvidenceError("protected_evidence_invalid")
    return value


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BoundedEvidenceError("protected_evidence_invalid")
    return value


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise BoundedEvidenceError("protected_evidence_unreadable") from error
    if not isinstance(value, dict):
        raise BoundedEvidenceError("protected_evidence_invalid")
    return value
