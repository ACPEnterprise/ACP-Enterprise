from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.operational_migration.repository import OperationalMigrationRepository


@pytest.mark.asyncio
async def test_job_lookup_requires_company_scope() -> None:
    session = AsyncMock()
    session.scalar.return_value = None
    company_id = uuid4()
    job_id = uuid4()

    result = await OperationalMigrationRepository.get_job(
        session, company_id=company_id, job_id=job_id
    )

    assert result is None
    statement = session.scalar.await_args.args[0]
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    sql = str(compiled)
    assert "jobs.id =" in sql
    assert str(job_id) in sql
    assert "jobs.company_id =" in sql
    assert str(company_id) in sql
