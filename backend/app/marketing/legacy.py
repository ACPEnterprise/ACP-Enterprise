import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .contracts import AttributionResolution


@dataclass(frozen=True, slots=True)
class LegacyCustomerSourceEvidence:
    customer_id: UUID
    original_value: str | None
    observed_at: datetime
    evidence_digest: str
    idempotency_key: str
    resolution: AttributionResolution = AttributionResolution.UNKNOWN
    evidence_kind: str = "legacy_customer_source"


def legacy_customer_source_evidence(
    *, customer_id: UUID, original_value: str | None, observed_at: datetime
) -> LegacyCustomerSourceEvidence:
    value = (
        original_value.strip() if original_value and original_value.strip() else None
    )
    payload = {
        "customer_id": str(customer_id),
        "original_value": value,
        "observed_at": observed_at.isoformat(),
        "provenance": "customers.source",
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return LegacyCustomerSourceEvidence(
        customer_id=customer_id,
        original_value=value,
        observed_at=observed_at,
        evidence_digest=digest,
        idempotency_key=f"legacy-customer-source:{customer_id}:{digest}",
    )
