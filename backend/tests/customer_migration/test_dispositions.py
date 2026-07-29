import hashlib
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from app.customer_migration.disposition_contracts import (
    DispositionApplicationReceipt,
    DispositionCode,
    DispositionDecision,
    DispositionKind,
    DispositionReplayApplication,
    DispositionSourceIdentity,
    OwnerDisposition,
    disposition_identity,
)
from app.customer_migration.disposition_service import (
    ApproveDisposition,
    DispositionEffectPort,
    DispositionOwnershipError,
    DispositionReplayService,
    DispositionVersionConflictError,
    OwnerApprovalRequiredError,
    OwnerDispositionService,
)
from app.platform.permissions.authorization import AuthorizationContext

COMPANY_ID = UUID("10000000-0000-0000-0000-000000000001")
OTHER_COMPANY_ID = UUID("20000000-0000-0000-0000-000000000002")
OWNER_ID = UUID("30000000-0000-0000-0000-000000000003")
ARTIFACT_SHA = "a" * 64
EVIDENCE_SHA = "b" * 64
APPROVAL_SHA = "c" * 64
NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


def context(company_id: UUID = COMPANY_ID) -> AuthorizationContext:
    value = SimpleNamespace(
        user=SimpleNamespace(id=OWNER_ID),
        company=SimpleNamespace(id=company_id),
        membership=SimpleNamespace(company_id=company_id),
    )
    return cast(AuthorizationContext, value)


def source(
    *,
    company_id: UUID = COMPANY_ID,
    identity_seed: str = "1",
) -> DispositionSourceIdentity:
    return DispositionSourceIdentity(
        company_id=company_id,
        source_artifact_sha256=ARTIFACT_SHA,
        source_identity_sha256=identity_seed * 64,
        adapter_version="4654bc74bca2d3bd5e924a5afe9f0063d21464b5",
        schema_version="housecall_pro_customer_451_v1",
        source_row_number=2,
    )


class InMemoryDispositionRepository:
    def __init__(self) -> None:
        self.records: list[OwnerDisposition] = []

    async def get_latest(
        self, *, company_id: UUID, disposition_identity: str
    ) -> OwnerDisposition | None:
        matching = [
            record
            for record in self.records
            if record.source.company_id == company_id
            and record.disposition_identity == disposition_identity
        ]
        return max(matching, key=lambda item: item.version, default=None)

    async def append(
        self,
        disposition: OwnerDisposition,
        *,
        expected_previous_version: int,
    ) -> OwnerDisposition:
        latest = await self.get_latest(
            company_id=disposition.source.company_id,
            disposition_identity=disposition.disposition_identity,
        )
        current = latest.version if latest else 0
        if current != expected_previous_version:
            raise DispositionVersionConflictError("concurrent disposition change")
        if disposition in self.records:
            return disposition
        self.records.append(disposition)
        return disposition

    async def list_for_replay(
        self, *, company_id: UUID, source_artifact_sha256: str
    ) -> tuple[OwnerDisposition, ...]:
        return tuple(
            reversed(
                [
                    record
                    for record in self.records
                    if record.source.company_id == company_id
                    and record.source.source_artifact_sha256 == source_artifact_sha256
                ]
            )
        )


class ApprovalVerifier:
    def __init__(self, approved: bool = True) -> None:
        self.approved = approved

    async def is_explicit_owner_approval(
        self,
        *,
        context: AuthorizationContext,
        approval_request_id: UUID,
        approval_evidence_sha256: str,
    ) -> bool:
        del context, approval_request_id, approval_evidence_sha256
        return self.approved


def command(
    *,
    source_link: DispositionSourceIdentity,
    kind: DispositionKind,
    code: DispositionCode,
    expected_previous_version: int = 0,
    request_number: int = 1,
) -> ApproveDisposition:
    return ApproveDisposition(
        source=source_link,
        subject_key=f"subject:{kind.value}",
        decision=DispositionDecision(
            kind=kind,
            code=code,
            decision_evidence_sha256=EVIDENCE_SHA,
        ),
        expected_previous_version=expected_previous_version,
        approved_by_user_id=OWNER_ID,
        approved_at=NOW,
        reason_code="owner_reviewed_source_evidence",
        approval_request_id=UUID(int=request_number),
        approval_evidence_sha256=APPROVAL_SHA,
    )


