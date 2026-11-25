"""Deterministic CSV/XLSX header mapping preview without admission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

ALIASES: dict[str, tuple[str, ...]] = {
    "source_customer_id": ("customer id", "customer number", "account id"),
    "first_name": ("first name", "firstname", "given name"),
    "last_name": ("last name", "lastname", "surname"),
    "business_name": ("business name", "company", "company name"),
    "email": ("email", "email address", "primary email"),
    "phone": ("phone", "phone number", "mobile", "mobile phone"),
    "address_line_1": ("address", "street", "street address", "address 1"),
    "city": ("city", "town"),
    "state": ("state", "province", "region"),
    "postal_code": ("zip", "zip code", "postal code"),
}


def normalize_header(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


@dataclass(frozen=True, slots=True)
class FieldMapping:
    source_header: str
    target_field: str | None
    confidence: str
    reason: str


@dataclass(frozen=True, slots=True)
class MappingPreview:
    contract_version: str
    mappings: tuple[FieldMapping, ...]
    unused_headers: tuple[str, ...]
    exceptions: tuple[str, ...]
    mapping_digest: str
    admission_authorized: bool = False


def preview_mapping(headers: tuple[str, ...]) -> MappingPreview:
    if not headers or any(not header.strip() for header in headers):
        raise ValueError("nonempty source headers are required")
    normalized = tuple(normalize_header(header) for header in headers)
    if len(normalized) != len(set(normalized)):
        raise ValueError("duplicate normalized source headers are not allowed")

    reverse = {
        alias: target for target, aliases in ALIASES.items() for alias in aliases
    }
    mappings: list[FieldMapping] = []
    used_targets: set[str] = set()
    exceptions: list[str] = []
    for header, key in zip(headers, normalized, strict=True):
        target = reverse.get(key)
        if target is None:
            mappings.append(FieldMapping(header, None, "UNMAPPED", "preserved_unused"))
            continue
        if target in used_targets:
            mappings.append(
                FieldMapping(header, None, "AMBIGUOUS", "target_already_mapped")
            )
            exceptions.append(f"ambiguous target {target}: {header}")
            continue
        used_targets.add(target)
        mappings.append(FieldMapping(header, target, "EXACT_ALIAS", "approved_alias"))

    unused = tuple(item.source_header for item in mappings if item.target_field is None)
    canonical = [
        {
            "source": item.source_header,
            "target": item.target_field,
            "confidence": item.confidence,
            "reason": item.reason,
        }
        for item in mappings
    ]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return MappingPreview(
        "twelvehats-import-mapping-preview/v1",
        tuple(mappings),
        unused,
        tuple(exceptions),
        digest,
    )
