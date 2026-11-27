"""Build an exact, deterministic inventory of absent HCP payload bodies."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

GET_ONLY_DOMAINS = frozenset({"employee", "estimate", "invoice"})


@dataclass(frozen=True, slots=True)
class MissingPayloadInventory:
    contract: str
    provider_company_id: str
    source_packet_digest: str
    records: tuple[dict[str, Any], ...]
    unsupported: tuple[dict[str, Any], ...]
    counts: dict[str, int]
    digest: str
    http_method_allowlist: tuple[str, ...] = ("GET",)
    provider_writes_allowed: bool = False


def build_missing_payload_inventory(
    *,
    packet: Mapping[str, Any],
    available_payload_locators: Iterable[str],
) -> MissingPayloadInventory:
    provider_company_id = packet.get("provider_company_id")
    packet_digest = packet.get("digest")
    records = packet.get("records")
    if not isinstance(provider_company_id, str) or not provider_company_id:
        raise ValueError("packet provider Company binding is absent")
    if not isinstance(packet_digest, str) or len(packet_digest) != 64:
        raise ValueError("source packet digest is invalid")
    if not isinstance(records, list) or not all(
        isinstance(row, dict) for row in records
    ):
        raise TypeError("source packet records are invalid")

    available = set(available_payload_locators)
    missing: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        domain = record.get("domain")
        source_id = record.get("source_id")
        locator = record.get("payload_locator")
        source_digest = record.get("source_digest")
        if not isinstance(domain, str) or not isinstance(source_id, str):
            raise TypeError("source record identity is incomplete")
        identity = (domain, source_id)
        if identity in seen:
            raise ValueError("duplicate source record identity")
        seen.add(identity)
        if record.get("source_executable") is not True or locator in available:
            continue
        if not isinstance(locator, str) or "#" not in locator:
            reason = "payload_locator_unavailable"
        elif not isinstance(source_digest, str) or len(source_digest) != 64:
            reason = "source_digest_unavailable"
        else:
            reason = "payload_body_unavailable"
        entry = {
            "domain": domain,
            "source_id": source_id,
            "payload_locator": locator,
            "source_digest": source_digest,
            "parent_keys": record.get("parent_keys", []),
            "reason": reason,
        }
        if reason == "payload_body_unavailable" and domain in GET_ONLY_DOMAINS:
            missing.append(entry)
        else:
            entry["retrieval_disposition"] = "UNSUPPORTED_OR_INCOMPLETE"
            unsupported.append(entry)

    ordering = lambda row: (str(row["domain"]), str(row["source_id"]))
    missing.sort(key=ordering)
    unsupported.sort(key=ordering)
    counts = {
        "packet_records": len(records),
        "available_payloads": len(available),
        "get_only_retrievable": len(missing),
        "unsupported_or_incomplete": len(unsupported),
    }
    canonical = {
        "provider_company_id": provider_company_id,
        "source_packet_digest": packet_digest,
        "records": missing,
        "unsupported": unsupported,
        "counts": counts,
        "http_method_allowlist": ["GET"],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return MissingPayloadInventory(
        "hcp-missing-payload-inventory/v1",
        provider_company_id,
        packet_digest,
        tuple(missing),
        tuple(unsupported),
        counts,
        digest,
    )