@pytest.mark.asyncio
async def test_supports_all_disposition_kinds_only_with_explicit_owner_approval() -> (
    None
):
    repository = InMemoryDispositionRepository()
    service = OwnerDispositionService(
        repository=repository,
        owner_approval=ApprovalVerifier(),
    )
    decisions = (
        (
            DispositionKind.MISSING_CUSTOMER_TYPE,
            DispositionCode.OWNER_PROVIDED_RESIDENTIAL,
        ),
        (
            DispositionKind.CONTACT_NAME_RESOLUTION,
            DispositionCode.ACCEPT_CUSTOMER_WITHOUT_CONTACT,
        ),
        (
            DispositionKind.DUPLICATE_CLUSTER_RESOLUTION,
            DispositionCode.KEEP_SEPARATE,
        ),
        (
            DispositionKind.ADDRESS_EXCEPTION_DISPOSITION,
            DispositionCode.SKIP_INCOMPLETE_ADDRESS,
        ),
    )

    records = []
    for index, (kind, code) in enumerate(decisions, start=1):
        records.append(
            await service.approve(
                context=context(),
                command=command(
                    source_link=source(identity_seed=str(index)),
                    kind=kind,
                    code=code,
                    request_number=index,
                ),
                disposition_id=UUID(int=100 + index),
            )
        )

    assert [record.decision.kind for record in records] == [
        item[0] for item in decisions
    ]
    assert all(record.audit.approved_by_user_id == OWNER_ID for record in records)
    assert all(record.version == 1 for record in records)

    denied = OwnerDispositionService(
        repository=repository,
        owner_approval=ApprovalVerifier(approved=False),
    )
    with pytest.raises(OwnerApprovalRequiredError):
        await denied.approve(
            context=context(),
            command=command(
                source_link=source(identity_seed="5"),
                kind=DispositionKind.MISSING_CUSTOMER_TYPE,
                code=DispositionCode.REQUIRES_SOURCE_CORRECTION,
            ),
        )


@pytest.mark.asyncio
async def test_versioned_identity_is_stable_and_records_are_immutable() -> None:
    repository = InMemoryDispositionRepository()
    service = OwnerDispositionService(
        repository=repository,
        owner_approval=ApprovalVerifier(),
    )
    first = await service.approve(
        context=context(),
        command=command(
            source_link=source(),
            kind=DispositionKind.MISSING_CUSTOMER_TYPE,
            code=DispositionCode.REQUIRES_SOURCE_CORRECTION,
        ),
        disposition_id=UUID(int=201),
    )
    second = await service.approve(
        context=context(),
        command=command(
            source_link=source(),
            kind=DispositionKind.MISSING_CUSTOMER_TYPE,
            code=DispositionCode.OWNER_PROVIDED_COMMERCIAL,
            expected_previous_version=1,
            request_number=2,
        ),
        disposition_id=UUID(int=202),
    )

    assert first.disposition_identity == second.disposition_identity
    assert second.version == 2
    assert second.prior_disposition_id == first.id
    assert first.record_sha256 != second.record_sha256
    with pytest.raises(FrozenInstanceError):
        first.version = 3  # type: ignore[misc]
    with pytest.raises(DispositionVersionConflictError):
        await service.approve(
            context=context(),
            command=command(
                source_link=source(),
                kind=DispositionKind.MISSING_CUSTOMER_TYPE,
                code=DispositionCode.PERMANENT_REJECTION,
                expected_previous_version=0,
                request_number=3,
            ),
        )


@pytest.mark.asyncio
async def test_company_ownership_is_enforced_for_approval_and_replay() -> None:
    repository = InMemoryDispositionRepository()
    service = OwnerDispositionService(
        repository=repository,
        owner_approval=ApprovalVerifier(),
    )

    with pytest.raises(DispositionOwnershipError):
        await service.approve(
            context=context(),
            command=command(
                source_link=source(company_id=OTHER_COMPANY_ID),
                kind=DispositionKind.CONTACT_NAME_RESOLUTION,
                code=DispositionCode.REQUIRES_SOURCE_CORRECTION,
            ),
        )

    await service.approve(
        context=context(),
        command=command(
            source_link=source(),
            kind=DispositionKind.CONTACT_NAME_RESOLUTION,
            code=DispositionCode.REQUIRES_SOURCE_CORRECTION,
        ),
        disposition_id=UUID(int=301),
    )
    plan = await service.replay_plan(
        context=context(), source_artifact_sha256=ARTIFACT_SHA
    )
    assert plan.company_id == COMPANY_ID


