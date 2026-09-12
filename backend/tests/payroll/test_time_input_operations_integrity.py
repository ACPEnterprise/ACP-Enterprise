from types import SimpleNamespace
from typing import cast

from app.payroll.operations import PayrollOperationsService
from app.timekeeping.models import WorkdayTimeEntryRevision


def test_correction_lineage_timestamp_does_not_make_successor_payable() -> None:
    approved = SimpleNamespace(state="approved", approved_at=object())
    corrected = SimpleNamespace(state="corrected", approved_at=object())
    submitted = SimpleNamespace(state="submitted", approved_at=None)

    result = PayrollOperationsService._accepted_time_revisions(
        cast(
            tuple[WorkdayTimeEntryRevision, ...],
            (approved, corrected, submitted),
        )
    )

    assert result == (approved,)
