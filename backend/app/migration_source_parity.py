"""Provider-neutral source parity certificate contracts.

The certificate is deliberately independent of provider payloads.  A migration
lane supplies one disposition for every acquired provider identity; this module
then makes silent loss structurally impossible and produces the counts used by
owner acceptance.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import Enum


CONTRACT = "migration-source-parity-certificate/v1"


class ParityDisposition(str, Enum):
    CANONICAL = "CANONICAL"
    QUARANTINED = "QUARANTINED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class SourceDisposition:
    family: str
    provider_record_id: str
    disposition: ParityDisposition
    explanation: str
    canonical_id: str | None = None

    def __post_init__(self) -> None:
        if not self.family.strip() or not self.provider_record_id.strip():
            raise ValueError(
                "source family and provider record identity are required"
            )
        if not self.explanation.strip():
            raise ValueError("every source disposition requires an explanation")
        if self.disposition is ParityDisposition.CANONICAL and not self.canonical_id:
            raise ValueError("canonical dispositions require a canonical identity")
        if self.disposition is not ParityDisposition.CANONICAL and self.canonical_id:
            raise ValueError(
                "non-canonical dispositions cannot claim a canonical identity"
            )


@dataclass(frozen=True, slots=True)
class DomainParity:
    family: str
    source_count: int
    canonical_count: int
    quarantined: int
    provider_unavailable: int
    unexplained_delta: int

    @property
    def complete(self) -> bool:
        return self.unexplained_delta == 0


@dataclass(frozen=True, slots=True)
class SourceParityCertificate:
    contract: str
    provider: str
    source_as_of: str
    domains: tuple[DomainParity, ...]
    unexplained_delta: int
    complete: bool
    digest: str

    def verify(self) -> None:
        payload = asdict(self)
        observed = payload.pop("digest")
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if self.contract != CONTRACT or observed != expected:
            raise ValueError("source parity certificate digest mismatch")
        if self.unexplained_delta != sum(
            row.unexplained_delta for row in self.domains
        ):
            raise ValueError("source parity certificate total is inconsistent")
        if self.complete != (self.unexplained_delta == 0):
            raise ValueError("source parity completion claim is inconsistent")


def build_source_parity_certificate(
    *,
    provider: str,
    source_as_of: str,
    source_identities: dict[str, Iterable[str]],
    dispositions: Iterable[SourceDisposition],
    required_families: Iterable[str],
) -> SourceParityCertificate:
    """Reconcile exact provider identities; duplicates and omissions fail closed."""
    required = tuple(dict.fromkeys(item.strip() for item in required_families))
    if not provider.strip() or not source_as_of.strip() or not required or any(
        not item for item in required
    ):
        raise ValueError("provider, source as-of, and required families are required")
    unknown = set(source_identities) - set(required)
    if unknown:
        raise ValueError(f"unexpected source families: {sorted(unknown)}")

    source: dict[str, set[str]] = {}
    for family in required:
        values = tuple(
            str(value).strip() for value in source_identities.get(family, ())
        )
        if any(not value for value in values) or len(values) != len(set(values)):
            raise ValueError(f"{family} source identities are blank or duplicated")
        source[family] = set(values)

    indexed: dict[tuple[str, str], SourceDisposition] = {}
    for item in dispositions:
        key = (item.family, item.provider_record_id)
        if (
            item.family not in source
            or item.provider_record_id not in source[item.family]
        ):
            raise ValueError(
                f"disposition has no acquired source identity: {key}"
            )
        if key in indexed:
            raise ValueError(
                f"source identity has multiple current dispositions: {key}"
            )
        indexed[key] = item

    domains: list[DomainParity] = []
    for family in required:
        counts = Counter(
            indexed[(family, source_id)].disposition
            for source_id in source[family]
            if (family, source_id) in indexed
        )
        explained = sum(counts.values())
        domains.append(
            DomainParity(
                family=family,
                source_count=len(source[family]),
                canonical_count=counts[ParityDisposition.CANONICAL],
                quarantined=counts[ParityDisposition.QUARANTINED],
                provider_unavailable=counts[ParityDisposition.PROVIDER_UNAVAILABLE],
                unexplained_delta=len(source[family]) - explained,
            )
        )
    delta = sum(item.unexplained_delta for item in domains)
    payload = {
        "contract": CONTRACT,
        "provider": provider,
        "source_as_of": source_as_of,
        "domains": tuple(domains),
        "unexplained_delta": delta,
        "complete": delta == 0,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            default=asdict,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    result = SourceParityCertificate(**payload, digest=digest)
    result.verify()
    return result