@pytest.mark.asyncio
async def test_replay_is_deterministic_latest_only_and_ordered() -> None:
    repository = InMemoryDispositionRepository()
    service = OwnerDispositionService(
        repository=repository,
        owner_approval=ApprovalVerifier(),
    )
    for index, (seed, kind, code) in enumerate(
        (
            (
                "3",
                DispositionKind.ADDRESS_EXCEPTION_DISPOSITION,
                DispositionCode.SKIP_INCOMPLETE_ADDRESS,
            ),
            (
                "1",
                DispositionKind.DUPLICATE_CLUSTER_RESOLUTION,
                DispositionCode.KEEP_SEPARATE,
            ),
            (
                "2",
                DispositionKind.CONTACT_NAME_RESOLUTION,
                DispositionCode.ACCEPT_CUSTOMER_WITHOUT_CONTACT,
            ),
        ),
        start=1,
    ):
        await service.approve(
            context=context(),
            command=command(
                source_link=source(identity_seed=seed),
                kind=kind,
                code=code,
                request_number=index,
            ),
            disposition_id=UUID(int=400 + index),
        )

    first = await service.replay_plan(
        context=context(), source_artifact_sha256=ARTIFACT_SHA
    )
    second = await service.replay_plan(
        context=context(), source_artifact_sha256=ARTIFACT_SHA
    )

    assert first == second
    assert first.replay_sha256 == second.replay_sha256
    assert [item.ordinal for item in first.applications] == [0, 1, 2]
    assert [
        item.disposition.source.source_identity_sha256 for item in first.applications
    ] == [
        "1" * 64,
        "2" * 64,
        "3" * 64,
    ]


class InMemoryLedger:
    def __init__(self) -> None:
        self.receipts: dict[str, DispositionApplicationReceipt] = {}

    async def get_receipt(
        self, *, company_id: UUID, application_id: str
    ) -> DispositionApplicationReceipt | None:
        receipt = self.receipts.get(application_id)
        return receipt if receipt is None or receipt.company_id == company_id else None

    async def record_receipt(
        self, receipt: DispositionApplicationReceipt
    ) -> DispositionApplicationReceipt:
        existing = self.receipts.get(receipt.application_id)
        if existing is not None and existing != receipt:
            raise ValueError("receipt conflict")
        self.receipts[receipt.application_id] = receipt
        return receipt


class CountingEffectPort(DispositionEffectPort):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def apply(self, application: DispositionReplayApplication) -> str:
        self.calls.append(application.application_id)
        return hashlib.sha256(application.application_id.encode()).hexdigest()


@pytest.mark.asyncio
async def test_application_contract_is_idempotent() -> None:
    repository = InMemoryDispositionRepository()
    disposition_service = OwnerDispositionService(
        repository=repository,
        owner_approval=ApprovalVerifier(),
    )
    await disposition_service.approve(
        context=context(),
        command=command(
            source_link=source(),
            kind=DispositionKind.DUPLICATE_CLUSTER_RESOLUTION,
            code=DispositionCode.KEEP_SEPARATE,
        ),
        disposition_id=UUID(int=501),
    )
    plan = await disposition_service.replay_plan(
        context=context(), source_artifact_sha256=ARTIFACT_SHA
    )
    ledger = InMemoryLedger()
    effects = CountingEffectPort()
    replay = DispositionReplayService(ledger=ledger, effect_port=effects)

    first = await replay.apply(context=context(), plan=plan, applied_at=NOW)
    second = await replay.apply(context=context(), plan=plan, applied_at=NOW)

    assert [item.reused for item in first] == [False]
    assert [item.reused for item in second] == [True]
    assert len(effects.calls) == 1
    assert first[0].receipt == second[0].receipt


def test_decisions_fail_closed_for_cross_kind_or_inferred_values() -> None:
    with pytest.raises(ValueError, match="not valid"):
        DispositionDecision(
            kind=DispositionKind.MISSING_CUSTOMER_TYPE,
            code=DispositionCode.ACCEPT_CUSTOMER_WITHOUT_CONTACT,
            decision_evidence_sha256=EVIDENCE_SHA,
        )
    with pytest.raises(ValueError, match="PII-safe"):
        disposition_identity(
            source=source(),
            kind=DispositionKind.ADDRESS_EXCEPTION_DISPOSITION,
            subject_key="contains spaces",
        )
