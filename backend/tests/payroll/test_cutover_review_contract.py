"""Fail-closed contract checks for Payroll cutover review authority."""

from app.payroll.cutover_router import (
    ACCOUNTANT_FACTS,
    BRIDGE_FACT_DEFINITIONS,
    OWNER_FACTS,
    router,
)
from app.payroll.models import (
    PayrollCutoverBridgeEmployeeFactRevision,
    PayrollCutoverBridgePeriodRecord,
    PayrollCutoverFactRevision,
    PayrollCutoverReviewRecord,
)
from app.payroll.permissions import PayrollPermission
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX, LaunchRoleCode


def test_cutover_permissions_are_distinct_from_execution_authority() -> None:
    cutover = {
        PayrollPermission.CUTOVER_READ,
        PayrollPermission.CUTOVER_OWNER_CERTIFY,
        PayrollPermission.CUTOVER_ACCOUNTANT_CERTIFY,
        PayrollPermission.CUTOVER_APPROVE,
    }
    execution = {
        PayrollPermission.CALCULATION_EXECUTE,
        PayrollPermission.RUN_APPROVE,
        PayrollPermission.PAYMENT_EXECUTION_AUTHORIZE,
        PayrollPermission.REMITTANCE_EXECUTE,
        PayrollPermission.ACCOUNTING_PREPARE,
    }
    assert cutover.isdisjoint(execution)
    administrator = next(
        item
        for item in LAUNCH_ROLE_MATRIX
        if item.code is LaunchRoleCode.COMPANY_ADMINISTRATOR
    )
    assert PayrollPermission.CUTOVER_READ in administrator.permission_codes
    assert PayrollPermission.CUTOVER_OWNER_CERTIFY in administrator.permission_codes
    assert (
        PayrollPermission.CUTOVER_ACCOUNTANT_CERTIFY
        not in administrator.permission_codes
    )


def test_cutover_schema_is_separate_from_operational_payroll() -> None:
    assert PayrollCutoverReviewRecord.__tablename__ == "payroll_cutover_reviews"
    assert PayrollCutoverFactRevision.__tablename__ == "payroll_cutover_fact_revisions"
    assert (
        PayrollCutoverBridgePeriodRecord.__tablename__
        == "payroll_cutover_bridge_periods"
    )
    assert (
        PayrollCutoverBridgeEmployeeFactRevision.__tablename__
        == "payroll_cutover_bridge_employee_fact_revisions"
    )
    table_names = set(PayrollCutoverReviewRecord.metadata.tables)
    assert "payroll_runs" in table_names
    assert "payroll_cutover_bridge_periods" in table_names


def test_api_has_review_only_and_no_execution_routes() -> None:
    paths = {route.path for route in router.routes}
    assert "/api/v1/payroll/cutover-review/facts" in paths
    assert "/api/v1/payroll/cutover-review/certifications" in paths
    assert "/api/v1/payroll/cutover-review/bridge-periods" in paths
    assert "/api/v1/payroll/cutover-review/gates" in paths
    assert "/api/v1/payroll/cutover-review/direct-deposit-readiness" in paths
    assert "/api/v1/payroll/cutover-review/completion-readiness" in paths
    assert not any(
        any(word in path for word in ("execute", "calculate", "ach", "post-accounting"))
        for path in paths
    )


def test_owner_and_accountant_fact_authorities_do_not_overlap() -> None:
    assert OWNER_FACTS
    assert ACCOUNTANT_FACTS
    assert OWNER_FACTS.isdisjoint(ACCOUNTANT_FACTS)


def test_bridge_completion_contract_requires_physical_payroll_evidence() -> None:
    fields = {item["key"]: item for item in BRIDGE_FACT_DEFINITIONS}
    assert set(fields) == {
        "gross_wages",
        "regular_hours",
        "regular_wages",
        "overtime_hours",
        "overtime_wages",
        "other_earnings",
        "deductions",
        "employee_taxes",
        "employer_taxes",
        "reimbursements",
        "net_pay",
        "check_reference",
        "liability_impact",
        "payment_status",
        "tax_remittance_status",
        "source_document",
        "notes",
    }
    assert fields["regular_hours"]["owner"] == "owner"
    assert fields["gross_wages"]["owner"] == "accountant"
    assert fields["liability_impact"]["owner"] == "accountant"
