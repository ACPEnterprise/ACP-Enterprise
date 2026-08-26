from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .contracts import AcquisitionRequest, SourceAcquisitionProvider
from .evidence import ProtectedFilesystemEvidenceStore, RunState


@dataclass(frozen=True)
class AcquisitionResult:
    run_id: str
    state: RunState
    envelope_count: int
    manifest_sha256: str
    failure_code: str | None


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
        self.evidence_store.begin_run(
            run_id=run_id, snapshot=request.snapshot, company_name=company_name
        )
        count = 0
        try:
            async for envelope in self.provider.acquire(request):
                self.evidence_store.store_envelope(run_id=run_id, envelope=envelope)
                count += 1
        except Exception as error:  # noqa: BLE001 - seals arbitrary provider failures
            code = getattr(error, "code", "acquisition_failed")
            digest = self.evidence_store.finish_run(
                run_id=run_id,
                state=RunState.PARTIAL,
                ended_at=datetime.now(timezone.utc),
                failure_code=str(code),
            )
            return AcquisitionResult(
                run_id=run_id,
                state=RunState.PARTIAL,
                envelope_count=count,
                manifest_sha256=digest,
                failure_code=str(code),
            )
        digest = self.evidence_store.finish_run(
            run_id=run_id,
            state=RunState.COMPLETE,
            ended_at=datetime.now(timezone.utc),
        )
        return AcquisitionResult(
            run_id=run_id,
            state=RunState.COMPLETE,
            envelope_count=count,
            manifest_sha256=digest,
            failure_code=None,
        )
