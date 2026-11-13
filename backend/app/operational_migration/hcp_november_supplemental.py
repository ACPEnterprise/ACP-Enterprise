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
import re
import stat
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _page_request(locator: str, *, domain: str) -> tuple[str, int]:
    relative = _locator_path(locator)
    pattern = rf"^{re.escape(COLLECTIONS[domain])}-page-(\d{{4}})\.json$"
    match = re.match(pattern, relative.name)
    if match is None or relative.parent.name != "acquisition":
        raise ValueError("supplemental locator is not an acquisition page locator")
    return COLLECTIONS[domain], int(match.group(1))


def _page_records(body: bytes, *, collection: str, page: int) -> list[dict[str, Any]]:
    value = json.loads(body)
    if not isinstance(value, dict) or not isinstance(value.get(collection), list):
        raise ValueError("HCP acquisition page is invalid")
    if value.get("page") != page:
        raise ValueError("HCP acquisition page number mismatch")
    if value.get("page_size") != 100:
        raise ValueError("HCP acquisition page size mismatch")
    records = value[collection]
    if not all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in records):
        raise ValueError("HCP acquisition page contains invalid identities")
    return records


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
    targets_by_domain: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        targets_by_domain[str(row["domain"])][str(row["source_id"])] = row
    for domain, targets in sorted(targets_by_domain.items()):
        collection = COLLECTIONS[domain]
        page = 1
        total_pages: int | None = None
        while total_pages is None or page <= total_pages:
            response = transport.get(
                f"/{collection}", query={"page": page, "page_size": 100}
            )
            if response.status != 200:
                raise ValueError(f"HCP GET failed for {domain} without exposing response body")
            document = json.loads(response.body)
            if not isinstance(document, dict) or not isinstance(document.get("total_pages"), int):
                raise ValueError("HCP acquisition pagination is invalid")
            total_pages = document["total_pages"]
            page_rows = _page_records(response.body, collection=collection, page=page)
            for record in page_rows:
                source_id = str(record["id"])
                row = targets.get(source_id)
                if row is None:
                    continue
                identity = (domain, source_id)
                if identity in seen:
                    raise ValueError("duplicate supplemental execution identity")
                seen.add(identity)
                actual_source_digest = _digest(record)
                if actual_source_digest != row["source_digest"]:
                    raise ValueError(f"source digest mismatch for {domain}:{source_id}")
                raw_body = (
                    json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    + "\n"
                ).encode()
                raw_name = "raw/{}-{}.json".format(
                    domain,
                    hashlib.sha256(source_id.encode("utf-8")).hexdigest(),
                )
                fetched.append(
                    {
                        "domain": domain,
                        "source_id": source_id,
                        "source_digest": actual_source_digest,
                        "parent_keys": row.get("parent_keys", row.get("parent_lineage", [])),
                        "payload": record,
                        "raw_body": raw_body,
                        "raw_artifact": raw_name,
                        "payload_locator": str(row["payload_locator"]),
                        "request": f"GET /{collection}?page={page}&page_size=100",
                    }
                )
            page += 1
        missing = sorted(set(targets) - {source_id for target_domain, source_id in seen if target_domain == domain})
        if missing:
            raise ValueError(f"HCP acquisition did not return all requested {domain} identities")

    by_locator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_seals: list[dict[str, Any]] = []
    raw_seen: set[str] = set()
    for item in fetched:
        raw_path = output_root / item["raw_artifact"]
        if item["raw_artifact"] not in raw_seen:
            _write_once(raw_path, item["raw_body"])
            raw_seals.append(
                {
                    "artifact": item["raw_artifact"],
                    "sha256": _sha256_bytes(item["raw_body"]),
                    "size_bytes": len(item["raw_body"]),
                    "request": item["request"],
                }
            )
            raw_seen.add(item["raw_artifact"])
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

    raw_seals.sort(key=lambda item: item["artifact"])
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
                "raw_artifact": item["raw_artifact"],
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


