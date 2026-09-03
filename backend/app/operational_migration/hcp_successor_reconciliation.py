"""Fail-closed, PII-free reconciliation of legacy HCP and SOURCE.4 identities.

This module is deliberately read-only.  It compares source identity bindings already
present in a target database with the identities in the sealed SOURCE.4 plan.  Public
results contain counts and a canonical digest only; source and native identifiers never
leave the boundary.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

LEGACY_SOURCE_SYSTEM = "housecall_pro"
SOURCE4_SOURCE_SYSTEM = "housecall_pro_source4"
CONTRACT_VERSION = "hcp-preview-successor-reconciliation/v1"


class SuccessorDisposition(StrEnum):
    EXACT_SUCCESSOR = "exact_successor"
    AMBIGUOUS = "ambiguous"
    CONTROLLED_REPLACEMENT = "controlled_preview_replacement"
    REUSE_LEGACY_TARGET = "reuse_legacy_target"
    CREATE_NEW_TARGET = "create_new_target"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class IdentityBinding:
    domain: str
    source_system: str
    source_id: str
    target_id: str


@dataclass(frozen=True)
class SealedIdentity:
    domain: str
    source_id: str


@dataclass(frozen=True)
class SuccessorReconciliationReport:
    contract: str
    disposition_counts: dict[str, int]
    domain_counts: dict[str, dict[str, int]]
    safe_digest: str
    admission_allowed: bool


@dataclass(frozen=True)
class PrivateReuseEntry:
    domain: str
    source_id: str
    target_id: str


@dataclass(frozen=True)
class PrivateSuccessorManifest:
    """Protected runtime authority. Entries must never be serialized publicly."""

    entries: tuple[PrivateReuseEntry, ...]
    digest: str

    def __post_init__(self) -> None:
        expected = _private_manifest_digest(self.entries)
        if self.digest != expected:
            raise ValueError("private successor manifest digest mismatch")


@dataclass(frozen=True)
class SuccessorReconciliationV2:
    report: SuccessorReconciliationReport
    private_manifest: PrivateSuccessorManifest


def _private_manifest_digest(entries: tuple[PrivateReuseEntry, ...]) -> str:
    return hashlib.sha256(
        json.dumps(
            [item.__dict__ for item in entries],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def reconcile_successors_v2(
    *,
    current_bindings: Iterable[IdentityBinding],
    sealed_source4: Iterable[SealedIdentity],
) -> SuccessorReconciliationV2:
    """Split reusable targets from safe creation and conflicts.

    The public report contains counts only. The private manifest binds the raw
    provider/native mapping by digest and stays inside the protected runtime.
    """

    bindings = tuple(current_bindings)
    sealed = tuple(sealed_source4)
    if any(not item.domain or not item.source_id for item in sealed):
        raise ValueError("sealed identities must have domain and source identity")
    sealed_keys = [(item.domain, item.source_id) for item in sealed]
    if len(sealed_keys) != len(set(sealed_keys)):
        raise ValueError("sealed SOURCE.4 identity population contains duplicates")
    if any(
        item.source_system not in {LEGACY_SOURCE_SYSTEM, SOURCE4_SOURCE_SYSTEM}
        for item in bindings
    ):
        raise ValueError("unsupported source system in successor reconciliation")

    by_key: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    target_owners: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for item in bindings:
        if not item.domain or not item.source_id or not item.target_id:
            raise ValueError("identity binding is incomplete")
        by_key[(item.domain, item.source_system, item.source_id)].append(item.target_id)
        target_owners[(item.domain, item.source_system, item.target_id)].add(
            item.source_id
        )

    classified: list[tuple[str, SuccessorDisposition]] = []
    reuse: list[PrivateReuseEntry] = []
    for domain, source_id in sorted(sealed_keys):
        legacy = by_key.get((domain, LEGACY_SOURCE_SYSTEM, source_id), [])
        successor = by_key.get((domain, SOURCE4_SOURCE_SYSTEM, source_id), [])
        collision = any(
            len(target_owners[(domain, system, target)]) != 1
            for system, targets in (
                (LEGACY_SOURCE_SYSTEM, legacy),
                (SOURCE4_SOURCE_SYSTEM, successor),
            )
            for target in targets
        )
        if len(legacy) > 1 or len(successor) > 1 or collision:
            disposition = SuccessorDisposition.CONFLICT
        elif successor and legacy and successor[0] == legacy[0]:
            disposition = SuccessorDisposition.EXACT_SUCCESSOR
            reuse.append(PrivateReuseEntry(domain, source_id, successor[0]))
        elif successor:
            disposition = SuccessorDisposition.CONFLICT
        elif legacy:
            disposition = SuccessorDisposition.REUSE_LEGACY_TARGET
            reuse.append(PrivateReuseEntry(domain, source_id, legacy[0]))
        else:
            disposition = SuccessorDisposition.CREATE_NEW_TARGET
        classified.append((domain, disposition))

    sealed_set = set(sealed_keys)
    classified.extend(
        (item.domain, SuccessorDisposition.CONFLICT)
        for item in bindings
        if item.source_system == LEGACY_SOURCE_SYSTEM
        and (item.domain, item.source_id) not in sealed_set
    )
    totals = Counter(item.value for _, item in classified)
    domains: dict[str, Counter[str]] = defaultdict(Counter)
    for domain, disposition in classified:
        domains[domain][disposition.value] += 1
    public_keys = (
        SuccessorDisposition.EXACT_SUCCESSOR,
        SuccessorDisposition.REUSE_LEGACY_TARGET,
        SuccessorDisposition.CREATE_NEW_TARGET,
        SuccessorDisposition.CONFLICT,
    )
    counts = {key.value: totals[key.value] for key in public_keys}
    domain_counts = {
        domain: {key.value: values[key.value] for key in public_keys}
        for domain, values in sorted(domains.items())
    }
    public = {
        "contract": "hcp-preview-successor-reconciliation/v2",
        "disposition_counts": counts,
        "domain_counts": domain_counts,
    }
    public_digest = hashlib.sha256(
        json.dumps(public, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    ordered_reuse = tuple(sorted(reuse, key=lambda item: (item.domain, item.source_id)))
    manifest_digest = _private_manifest_digest(ordered_reuse)
    return SuccessorReconciliationV2(
        report=SuccessorReconciliationReport(
            contract="hcp-preview-successor-reconciliation/v2",
            disposition_counts=counts,
            domain_counts=domain_counts,
            safe_digest=public_digest,
            admission_allowed=counts[SuccessorDisposition.CONFLICT.value] == 0,
        ),
        private_manifest=PrivateSuccessorManifest(ordered_reuse, manifest_digest),
    )


def reconcile_successors(
    *,
    current_bindings: Iterable[IdentityBinding],
    sealed_source4: Iterable[SealedIdentity],
) -> SuccessorReconciliationReport:
    """Classify every sealed identity without exposing identifiers.

    An exact successor requires one legacy and one SOURCE.4 binding for the same
    provider identity and the same native target.  Any duplicate binding or target
    collision is ambiguous.  A sealed identity with no SOURCE.4 binding is eligible
    only for the sanctioned Preview replacement path.  Ambiguity fails admission.
    """

    bindings = tuple(current_bindings)
    sealed = tuple(sealed_source4)
    if any(not item.domain or not item.source_id for item in sealed):
        raise ValueError("sealed identities must have domain and source identity")
    sealed_keys = [(item.domain, item.source_id) for item in sealed]
    if len(sealed_keys) != len(set(sealed_keys)):
        raise ValueError("sealed SOURCE.4 identity population contains duplicates")
    if any(
        item.source_system not in {LEGACY_SOURCE_SYSTEM, SOURCE4_SOURCE_SYSTEM}
        for item in bindings
    ):
        raise ValueError("unsupported source system in successor reconciliation")

    by_key: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    source4_target_owners: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in bindings:
        if not item.domain or not item.source_id or not item.target_id:
            raise ValueError("identity binding is incomplete")
        by_key[(item.domain, item.source_system, item.source_id)].append(item.target_id)
        if item.source_system == SOURCE4_SOURCE_SYSTEM:
            source4_target_owners[(item.domain, item.target_id)].add(item.source_id)

    classified: list[tuple[str, SuccessorDisposition]] = []
    for domain, source_id in sorted(sealed_keys):
        legacy = by_key.get((domain, LEGACY_SOURCE_SYSTEM, source_id), [])
        successor = by_key.get((domain, SOURCE4_SOURCE_SYSTEM, source_id), [])
        duplicate = len(set(legacy)) != len(legacy) or len(set(successor)) != len(
            successor
        )
        target_collision = any(
            len(source4_target_owners[(domain, target_id)]) > 1
            for target_id in successor
        )
        if duplicate or target_collision or len(legacy) > 1 or len(successor) > 1:
            disposition = SuccessorDisposition.AMBIGUOUS
        elif successor and legacy and successor[0] == legacy[0]:
            disposition = SuccessorDisposition.EXACT_SUCCESSOR
        elif successor:
            # A SOURCE.4 row bound to a different/no legacy target cannot be replaced
            # automatically; doing so could create a second native truth.
            disposition = SuccessorDisposition.AMBIGUOUS
        else:
            disposition = SuccessorDisposition.CONTROLLED_REPLACEMENT
        classified.append((domain, disposition))

    sealed_key_set = set(sealed_keys)
    legacy_only = {
        (item.domain, item.source_id)
        for item in bindings
        if item.source_system == LEGACY_SOURCE_SYSTEM
        and (item.domain, item.source_id) not in sealed_key_set
    }
    # A legacy identity absent from the sealed authority cannot be silently ignored:
    # an operator must resolve whether it is obsolete pilot data or conflicting truth.
    classified.extend(
        (domain, SuccessorDisposition.AMBIGUOUS)
        for domain, _source_id in sorted(legacy_only)
    )

    totals = Counter(disposition.value for _, disposition in classified)
    domains: dict[str, Counter[str]] = defaultdict(Counter)
    for domain, disposition in classified:
        domains[domain][disposition.value] += 1
    legacy_keys = (
        SuccessorDisposition.EXACT_SUCCESSOR,
        SuccessorDisposition.AMBIGUOUS,
        SuccessorDisposition.CONTROLLED_REPLACEMENT,
    )
    disposition_counts = {key.value: totals.get(key.value, 0) for key in legacy_keys}
    domain_counts = {
        domain: {key.value: counts.get(key.value, 0) for key in legacy_keys}
        for domain, counts in sorted(domains.items())
    }
    safe_payload = {
        "contract": CONTRACT_VERSION,
        "disposition_counts": disposition_counts,
        "domain_counts": domain_counts,
    }
    safe_digest = hashlib.sha256(
        json.dumps(safe_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SuccessorReconciliationReport(
        contract=CONTRACT_VERSION,
        disposition_counts=disposition_counts,
        domain_counts=domain_counts,
        safe_digest=safe_digest,
        admission_allowed=totals[SuccessorDisposition.AMBIGUOUS.value] == 0,
    )
