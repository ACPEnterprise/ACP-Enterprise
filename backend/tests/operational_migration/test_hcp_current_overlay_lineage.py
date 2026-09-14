from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.customer_migration.models import CustomerMigrationRun
from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayExecutor,
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayExecutionReceipt,
    OverlayJournalEntry,
    OverlayKey,
    OverlayRecord,
    OverlaySourceState,
)
from app.operational_migration.hcp_current_overlay_adapter import (
    SqlAlchemyCurrentOverlayRepository,
)
from app.operational_migration.hcp_current_overlay_lineage import (
    MASTER_STATUS,
    CurrentOverlayLineageBinding,
    CurrentOverlayLineageBootstrap,
)
from app.operational_migration.models import (
    HcpMigrationMasterRun,
    OperationalMigrationRun,
)
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.users.models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DIGEST = "a" * 64
MANIFEST_DIGEST = "b" * 64


@pytest_asyncio.fixture
async def lineage_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _scope(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[Company, Branch, User]:
    suffix = uuid4().hex[:8]
    async with factory() as session, session.begin():
        company = Company(
            name="Overlay Lineage",
            code=f"OL{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        user = User(
            normalized_email=f"overlay-{suffix}@example.test",
            first_name="Overlay",
            last_name="Operator",
            display_name="Overlay Operator",
            status="active",
        )
        session.add_all((company, user))
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="Overlay Branch",
            code="OVERLAY",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add(branch)
        await session.flush()
    return company, branch, user


def _manifest(company: Company, branch: Branch) -> CurrentOverlayManifest:
    return CurrentOverlayManifest.build(
        base_source4_digest=DIGEST,
        delta_digest="c" * 64,
        company_id=str(company.id),
        branch_id=str(branch.id),
        acquired_at="2026-09-12T17:00:00+00:00",
        records=(
            OverlayRecord(
                "customer",
                "cus_1",
                OverlayAssertion.CREATE,
                "d" * 64,
                "2026-09-12T17:00:00+00:00",
                {},
            ),
            OverlayRecord(
                "appointment",
                "apt_1",
                OverlayAssertion.HOLD,
                "e" * 64,
                "2026-09-12T17:00:00+00:00",
                {},
                reason="canonical hold",
            ),
        ),
    )


def _bootstrap(
    company: Company,
    branch: Branch,
    user: User,
    manifest: CurrentOverlayManifest,
    *,
    hold_digest: str = "f" * 64,
) -> CurrentOverlayLineageBootstrap:
    return CurrentOverlayLineageBootstrap(
        CurrentOverlayLineageBinding(
            company.id,
            branch.id,
            user.id,
            "SOURCE.4/sealed/2026-08-28",
            DIGEST,
            manifest.digest,
            "1" * 64,
            hold_digest,
            1389,
            "2" * 40,
            "g7i9k1m3o5q7",
        ),
        manifest,
    )


def _receipt(manifest: CurrentOverlayManifest) -> OverlayExecutionReceipt:
    journal = (
        OverlayJournalEntry(
            OverlayKey("customer", "cus_1"),
            OverlayAssertion.CREATE,
            "created",
            None,
            "d" * 64,
            str(uuid4()),
        ),
        OverlayJournalEntry(
            OverlayKey("appointment", "apt_1"),
            OverlayAssertion.HOLD,
            "held",
            None,
            None,
            None,
        ),
    )
    return OverlayExecutionReceipt(
        "hcp-current-overlay-executor/v1",
        manifest.digest,
        "3" * 64,
        {"created": 1, "held": 1},
        journal,
        "4" * 64,
    )


class _Services:
    def bind_lineage(self, **values: object) -> None:
        self.lineage = values

    async def prepare_update_bindings(
        self, session: AsyncSession, records: tuple[OverlayRecord, ...]
    ) -> dict[str, dict[str, int]]:
        return {}

    async def source_state(
        self, session: AsyncSession, key: OverlayKey
    ) -> OverlaySourceState | None:
        return None

    async def source_exists(self, session: AsyncSession, key: OverlayKey) -> bool:
        return False

    async def fingerprint_owners(
        self, session: AsyncSession, domain: str, fingerprint: str
    ) -> tuple[str, ...]:
        return ()

    async def create(
        self, session: AsyncSession, record: OverlayRecord
    ) -> OverlaySourceState:
        return OverlaySourceState(
            record.source_digest, f"native-{record.source_id}", {}
        )

    async def update(
        self, session: AsyncSession, state: OverlaySourceState, record: OverlayRecord
    ) -> OverlaySourceState:
        return state

    async def record_non_mutating_assertion(
        self, session: AsyncSession, record: OverlayRecord
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_bootstrap_is_atomic_truthful_and_replay_safe(
    lineage_database: async_sessionmaker[AsyncSession],
) -> None:
    company, branch, user = await _scope(lineage_database)
    manifest = _manifest(company, branch)
    first = _bootstrap(company, branch, user, manifest)
    async with lineage_database() as session, session.begin():
        master = await first.establish(session)
        await first.finalize(_receipt(manifest))
        master_id = master.id
    async with lineage_database() as session:
        master = await session.get(HcpMigrationMasterRun, master_id)
        assert master is not None and master.status == MASTER_STATUS
        assert master.hold_counts == {"canonical_ambiguous": 1389}
        assert master.transformation_contracts["canonical_admission_allowed"] is False
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationRun)
                .where(CustomerMigrationRun.master_run_id == master_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OperationalMigrationRun)
                .where(OperationalMigrationRun.master_run_id == master_id)
            )
            == 1
        )
    replay = _bootstrap(company, branch, user, manifest)
    async with lineage_database() as session, session.begin():
        assert (await replay.establish(session)).id == master_id


