import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customer_migration.native_location_identity import (
    AcceptedLocationIdentity,
    LocationIdentityClassification,
    NativeLocationObservation,
    preserve_pilot_boundary,
    reconcile_native_locations,
    scoped_identity,
)
from app.customer_migration.native_location_matching import (
    AcquiredNativeLocation,
    match_native_location,
)
from app.customer_migration.native_location_reconciliation import (
    ReconciliationWrite,
    native_location_reconciliation_repository,
)
from app.customer_migration.native_location_repository import (
    EvidenceWrite,
    native_location_evidence_repository,
)
from app.customer_migration.native_location_review import (
    list_location_identity_evidence,
    list_location_reconciliation_evidence,
)
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.users.models import User


def observation(
    location: str | None = "loc-1", customer: str | None = "cust-1", **changes: object
) -> NativeLocationObservation:
    values: dict[str, object] = {
        "provider": "provider-a",
        "native_location_id": location,
        "native_customer_id": customer,
        "source_artifact_sha256": "a" * 64,
        "source_record_sha256": hashlib.sha256(str(changes).encode()).hexdigest(),
        "normalized_address_sha256": "b" * 64,
        "address_complete": True,
        "candidate_location_keys": ("candidate-1",),
    }
    values.update(changes)
    return NativeLocationObservation(**values)  # type: ignore[arg-type]


def known_customer(
    provider: str = "provider-a", customer: str = "cust-1"
) -> frozenset[str]:
    return frozenset({scoped_identity(provider, "customer", customer)})


def test_identity_is_provider_and_entity_scoped_and_replay_deterministic() -> None:
    item = observation()
    first = reconcile_native_locations((item,), known_customer_hashes=known_customer())
    second = reconcile_native_locations((item,), known_customer_hashes=known_customer())
    assert first == second
    assert first[0].classification is LocationIdentityClassification.ACQUIRED
    assert scoped_identity("provider-a", "service_location", "1") != scoped_identity(
        "provider-b", "service_location", "1"
    )
    assert scoped_identity("provider-a", "service_location", "1") != scoped_identity(
        "provider-a", "customer", "1"
    )


@pytest.mark.parametrize(
    ("item", "classification"),
    [
        (
            observation(location=None),
            LocationIdentityClassification.MISSING_SOURCE_IDENTIFIER,
        ),
        (
            observation(customer=None),
            LocationIdentityClassification.MISSING_PARENT_CUSTOMER,
        ),
        (
            observation(address_complete=False),
            LocationIdentityClassification.INCOMPLETE_ADDRESS,
        ),
        (
            observation(authoritative_parent_customer_sha256="c" * 64),
            LocationIdentityClassification.SOURCE_CUSTOMER_MISMATCH,
        ),
        (
            observation(existing_acp_identity_conflict=True),
            LocationIdentityClassification.EXISTING_ACP_IDENTITY_CONFLICT,
        ),
        (
            observation(reconciliation_required=True),
            LocationIdentityClassification.RECONCILIATION_REQUIRED,
        ),
    ],
)
def test_fail_closed_classifications(
    item: NativeLocationObservation, classification: LocationIdentityClassification
) -> None:
    result = reconcile_native_locations(
        (item,), known_customer_hashes=known_customer()
    )[0]
    assert result.classification is classification
    assert result.readiness == "reconciliation_required"


def test_duplicate_identifier_and_multiple_candidate_locations() -> None:
    duplicate = reconcile_native_locations(
        (
            observation(source_record_sha256="1" * 64),
            observation(source_record_sha256="2" * 64),
        ),
        known_customer_hashes=known_customer(),
    )
    assert {item.classification for item in duplicate} == {
        LocationIdentityClassification.DUPLICATE_SOURCE_IDENTIFIER
    }
    conflict = reconcile_native_locations(
        (observation(candidate_location_keys=("one", "two")),),
        known_customer_hashes=known_customer(),
    )[0]
    assert (
        conflict.classification
        is LocationIdentityClassification.SOURCE_IDENTIFIER_MULTIPLE_LOCATIONS
    )


def test_equal_address_never_merges_distinct_native_identities() -> None:
    results = reconcile_native_locations(
        (
            observation("loc-1", source_record_sha256="1" * 64),
            observation("loc-2", source_record_sha256="2" * 64),
        ),
        known_customer_hashes=known_customer(),
    )
    assert len({item.source_location_id_sha256 for item in results}) == 2
    assert {item.classification for item in results} == {
        LocationIdentityClassification.ADDRESS_MULTIPLE_SOURCE_IDENTIFIERS
    }


