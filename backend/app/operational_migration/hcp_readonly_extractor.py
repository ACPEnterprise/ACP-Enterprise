"""Credential-safe, GET-only Housecall Pro extraction qualification primitives."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .hcp_source_acquisition import (
    SnapshotIdentity,
    SourceEnvelope,
    SourceRelationship,
    seal_source_envelope,
)

APPROVED_API_BASE = "https://api.housecallpro.com"
REQUIRED_SECRET_KEYS = ("HOUSECALL_PRO_API_KEY", "HOUSECALL_PRO_API_BASE")


@dataclass(frozen=True)
class HcpReadOnlyConfig:
    api_base: str
    _api_key: str = field(repr=False)

    @property
    def authorization_header(self) -> str:
        return f"Token {self._api_key}"

    @classmethod
    def load(cls, path: Path) -> HcpReadOnlyConfig:
        if not path.is_file():
            raise ValueError("HCP secret file is missing")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ValueError("HCP secret file must have mode 0600")
        values: dict[str, str] = {}
        for line in path.read_text().splitlines():
            candidate = line.strip()
            if not candidate or candidate.startswith("#"):
                continue
            if "=" not in candidate:
                raise ValueError("HCP secret file contains a malformed line")
            key, value = candidate.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        if any(not values.get(key) for key in REQUIRED_SECRET_KEYS):
            raise ValueError("HCP secret configuration is incomplete")
        base = values["HOUSECALL_PRO_API_BASE"].rstrip("/")
        if base != APPROVED_API_BASE:
            raise ValueError("HCP API base is not approved")
        return cls(base, values["HOUSECALL_PRO_API_KEY"])


@dataclass(frozen=True)
class HcpResponse:
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)


class HcpReadOnlyTransport:
    """A deliberately GET-only transport; it has no mutation method surface."""

    def __init__(self, config: HcpReadOnlyConfig) -> None:
        self._config = config

    def get(
        self, path: str, *, query: Mapping[str, str | int] | None = None
    ) -> HcpResponse:
        parsed = urlparse(path)
        if not path.startswith("/") or parsed.scheme or parsed.netloc:
            raise ValueError("HCP request must use a relative API path")
        url = self._config.api_base + path
        if query:
            url += "?" + urlencode(query)
        request = Request(
            url,
            headers={
                "Authorization": self._config.authorization_header,
                "Accept": "application/json",
            },
            method="GET",
        )
        with urlopen(request, timeout=30) as response:
            return HcpResponse(response.status, response.read(), dict(response.headers))


class ProtectedEvidenceStore:
    def __init__(self, root: Path) -> None:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if stat.S_IMODE(root.stat().st_mode) != 0o700:
            raise ValueError("HCP evidence directory must have mode 0700")
        self.root = root

    def write_once(self, name: str, body: bytes) -> Path:
        if Path(name).name != name:
            raise ValueError("evidence name must be a basename")
        target = self.root / name
        with target.open("xb") as stream:
            stream.write(body)
        target.chmod(0o600)
        return target


class NativeIdentityRegistry:
    """Reject one native identity asserting two different source digests."""

    def __init__(self) -> None:
        self._digests: dict[tuple[str, str], str] = {}

    def accept(self, envelope: SourceEnvelope) -> bool:
        identity = (envelope.native_entity, envelope.native_id)
        existing = self._digests.get(identity)
        if existing is not None and existing != envelope.source_digest:
            raise ValueError("conflicting duplicate HCP native identity")
        self._digests[identity] = envelope.source_digest
        return existing is None


def qualify_records(
    *,
    native_entity: str,
    records: Iterable[Mapping[str, Any]],
    snapshot: SnapshotIdentity,
    status_field: str | None,
    created_field: str | None,
    updated_field: str | None,
    relationship_fields: Mapping[str, str],
) -> tuple[SourceEnvelope, ...]:
    """Seal exact records; only explicit native relationship IDs are projected."""
    registry = NativeIdentityRegistry()
    result: list[SourceEnvelope] = []
    for record in records:
        native_id = record.get("id")
        if not isinstance(native_id, str) or not native_id:
            raise ValueError(f"{native_entity} is missing a native ID")
        relationships = tuple(
            SourceRelationship(relation, parent_entity, str(record[field_name]))
            for relation, specification in sorted(relationship_fields.items())
            for parent_entity, field_name in (specification.split(":", 1),)
            if record.get(field_name) not in (None, "")
        )
        envelope = seal_source_envelope(
            native_entity=native_entity,
            native_id=native_id,
            raw_payload=record,
            snapshot=snapshot,
            source_status=str(record[status_field])
            if status_field and record.get(status_field) is not None
            else None,
            source_created_at=str(record[created_field])
            if created_field and record.get(created_field) is not None
            else None,
            source_updated_at=str(record[updated_field])
            if updated_field and record.get(updated_field) is not None
            else None,
            relationships=relationships,
            company_evidence={"company_id": record.get("company_id")}
            if record.get("company_id") is not None
            else None,
        )
        if registry.accept(envelope):
            result.append(envelope)
    return tuple(result)


def parse_collection(body: bytes, collection: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    document = json.loads(body)
    records = document.get(collection)
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError(f"invalid HCP {collection} collection")
    pagination = {
        key: document[key]
        for key in ("page", "page_size", "total_items", "total_pages")
        if isinstance(document.get(key), int)
    }
    if set(pagination) != {"page", "page_size", "total_items", "total_pages"}:
        raise ValueError("incomplete HCP pagination metadata")
    return records, pagination