@pytest.mark.asyncio
async def test_conflicting_binding_fails_closed(
    lineage_database: async_sessionmaker[AsyncSession],
) -> None:
    company, branch, user = await _scope(lineage_database)
    manifest = _manifest(company, branch)
    bootstrap = _bootstrap(company, branch, user, manifest)
    async with lineage_database() as session, session.begin():
        await bootstrap.establish(session)
        await bootstrap.finalize(_receipt(manifest))
    conflict = _bootstrap(company, branch, user, manifest, hold_digest="9" * 64)
    async with lineage_database() as session:
        with pytest.raises(ValueError, match="binding conflict"):
            async with session.begin():
                await conflict.establish(session)


@pytest.mark.asyncio
async def test_failure_rolls_back_master_and_children(
    lineage_database: async_sessionmaker[AsyncSession],
) -> None:
    company, branch, user = await _scope(lineage_database)
    manifest = _manifest(company, branch)
    bootstrap = _bootstrap(company, branch, user, manifest)
    with pytest.raises(RuntimeError, match="overlay failed"):
        async with lineage_database() as session, session.begin():
            await bootstrap.establish(session)
            raise RuntimeError("overlay failed")
    async with lineage_database() as session:
        assert (
            await session.get(HcpMigrationMasterRun, bootstrap.binding.master_run_id)
            is None
        )


@pytest.mark.asyncio
async def test_repository_persists_receipt_and_exact_replay(
    lineage_database: async_sessionmaker[AsyncSession],
) -> None:
    company, branch, user = await _scope(lineage_database)
    manifest = _manifest(company, branch)
    first = _bootstrap(company, branch, user, manifest)
    async with lineage_database() as session:
        receipt = await CurrentOverlayExecutor().execute(
            SqlAlchemyCurrentOverlayRepository(
                session,
                master_run_id=first.binding.master_run_id,
                services=_Services(),
                lineage_bootstrap=first,
            ),
            manifest=manifest,
            expected_base_source4_digest=DIGEST,
            rollback_backup_digest="3" * 64,
        )
    replay = _bootstrap(company, branch, user, manifest)
    async with lineage_database() as session:
        second = await CurrentOverlayExecutor().execute(
            SqlAlchemyCurrentOverlayRepository(
                session,
                master_run_id=replay.binding.master_run_id,
                services=_Services(),
                lineage_bootstrap=replay,
            ),
            manifest=manifest,
            expected_base_source4_digest=DIGEST,
            rollback_backup_digest="3" * 64,
        )
    assert second == receipt
