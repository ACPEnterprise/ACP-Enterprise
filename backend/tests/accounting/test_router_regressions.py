from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.accounting import router as accounting_router
from app.accounting.router import list_journals


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _Session:
    def __init__(self, journal: object) -> None:
        self.journal = journal

    async def scalars(self, _query: object) -> _ScalarRows:
        return _ScalarRows([self.journal])


def _journal() -> SimpleNamespace:
    company_id = uuid4()
    return SimpleNamespace(
        id=uuid4(),
        company_id=company_id,
        period_id=uuid4(),
        journal_type="standard",
        status="draft",
        effective_date=date(2026, 11, 14),
        currency="USD",
        description="Synthetic journal",
        total_debits=Decimal("10.00"),
        total_credits=Decimal("10.00"),
        source_system="simulation",
        source_type="acceptance",
        source_identity="journal-1",
        source_digest="d" * 64,
        posting_rule_version="v1",
        prepared_by_user_id=uuid4(),
        approved_by_user_id=None,
        posted_at=None,
        reversal_of_id=None,
        version=1,
    )


@pytest.mark.asyncio
async def test_list_journals_awaits_line_queries_before_building_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _journal()

    async def lines(
        _session: object, _company_id: object, _journal_id: object
    ) -> tuple:
        return ()

    monkeypatch.setattr(accounting_router.accounting_repository, "lines", lines)
    context = SimpleNamespace(company=SimpleNamespace(id=journal.company_id))

    result = await list_journals(context, _Session(journal), limit=1)

    assert len(result) == 1
    assert result[0].id == journal.id
    assert result[0].lines == ()