def test_previously_imported_parent_mismatch_is_not_replaced() -> None:
    item = observation()
    accepted = AcceptedLocationIdentity(
        scoped_identity("provider-a", "service_location", "loc-1"),
        scoped_identity("provider-a", "customer", "different"),
        "acp-location",
    )
    result = reconcile_native_locations(
        (item,), known_customer_hashes=known_customer(), accepted_identities=(accepted,)
    )[0]
    assert (
        result.classification
        is LocationIdentityClassification.PREVIOUSLY_IMPORTED_IDENTITY_MISMATCH
    )


def test_pilot_boundary_is_immutable() -> None:
    preserve_pilot_boundary(("a", "b"), ("a", "b"))
    with pytest.raises(ValueError, match="immutable pilot boundary"):
        preserve_pilot_boundary(("a",), ("a", "b"))


@pytest.mark.asyncio
async def test_postgres_evidence_is_company_scoped_and_replay_safe() -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:8]
    try:
        async with factory() as session, session.begin():
            user = User(
                normalized_email=f"source4-{suffix}@example.test",
                first_name="Source",
                last_name="Four",
                display_name="Source Four",
                status="active",
            )
            company = Company(
                name="SOURCE.4 Test",
                code=f"S4{suffix}".upper(),
                status="active",
                timezone="America/New_York",
            )
            session.add_all([user, company])
            await session.flush()
            branch = Branch(
                company_id=company.id,
                name="SOURCE.4",
                code="SOURCE4",
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
            session.add(branch)
            await session.flush()
            other_user = User(
                normalized_email=f"source4-other-{suffix}@example.test",
                first_name="Other",
                last_name="Tenant",
                display_name="Other Tenant",
                status="active",
            )
            other_company = Company(
                name="SOURCE.4 Other Tenant",
                code=f"OT{suffix}".upper(),
                status="active",
                timezone="America/New_York",
            )
            session.add_all([other_user, other_company])
            await session.flush()
            other_branch = Branch(
                company_id=other_company.id,
                name="Other Branch",
                code="OTHER",
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
            session.add(other_branch)
            await session.flush()
            result = reconcile_native_locations(
                (observation(),), known_customer_hashes=known_customer()
            )[0]
            write = EvidenceWrite(
                company.id,
                branch.id,
                user.id,
                None,
                "provider-a",
                "a" * 64,
                "b" * 64,
                "c" * 64,
                result,
            )
            first, created = await native_location_evidence_repository.record(
                session, evidence=write
            )
            replay, replay_created = await native_location_evidence_repository.record(
                session, evidence=write
            )
            assert created is True
            assert replay_created is False
            assert replay.id == first.id
            assert first.source_location_id_sha256 == result.source_location_id_sha256
            assert not hasattr(first, "source_location_id")
            other_write = EvidenceWrite(
                other_company.id,
                other_branch.id,
                other_user.id,
                None,
                "provider-a",
                "a" * 64,
                "b" * 64,
                "c" * 64,
                result,
            )
            _, other_created = await native_location_evidence_repository.record(
                session, evidence=other_write
            )
            assert other_created is True
            projection = await list_location_identity_evidence(
                SimpleNamespace(company=company, active_branch=branch),
                session,
                readiness=None,
                limit=50,
                offset=0,
            )
            assert projection.total == 1
            assert "source_location_id" not in projection.items[0].model_dump()
            assert (
                projection.items[0].source_location_id_sha256
                == result.source_location_id_sha256
            )
            acquired = AcquiredNativeLocation(
                identity_evidence_id=first.id,
                company_id=company.id,
                branch_id=branch.id,
                source_location_id_sha256=result.source_location_id_sha256,
                source_customer_id_sha256=result.source_customer_id_sha256,
                customer_source_identity_id=None,
                normalized_address_sha256="c" * 64,
                readiness=result.readiness,
                evidence_digest=result.evidence_digest,
            )
            reconciliation = match_native_location(acquired, ())
            reconciliation_write = ReconciliationWrite(
                company.id, branch.id, user.id, reconciliation
            )
            (
                first_reconciliation,
                reconciliation_created,
            ) = await native_location_reconciliation_repository.record(
                session, evidence=reconciliation_write
            )
            (
                replay_reconciliation,
                replay_reconciliation_created,
            ) = await native_location_reconciliation_repository.record(
                session, evidence=reconciliation_write
            )
            assert reconciliation_created is True
            assert replay_reconciliation_created is False
            assert replay_reconciliation.id == first_reconciliation.id
            reconciliation_projection = await list_location_reconciliation_evidence(
                SimpleNamespace(company=company, active_branch=branch),
                session,
                outcome=None,
                limit=50,
                offset=0,
            )
            assert reconciliation_projection.total == 1
            assert reconciliation_projection.items[0].outcome == "no_match"
    finally:
        await engine.dispose()
