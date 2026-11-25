"""Deterministic recovery validation for admissible HCP history packets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

REQUIRED_HCP_CSV_SHA256 = (
    "62e9e91c32a979d501f0ba9f812cb8b065c50783fe821874a65b911855923d4a"
)


@dataclass(frozen=True, slots=True)
class HcpJobDetail:
    source_job_id: str
    source_customer_id: str
    source_location_id: str
    summary: str | None
    description: str | None
    source_updated_at: str | None
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class HcpPhotograph:
    source_photo_id: str
    source_job_id: str
    media_digest: str
    captured_at: str | None
    caption: str | None


@dataclass(frozen=True, slots=True)
class HcpRecoveredPacket:
    contract_version: str
    source_csv_sha256: str
    jobs: tuple[HcpJobDetail, ...]
    photographs: tuple[HcpPhotograph, ...]
    held_exceptions: tuple[str, ...]
    packet_digest: str
    admissible: bool
    read_only: bool = True


def recover_hcp_packet(
    *,
    source_csv_sha256: str,
    jobs: tuple[HcpJobDetail, ...],
    photographs: tuple[HcpPhotograph, ...],
) -> HcpRecoveredPacket:
    if source_csv_sha256 != REQUIRED_HCP_CSV_SHA256:
        raise ValueError("HCP source CSV digest does not match approved custody")
    if len({job.source_job_id for job in jobs}) != len(jobs):
        raise ValueError("duplicate HCP Job source identity")
    known_jobs = {job.source_job_id for job in jobs}
    held: list[str] = []
    for job in jobs:
        if not all((job.source_job_id, job.source_customer_id, job.source_location_id)):
            held.append(f"job:{job.source_job_id or 'missing'}:missing_parent_identity")
        if len(job.evidence_digest) != 64:
            held.append(f"job:{job.source_job_id}:invalid_evidence_digest")
    for photo in photographs:
        if photo.source_job_id not in known_jobs:
            held.append(
                f"photo:{photo.source_photo_id}:missing_job:{photo.source_job_id}"
            )
        if len(photo.media_digest) != 64:
            held.append(f"photo:{photo.source_photo_id}:invalid_media_digest")
    canonical = {
        "source_csv_sha256": source_csv_sha256,
        "jobs": [
            {
                "id": job.source_job_id,
                "customer": job.source_customer_id,
                "location": job.source_location_id,
                "evidence": job.evidence_digest,
            }
            for job in sorted(jobs, key=lambda item: item.source_job_id)
        ],
        "photographs": [
            {
                "id": photo.source_photo_id,
                "job": photo.source_job_id,
                "media": photo.media_digest,
            }
            for photo in sorted(photographs, key=lambda item: item.source_photo_id)
        ],
        "held": sorted(held),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return HcpRecoveredPacket(
        "twelvehats-hcp-admissible-packet-recovery/v1",
        source_csv_sha256,
        tuple(sorted(jobs, key=lambda item: item.source_job_id)),
        tuple(sorted(photographs, key=lambda item: item.source_photo_id)),
        tuple(sorted(held)),
        digest,
        not held,
    )
