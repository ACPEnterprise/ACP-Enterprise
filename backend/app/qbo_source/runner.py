from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from .contracts import AcquisitionRequest, SourceAcquisitionProvider
from .evidence import (
    AcquisitionFailureEvidence,
    ProtectedFilesystemEvidenceStore,
    RunState,
)

CATALOG_VERSION = "qbo-production-acquisition-catalog/v2"

# Financial source families remain required. Provider-dependent dimensions and
# payroll-adjacent query surfaces are explicit rather than silently skipped.
OPTIONAL_PROVIDER_DEPENDENT = frozenset(
    {
        "credit_card_payment",
        "tax_payment",
        "tax_agency",
        "class",
        "department",
        "employee",
        "time_activity",
    }
)


def _failure_evidence(run_id: str, error: Exception) -> AcquisitionFailureEvidence:
    code = str(getattr(error, "code", "acquisition_failed"))
    status = getattr(error, "provider_status", None)
    kind = getattr(error, "entity_kind", None)
    page = getattr(error, "page", None)
    if code == "api_authorization_rejected":
        classification, retryable = "AUTHORIZATION_FAILURE", False
    elif status == 429:
        classification, retryable = "RATE_LIMITED", True
    elif code == "api_retry_exhausted":
        classification, retryable = "TEMPORARY_PROVIDER_FAILURE", True
    elif code in {
        "query_response_missing",
        "query_rows_invalid",
        "authoritative_transaction_date_invalid",
        "authoritative_transaction_date_missing",
        "source_blob_unavailable",
        "source_blob_invalid",
        "source_envelope_unavailable",
    }:
        classification, retryable = "DATA_VALIDATION_FAILURE", False
    elif code in {"duplicate_native_id", "native_id_missing"}:
        classification, retryable = "PAGINATION_FAILURE", False
    elif code == "api_request_rejected":
        classification, retryable = "UNKNOWN_PROVIDER_REJECTION", False
    else:
        classification, retryable = "PROVIDER_UNCERTAIN", False
    status_class = (
        "not_available"
        if status is None
        else "client_rejection"
        if 400 <= status < 500
        else "provider_failure"
    )
    requirement = (
        "OPTIONAL_PROVIDER_DEPENDENT"
        if kind in OPTIONAL_PROVIDER_DEPENDENT
        else "REQUIRED_FOR_COMPLETE_ACQUISITION"
    )
    occurred = datetime.now(timezone.utc).isoformat()
    correlation = hashlib.sha256(
        f"{run_id}:{kind}:{page}:{code}:{status}:{occurred}".encode()
    ).hexdigest()
    return AcquisitionFailureEvidence(
        schema_version="qbo-acquisition-failure/v1",
        catalog_version=CATALOG_VERSION,
        acquisition_generation=run_id,
        entity_kind=kind,
        query_classification="paginated_query" if page is not None else "direct_query",
        page=page,
        provider_status_classification=status_class,
        error_classification=classification,
        retryable=retryable,
        catalog_requirement=requirement,
        occurred_at=occurred,
        correlation_id=correlation,
    )


@dataclass(frozen=True)
class AcquisitionResult:
    run_id: str
    state: RunState
    envelope_count: int
    manifest_sha256: str
    failure_code: str | None
    bounded_snapshot: dict[str, object] | None = None


class AcquisitionRunner:
    def __init__(
        self,
        *,
        provider: SourceAcquisitionProvider,
        evidence_store: ProtectedFilesystemEvidenceStore,
    ) -> None:
        self.provider = provider
        self.evidence_store = evidence_store

    async def run(
        self,
        *,
        run_id: str,
        request: AcquisitionRequest,
        company_name: str,
    ) -> AcquisitionResult:
        acquisition_run = self.evidence_store.begin_run(
            run_id=run_id, snapshot=request.snapshot, company_name=company_name
        )
        if acquisition_run.state is not RunState.IN_PROGRESS:
            existing = self.evidence_store.terminal_run_summary(run_id=run_id)
            existing_state = existing["state"]
            if not isinstance(existing_state, RunState):
                raise TypeError("stored run state is invalid")
            existing_count = existing["envelope_count"]
            if not isinstance(existing_count, int):
                raise TypeError("stored envelope count is invalid")
            return AcquisitionResult(
                run_id=run_id,
                state=existing_state,
                envelope_count=existing_count,
                manifest_sha256=str(existing["manifest_sha256"]),
                failure_code=(
                    str(existing["failure_code"])
                    if existing["failure_code"] is not None
                    else None
                ),
                bounded_snapshot=self.evidence_store.bounded_snapshot_summary(
                    run_id=run_id
                ),
            )
        count = 0
        try:
            async for envelope in self.provider.acquire(request):
                self.evidence_store.store_envelope(run_id=run_id, envelope=envelope)
                count += 1
        except Exception as error:  # noqa: BLE001 - seals arbitrary provider failures
            code = getattr(error, "code", "acquisition_failed")
            failure_evidence = _failure_evidence(run_id, error)
            digest = self.evidence_store.finish_run(
                run_id=run_id,
                state=RunState.PARTIAL,
                ended_at=datetime.now(timezone.utc),
                failure_code=str(code),
                failure_evidence=failure_evidence,
            )
            return AcquisitionResult(
                run_id=run_id,
                state=RunState.PARTIAL,
                envelope_count=count,
                manifest_sha256=digest,
                failure_code=str(code),
            )
        try:
            digest = self.evidence_store.finish_run(
                run_id=run_id,
                state=RunState.COMPLETE,
                ended_at=datetime.now(timezone.utc),
            )
        except Exception as error:  # noqa: BLE001 - seals projection failures
            code = getattr(error, "code", "acquisition_finalization_failed")
            digest = self.evidence_store.finish_run(
                run_id=run_id,
                state=RunState.PARTIAL,
                ended_at=datetime.now(timezone.utc),
                failure_code=str(code),
                failure_evidence=_failure_evidence(run_id, error),
            )
            return AcquisitionResult(
                run_id=run_id,
                state=RunState.PARTIAL,
                envelope_count=count,
                manifest_sha256=digest,
                failure_code=str(code),
            )
        return AcquisitionResult(
            run_id=run_id,
            state=RunState.COMPLETE,
            envelope_count=count,
            manifest_sha256=digest,
            failure_code=None,
            bounded_snapshot=self.evidence_store.bounded_snapshot_summary(
                run_id=run_id
            ),
        )
