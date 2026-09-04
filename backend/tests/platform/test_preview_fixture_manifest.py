from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.platform.onboarding.fixture_manifest import (
    FIXTURE_KEY,
    FixtureReleaseStep,
    FixtureResourceEvidence,
    PreviewFixtureManifestService,
)
from app.platform.onboarding.service import OnboardingConflictError


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class Session:
    def __init__(self, records, scalar_values=None):
        self.records = records
        self.scalar_values = list(scalar_values) if scalar_values is not None else None
        self.scalar_index = 0

    async def scalars(self, _statement):
        return ScalarResult(self.records)

    async def scalar(self, _statement):
        if self.scalar_values is not None:
            if not self.scalar_values:
                return None
            return self.scalar_values.pop(0)
        if not self.records:
            return None
        value = self.records[min(self.scalar_index, len(self.records) - 1)]
        self.scalar_index += 1
        return value

    def begin(self):
        return Transaction()

    def add(self, value):
        self.records.append(value)

    async def flush(self):
        return None


def service():
    return PreviewFixtureManifestService(
        configuration=SimpleNamespace(environment="preview")
    )


def context():
    return SimpleNamespace(
        company=SimpleNamespace(id=uuid4()), user=SimpleNamespace(id=uuid4())
    )


@pytest.mark.asyncio
async def test_register_binds_creation_authority_and_rejects_unsafe_digest():
    evidence = FixtureResourceEvidence(
        resource_key="synthetic-beta-job",
        resource_type="job",
        resource_id=uuid4(),
        authority_type="mutation_receipt",
        authority_id=uuid4(),
        authority_digest="a" * 64,
    )
    authority = SimpleNamespace(request_digest=evidence.authority_digest)
    session = Session([], scalar_values=[authority, None])
    record = await service().register(
        session,
        context=context(),
        fixture_key=FIXTURE_KEY,
        authorized=True,
        evidence=evidence,
    )
    assert record.resource_id == evidence.resource_id
    assert record.authority_id == evidence.authority_id
    with pytest.raises(OnboardingConflictError, match="digest is invalid"):
        await service().register(
            Session([], scalar_values=[]),
            context=context(),
            fixture_key=FIXTURE_KEY,
            authorized=True,
            evidence=FixtureResourceEvidence(
                **{**evidence.__dict__, "authority_digest": "unsafe"}
            ),
        )


@pytest.mark.asyncio
async def test_release_requires_complete_tenant_fixture_manifest():
    with pytest.raises(OnboardingConflictError, match="complete ownership manifest"):
        await service().release(
            Session([]),
            context=context(),
            fixture_key=FIXTURE_KEY,
            authorized=True,
            steps=(FixtureReleaseStep("synthetic-beta-job", AsyncMock()),),
        )


@pytest.mark.asyncio
async def test_release_calls_owner_then_removes_active_projection():
    release = AsyncMock()
    record = SimpleNamespace(
        id=uuid4(),
        resource_key="synthetic-beta-job",
        resource_type="job",
        active_projection=True,
        lifecycle="active",
        released_at=None,
    )
    await service().release(
        Session([record]),
        context=context(),
        fixture_key=FIXTURE_KEY,
        authorized=True,
        steps=(FixtureReleaseStep(record.resource_key, release),),
    )
    release.assert_awaited_once()
    assert record.active_projection is False
    assert record.lifecycle == "released"


@pytest.mark.asyncio
async def test_time_and_field_evidence_are_retained_not_deleted():
    records = [
        SimpleNamespace(
            id=uuid4(),
            resource_key=f"synthetic-beta-{kind}",
            resource_type=kind,
            active_projection=True,
            lifecycle="active",
            released_at=None,
        )
        for kind in ("timekeeping", "field_evidence")
    ]
    await service().release(
        Session(records),
        context=context(),
        fixture_key=FIXTURE_KEY,
        authorized=True,
        steps=tuple(FixtureReleaseStep(record.resource_key) for record in records),
    )
    assert all(record.active_projection is False for record in records)
    assert all(record.lifecycle == "audit_retained" for record in records)


@pytest.mark.asyncio
async def test_audit_evidence_rejects_deletion_callback():
    record = SimpleNamespace(
        id=uuid4(),
        resource_key="synthetic-beta-time",
        resource_type="timekeeping",
        active_projection=True,
    )
    with pytest.raises(OnboardingConflictError, match="cannot be deleted"):
        await service().release(
            Session([record]),
            context=context(),
            fixture_key=FIXTURE_KEY,
            authorized=True,
            steps=(FixtureReleaseStep(record.resource_key, AsyncMock()),),
        )
