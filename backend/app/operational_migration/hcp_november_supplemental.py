"""Exact-identity, GET-only acquisition for missing November payload bodies.

The qualified November packets remain immutable.  This module only consumes a
private missing-identity inventory and writes a supplemental custody set.  It
has no mutation-capable HCP client and refuses to fetch anything outside the
inventory.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

COLLECTIONS = {
    "employee": "employees",
    "estimate": "estimates",
    "invoice": "invoices",
}


class GetResponse(Protocol):
    status: int
    body: bytes


class GetOnlyTransport(Protocol):
    def get(self, path: str, *, query: Mapping[str, str | int] | None = None) -> GetResponse:
        ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object) -> str:
    return _sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    )


def _safe_mode(path: Path, mode: int) -> None:
    path.chmod(mode)
    if stat.S_IMODE(path.stat().st_mode) != mode:
        raise ValueError(f"unable to set protected mode on {path}")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def load_inventory(path: Path, expected_sha256: str) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("missing payload inventory is absent or is a symlink")
    actual = _sha256_bytes(path.read_bytes())
    if actual != expected_sha256:
        raise ValueError("missing payload inventory SHA-256 mismatch")
    value = _read_json(path)
    if not isinstance(value, dict):
        raise ValueError("missing payload inventory must be an object")
    raw = value.get("records", value.get("missing", value.get("inventory")))
    if not isinstance(raw, list) or not all(isinstance(row, dict) for row in raw):
        raise ValueError("missing payload inventory records are invalid")
    rows: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for row in raw:
        domain = row.get("domain")
        source_id = row.get("source_id")
        locator = row.get("payload_locator")
        source_digest = row.get("source_digest")
        if (
            domain not in COLLECTIONS
            or not isinstance(source_id, str)
            or not source_id
            or not isinstance(locator, str)
            or "#" not in locator
            or not isinstance(source_digest, str)
            or len(source_digest) != 64
        ):
            raise ValueError("missing payload inventory row is incomplete")
        identity = (domain, source_id)
        if identity in identities:
            raise ValueError("missing payload inventory contains duplicate identity")
        identities.add(identity)
        rows.append(dict(row))
    return value, tuple(rows)


def _locator_path(locator: str) -> Path:
    relative, selector = locator.split("#", 1)
    if not relative or not selector or ":" not in selector:
        raise ValueError("invalid payload locator")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("payload locator escapes acquisition root")
    return path


def _response_record(body: bytes, *, domain: str, source_id: str) -> dict[str, Any]:
    value = json.loads(body)
    if isinstance(value, dict) and value.get("id") == source_id:
        return value
    candidates: list[dict[str, Any]] = []
    if isinstance(value, dict):
        names = (domain, COLLECTIONS[domain], "record")
        for name in names:
            candidate = value.get(name)
            if isinstance(candidate, dict):
                candidates.append(candidate)
            elif isinstance(candidate, list):
                candidates.extend(item for item in candidate if isinstance(item, dict))
    matches = [candidate for candidate in candidates if candidate.get("id") == source_id]
    if len(matches) != 1:
        raise ValueError(f"HCP response did not contain exactly one requested {domain}")
    return matches[0]


def _write_once(path: Path, body: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _safe_mode(path.parent, 0o700)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != body:
            raise ValueError(f"conflicting supplemental artifact: {path}")
        return
    with path.open("xb") as stream:
        stream.write(body)
    _safe_mode(path, 0o600)


def build_supplemental(
    *,
    transport: GetOnlyTransport,
    inventory_path: Path,
    inventory_sha256: str,
    output_root: Path,
    source_packet_sha256: str,
    source_canonical_digest: str,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    inventory, rows = load_inventory(inventory_path, inventory_sha256)
    if output_root.exists():
        if output_root.is_symlink() or not output_root.is_dir():
            raise ValueError("supplemental output root is unsafe")
    else:
        output_root.mkdir(mode=0o700, parents=True)
    _safe_mode(output_root, 0o700)

    # Fetch and validate all bodies before writing any artifact.  A failed run
    # therefore cannot leave a partially sealed supplemental set.
    fetched: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in sorted(rows, key=lambda item: (str(item["domain"]), str(item["source_id"]))):
        domain = str(row["domain"])
        source_id = str(row["source_id"])
        identity = (domain, source_id)
        if identity in seen:
            raise ValueError("duplicate supplemental execution identity")
        seen.add(identity)
        response = transport.get(f"/{COLLECTIONS[domain]}/{source_id}")
        if response.status != 200:
            raise ValueError(f"HCP GET failed for {domain} without exposing response body")
        record = _response_record(response.body, domain=domain, source_id=source_id)
        actual_source_digest = _digest(record)
        if actual_source_digest != row["source_digest"]:
            raise ValueError(f"source digest mismatch for {domain}:{source_id}")
        locator = str(row["payload_locator"])
        _locator_path(locator)
        fetched.append(
            {
                "domain": domain,
                "source_id": source_id,
                "source_digest": actual_source_digest,
                "parent_keys": row.get("parent_keys", row.get("parent_lineage", [])),
                "payload": record,
                "raw_body": response.body,
                "payload_locator": locator,
                "request": f"GET /{COLLECTIONS[domain]}/{source_id}",
            }
        )

    by_locator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_seals: list[dict[str, Any]] = []
    for item in fetched:
        raw_name = "supplemental-raw-{}.json".format(
            hashlib.sha256(f"{item['domain']}:{item['source_id']}".encode()).hexdigest()
        )
        raw_path = output_root / "raw" / raw_name
        _write_once(raw_path, item["raw_body"])
        raw_seals.append(
            {
                "artifact": str(raw_path.relative_to(output_root)),
                "domain": item["domain"],
                "source_id": item["source_id"],
                "sha256": _sha256_bytes(item["raw_body"]),
                "size_bytes": len(item["raw_body"]),
                "request": item["request"],
            }
        )
        by_locator[item["payload_locator"]].append(
            {
                "domain": item["domain"],
                "source_id": item["source_id"],
                "source_digest": item["source_digest"],
                "parent_keys": item["parent_keys"],
                "payload": item["payload"],
            }
        )

    for locator, records in sorted(by_locator.items()):
        relative = _locator_path(locator)
        body = (json.dumps({"records": records}, sort_keys=True, indent=2) + "\n").encode()
        _write_once(output_root / relative, body)

    raw_seals.sort(key=lambda item: (item["domain"], item["source_id"]))
    fetched_at = fetched_at or _now()
    manifest: dict[str, Any] = {
        "contract": "hcp-november-supplemental-custody/v1",
        "http_method_allowlist": ["GET"],
        "inventory_sha256": inventory_sha256,
        "inventory_count": len(rows),
        "source_packet_sha256": source_packet_sha256,
        "source_canonical_digest": source_canonical_digest,
        "fetched_at": fetched_at,
        "records": [
            {
                "domain": item["domain"],
                "source_id": item["source_id"],
                "source_digest": item["source_digest"],
                "payload_locator": item["payload_locator"],
            }
            for item in fetched
        ],
        "raw_artifacts": raw_seals,
        "status": "COMPLETE",
    }
    manifest["digest"] = _digest(manifest)
    manifest_path = output_root / "supplemental-custody-manifest.json"
    _write_once(manifest_path, (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    # Inventory metadata is retained as a receipt, not copied as authority.
    receipt = {
        "contract": "hcp-november-supplemental-custody-receipt/v1",
        "inventory_sha256": inventory_sha256,
        "inventory_metadata": {
            key: inventory[key]
            for key in ("bundle_sha256", "policy_digest", "reconciliation_digest")
            if key in inventory
        },
        "supplemental_manifest_digest": manifest["digest"],
        "count": len(fetched),
        "status": "COMPLETE",
    }
    _write_once(output_root / "supplemental-custody-receipt.json", (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
    return manifest
