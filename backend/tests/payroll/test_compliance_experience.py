from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from app.payroll.compliance import DraftComplianceSchema, ProtectedPayrollReportStorage
from app.payroll.contracts import PayrollConflictError


def test_compliance_schema_is_explicit_and_provider_neutral() -> None:
    value = DraftComplianceSchema(
        "synthetic-jurisdiction",
        "quarterly-employer",
        2027,
        1,
        "synthetic-schema-v1",
        "synthetic-rule-v1",
        ("approved-report", "complete-history"),
        ("legal-wording-unresolved",),
        date(2027, 1, 1),
        date(2027, 3, 31),
    )
    assert value.required_evidence == ("approved-report", "complete-history")
    with pytest.raises(ValueError, match="quarter"):
        DraftComplianceSchema(
            "synthetic", "quarterly", 2027, 5, "v1", "v1", ("report",), (), date(2027, 1, 1)
        )


def test_reporting_storage_is_opaque_private_and_tenant_scoped(tmp_path: Path) -> None:
    company_id = uuid4()
    storage = ProtectedPayrollReportStorage(tmp_path.resolve())
    storage.put(company_id, "pra-abcdef123456", b"synthetic report")
    stored = next(tmp_path.rglob("pra-*"))
    assert stored.stat().st_mode & 0o777 == 0o600
    assert str(company_id) in stored.parts
    assert storage.get(company_id, "pra-abcdef123456") == b"synthetic report"
    with pytest.raises(PayrollConflictError):
        storage.get(company_id, "../public")
    with pytest.raises(ValueError):
        ProtectedPayrollReportStorage(Path("relative"))
