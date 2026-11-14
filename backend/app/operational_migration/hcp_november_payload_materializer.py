"""Resolve qualified November payload locators from sealed private evidence.

The qualified packet is immutable classification data.  This module creates a
separate, deterministic view with payloads attached; it never edits the source
packet and never treats a manifest digest as a payload body.
"""

from __future__ import annotations

import copy
import hashlib
import json
import stat
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_executor import _digest


WRITE_DISPOSITIONS = frozenset({"CREATE", "UPDATE", "REPLAY"})


def _fail(code: str, value: object = "") -> None:
    raise SafeEvidenceError(code, _digest(value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: object) -> Path:
    if not isinstance(value, str) or not value or value.startswith("/"):
        _fail("hcp_november_payload_locator_invalid", value)
    path = Path(value)
    if ".." in path.parts:
        _fail("hcp_november_payload_locator_escape", value)
    return path


def _records(document: object, *, path: Path) -> list[dict[str, Any]]:
    if isinstance(document, dict) and isinstance(document.get("records"), list):
        value = document["records"]
    elif isinstance(document, list):
        value = document
    else:
        _fail("hcp_november_payload_evidence_records_missing", str(path))
    if not all(isinstance(item, dict) for item in value):
        _fail("hcp_november_payload_evidence_record_invalid", str(path))
    return [dict(item) for item in value]


def _locator(value: object) -> tuple[Path, str, str]:
    if not isinstance(value, str) or "#" not in value:
        _fail("hcp_november_payload_locator_invalid", value)
    relative, selector = value.split("#", 1)
    if ":" not in selector:
        _fail("hcp_november_payload_locator_selector_invalid", value)
    domain, source_id = selector.split(":", 1)
    if not domain or not source_id:
        _fail("hcp_november_payload_locator_selector_invalid", value)
    return _safe_relative_path(relative), domain, source_id


def _source_digest(record: dict[str, Any]) -> str | None:
    for key in ("source_digest", "_source_digest", "digest"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    payload = record.get("payload")
    if isinstance(payload, dict):
        value = payload.get("_source_digest")
        if isinstance(value, str) and value:
            return value
    return None


def _lineage(record: dict[str, Any]) -> set[tuple[str, str]]:
    value = record.get("parent_keys", record.get("parent_lineage", []))
    if not isinstance(value, list):
        _fail("hcp_november_payload_lineage_missing", record.get("source_id"))
    result: set[tuple[str, str]] = set()
    for parent in value:
        if not isinstance(parent, dict) or not parent.get("domain") or not parent.get("source_id"):
            _fail("hcp_november_payload_lineage_invalid", record.get("source_id"))
        result.add((str(parent["domain"]), str(parent["source_id"])))
    return result

def _resolve(
    *,
    evidence_root: Path,
    locator: object,
    expected_domain: str,
    expected_source_id: str,
    expected_digest: str,
    expected_parents: set[tuple[str, str]],
    cache: dict[Path, tuple[str, list[dict[str, Any]]]],
) -> tuple[dict[str, Any], str]:
    relative, locator_domain, locator_source_id = _locator(locator)
    if (locator_domain, locator_source_id) != (expected_domain, expected_source_id):
        _fail("hcp_november_payload_locator_identity_mismatch", locator)
    path = (evidence_root / relative).resolve()
    root = evidence_root.resolve()
    if root not in path.parents or path.is_symlink() or not path.is_file():
        _fail("hcp_november_payload_source_object_missing", str(relative))
    if path not in cache:
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            _fail("hcp_november_payload_evidence_permissions", str(relative))
        try:
            document = json.loads(path.read_bytes())
        except (OSError, ValueError) as error:
            _fail("hcp_november_payload_evidence_invalid", str(error))
        cache[path] = (_sha256(path), _records(document, path=path))
    file_digest, candidates = cache[path]
    matches = [
        item
        for item in candidates
        if item.get("domain") == expected_domain
        and item.get("source_id") == expected_source_id
    ]
    if len(matches) != 1:
        _fail("hcp_november_payload_resolution_ambiguous", (str(relative), expected_source_id, len(matches)))
    match = matches[0]
    actual_digest = _source_digest(match)
    if actual_digest != expected_digest:
        _fail("hcp_november_payload_digest_mismatch", expected_source_id)
    if _lineage(match) != expected_parents:
        _fail("hcp_november_payload_lineage_mismatch", expected_source_id)
    payload = match.get("payload")
    if not isinstance(payload, dict):
        _fail("hcp_november_payload_unsupported", expected_source_id)
    return dict(payload), file_digest


def materialize_executable_payloads(
    source_packet: dict[str, Any],
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    """Return a payload-materialized copy of ``source_packet``.

    Every executable record must resolve exactly once.  HOLD records are copied
    byte-for-byte at the record level and are never resolved or made writable.
    """

    if not isinstance(source_packet, dict) or not isinstance(source_packet.get("records"), list):
        _fail("hcp_november_payload_packet_invalid")
    if not evidence_root.is_dir() or evidence_root.is_symlink():
        _fail("hcp_november_payload_evidence_root_missing", str(evidence_root))
    result = copy.deepcopy(source_packet)
    cache: dict[Path, tuple[str, list[dict[str, Any]]]] = {}
    for item in result["records"]:
        if not isinstance(item, dict):
            _fail("hcp_november_payload_packet_record_invalid")
        if str(item.get("disposition", "")).upper() not in WRITE_DISPOSITIONS:
            continue
        payload, evidence_digest = _resolve(
            evidence_root=evidence_root,
            locator=item.get("payload_locator"),
            expected_domain=str(item.get("domain")),
            expected_source_id=str(item.get("source_id")),
            expected_digest=str(item.get("source_digest")),
            expected_parents={
                (str(parent["domain"]), str(parent["source_id"]))
                for parent in item.get("parent_lineage", [])
                if isinstance(parent, dict)
            },
            cache=cache,
        )
        item["payload"] = payload
        item["payload_evidence_sha256"] = evidence_digest
    return result