def build_paginated_current_state_supplemental(
    *,
    transport: GetOnlyTransport,
    inventory_path: Path,
    inventory_sha256: str,
    output_root: Path,
    source_packet_sha256: str,
    source_canonical_digest: str,
    fetched_at: str | None = None,
    expected_target_count: int = 1013,
    max_workers: int = 1,
) -> dict[str, Any]:
    """Scan only Estimate/Invoice collection pages and retain target records.

    Collection APIs return page peers, so peers are counted and discarded in
    memory.  Only identities present in the sealed inventory are written to the
    current-state custody set.  A digest mismatch is conservatively classified
    as ``BUSINESS_STATE_CHANGED`` for execution safety; without the historical
    body, this is not a claim that a particular business field changed.
    """
    inventory, rows = load_inventory(inventory_path, inventory_sha256)
    targets_by_domain: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        if row["domain"] in {"employee", "estimate", "invoice"}:
            targets_by_domain[str(row["domain"])][str(row["source_id"])] = row
    if sum(len(value) for value in targets_by_domain.values()) != expected_target_count:
        raise ValueError("paginated supplemental target population has an unexpected size")
    if output_root.exists():
        if output_root.is_symlink() or not output_root.is_dir():
            raise ValueError("current supplemental output root is unsafe")
    else:
        output_root.mkdir(mode=0o700, parents=True)
    _safe_mode(output_root, 0o700)

    fetched: list[dict[str, Any]] = []
    pages_requested: dict[str, int] = {}
    records_examined: dict[str, int] = {}
    unrelated_discarded: dict[str, int] = {}
    found: dict[str, set[str]] = defaultdict(set)
    duplicate_targets: set[tuple[str, str]] = set()
    for domain, targets in sorted(targets_by_domain.items()):
        collection = COLLECTIONS[domain]
        def fetch_page(page: int) -> tuple[int, bytes, dict[str, Any]]:
            response = transport.get(
                f"/{collection}", query={"page": page, "page_size": 100}
            )
            if response.status != 200:
                raise ValueError(f"HCP GET failed for {domain} without exposing response body")
            document = json.loads(response.body)
            if not isinstance(document, dict) or not isinstance(document.get("total_pages"), int):
                raise ValueError("HCP acquisition pagination is invalid")
            return page, response.body, document

        def consume_page(page: int, body: bytes) -> None:
            page_rows = _page_records(body, collection=collection, page=page)
            pages_requested[domain] = pages_requested.get(domain, 0) + 1
            records_examined[domain] = records_examined.get(domain, 0) + len(page_rows)
            for record in page_rows:
                source_id = str(record["id"])
                row = targets.get(source_id)
                if row is None:
                    unrelated_discarded[domain] = unrelated_discarded.get(domain, 0) + 1
                    continue
                identity = (domain, source_id)
                if identity in duplicate_targets or source_id in found[domain]:
                    duplicate_targets.add(identity)
                    continue
                found[domain].add(source_id)
                current_digest = _digest(record)
                classification = (
                    "EXACT_SEALED_MATCH"
                    if current_digest == row["source_digest"]
                    else "BUSINESS_STATE_CHANGED"
                )
                raw_body = (
                    json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    + "\n"
                ).encode()
                raw_artifact = "raw/{}-{}.json".format(
                    domain,
                    hashlib.sha256(source_id.encode("utf-8")).hexdigest(),
                )
                fetched.append(
                    {
                        "domain": domain,
                        "source_id": source_id,
                        "original_disposition": row["disposition"],
                        "original_source_digest": row["source_digest"],
                        "current_source_digest": current_digest,
                        "classification": classification,
                        "comparison_limitation": (
                            None
                            if classification == "EXACT_SEALED_MATCH"
                            else "historical November body unavailable; digest mismatch is conservatively held and is not field-level proof of business change"
                        ),
                        "payload_locator": row["payload_locator"],
                        "raw_body": raw_body,
                        "raw_artifact": raw_artifact,
                        "request": f"GET /{collection}?page={page}&page_size=100",
                        "acquired_at": fetched_at or _now(),
                    }
                )
        first_page, first_body, first_document = fetch_page(1)
        total_pages = first_document["total_pages"]
        consume_page(first_page, first_body)
        if found[domain] < set(targets):
            remaining_pages = range(2, total_pages + 1)
            if max_workers <= 1:
                for page in remaining_pages:
                    _, body, _ = fetch_page(page)
                    consume_page(page, body)
                    if found[domain] >= set(targets):
                        break
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(fetch_page, page): page for page in remaining_pages}
                    for future in as_completed(futures):
                        page, body, _ = future.result()
                        consume_page(page, body)
    missing = {
        domain: sorted(set(targets) - found[domain])
        for domain, targets in targets_by_domain.items()
        if set(targets) - found[domain]
    }
    if duplicate_targets:
        for domain, source_id in duplicate_targets:
            missing.setdefault(domain, []).append(source_id)
    raw_seals: list[dict[str, Any]] = []
    by_artifact: dict[str, dict[str, Any]] = {}
    for item in fetched:
        by_artifact[item["raw_artifact"]] = item
    for artifact, item in sorted(by_artifact.items()):
        path = output_root / artifact
        _write_once(path, item["raw_body"])
        raw_seals.append(
            {
                "artifact": artifact,
                "sha256": _sha256_bytes(item["raw_body"]),
                "size_bytes": len(item["raw_body"]),
                "domain": item["domain"],
                "source_id": item["source_id"],
                "request": item["request"],
            }
        )
    counts = Counter(item["classification"] for item in fetched)
    manifest: dict[str, Any] = {
        "contract": "hcp-november-supplemental-current-state-custody/v1",
        "http_method_allowlist": ["GET"],
        "inventory_sha256": inventory_sha256,
        "inventory_metadata": {
            key: inventory[key]
            for key in ("contract", "source_packet_sha256", "derived_packet_sha256")
            if key in inventory
        },
        "source_packet_sha256": source_packet_sha256,
        "source_canonical_digest": source_canonical_digest,
        "fetched_at": fetched_at or _now(),
        "scan": {
            "pages_requested": pages_requested,
            "records_examined": records_examined,
            "target_found": {domain: len(found[domain]) for domain in targets_by_domain},
            "target_missing": {domain: len(values) for domain, values in missing.items()},
            "unrelated_records_examined_and_discarded": unrelated_discarded,
            "stop_policy": "all_targets_found_or_pagination_exhausted",
        },
        "classification_counts": {
            name: counts.get(name, 0)
            for name in (
                "EXACT_SEALED_MATCH",
                "REPRESENTATION_DRIFT",
                "BUSINESS_STATE_CHANGED",
                "IDENTITY_CONFLICT",
                "MISSING_CURRENT",
            )
        },
        "records": [
            {
                key: value
                for key, value in item.items()
                if key not in {"raw_body"}
            }
            for item in sorted(fetched, key=lambda value: (value["domain"], value["source_id"]))
        ],
        "raw_artifacts": raw_seals,
        "missing": missing,
        "status": "COMPLETE" if not missing and not duplicate_targets else "INCOMPLETE",
    }
    manifest["digest"] = _digest(manifest)
    _write_once(
        output_root / "supplemental-current-state-manifest.json",
        (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(),
    )
    return manifest
