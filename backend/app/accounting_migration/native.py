import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingValidation,
)
from app.accounting.models import ControlAccountAssignment, Journal
from app.accounting.repository import AccountingRepository, accounting_repository
from app.accounting.schemas import JournalCreate, JournalLineCreate
from app.accounting.service import AccountingService
from app.accounting_migration.manifest import OpeningPackage
from app.accounting_migration.runtime import OpeningMigrationRuntime, OpeningStatePlan
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission


class OpeningComponent(str, Enum):
    AR_CONTROL = "ar_control"
    AP_CONTROL = "ap_control"
    BANK_CASH = "bank_cash"
    UNDEPOSITED_FUNDS = "undeposited_funds"
    PAYMENT_CLEARING = "payment_clearing"
    SALES_TAX = "sales_tax"
    INVENTORY = "inventory"
    PAYROLL_LIABILITY = "payroll_liability"
    RETAINED_EARNINGS = "retained_earnings"
    OPENING_EQUITY = "opening_equity"
    OTHER_BALANCE_SHEET = "other_balance_sheet"


class ReconciliationState(str, Enum):
    RECONCILED = "reconciled"
    PARTIALLY_RECONCILED = "partially_reconciled"
    CONFLICTING = "conflicting"
    MISSING_EVIDENCE = "missing_evidence"
    REJECTED = "rejected"
    APPROVED_ELIGIBLE = "approved_eligible_for_posting"


@dataclass(frozen=True, slots=True)
class AccountTargetBinding:
    source_account_id: str
    target_account_id: UUID
    component: OpeningComponent
    finance_mapping_reference: str


@dataclass(frozen=True, slots=True)
class BranchTargetBinding:
    source_branch_id: str
    target_branch_id: UUID


@dataclass(frozen=True, slots=True)
class OpeningPolicyPrerequisites:
    definition_version: str
    cutover_date: date
    period_id: UUID
    currency: str
    opening_balance_acceptance_reference: str
    reconciliation_precedence_reference: str
    retained_earnings_treatment_reference: str
    opening_equity_treatment_reference: str
    unresolved_ar_ap_treatment_reference: str
    unresolved_bank_cash_treatment_reference: str
    materiality_policy_reference: str
    approval_evidence_digest: str


@dataclass(frozen=True, slots=True)
class OpeningReconciliationLine:
    source_identity: str
    source_authority_classification: str
    source_evidence_digest: str
    reconciliation_identity: str
    imported_value_digest: str
    target_account_id: UUID | None
    target_branch_id: UUID | None
    component: OpeningComponent | None
    expected_debit: Decimal | None
    expected_credit: Decimal | None
    actual_prepared_debit: Decimal | None
    actual_prepared_credit: Decimal | None
    difference: Decimal | None
    state: ReconciliationState
    limitations: tuple[str, ...]
    source_artifact_id: str
    source_row: int


@dataclass(frozen=True, slots=True)
class OpeningReconciliation:
    package_id: str
    canonical_package_digest: str
    imported_value_digest: str
    reconciliation_identity: str
    reconciliation_digest: str
    definition_version: str
    transformation_version: str
    company_id: UUID
    branch_ids: tuple[UUID, ...]
    period_id: UUID
    cutover_date: date
    currency: str
    state: ReconciliationState
    eligible_for_posting: bool
    lines: tuple[OpeningReconciliationLine, ...]
    limitations: tuple[str, ...]
    prepared_by_user_id: UUID
    approved_by_user_id: UUID
    approval_evidence_digest: str
    policy_digest: str


@dataclass(frozen=True, slots=True)
class NativeOpeningReceipt:
    company_id: UUID
    package_id: str
    reconciliation_identity: str
    reconciliation_digest: str
    journal_id: UUID
    journal_version: int
    status: str
    posted_at: datetime


_CONTROL_ROLES = {
    OpeningComponent.AR_CONTROL: "accounts_receivable",
    OpeningComponent.AP_CONTROL: "accounts_payable",
    OpeningComponent.BANK_CASH: "bank_cash",
    OpeningComponent.UNDEPOSITED_FUNDS: "undeposited_funds",
    OpeningComponent.PAYMENT_CLEARING: "payment_clearing",
    OpeningComponent.SALES_TAX: "sales_tax_payable",
    OpeningComponent.INVENTORY: "inventory_asset",
    OpeningComponent.PAYROLL_LIABILITY: "payroll_liability",
    OpeningComponent.OPENING_EQUITY: "opening_balance",
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class NativeOpeningStateService:
    """Bind an accepted synthetic plan to governed native Accounting contracts."""

    def __init__(
        self,
        *,
        accounting: AccountingService | None = None,
        repository: AccountingRepository | None = None,
    ) -> None:
        self.accounting = accounting or AccountingService()
        self.repository = repository or accounting_repository

    @staticmethod
    def _validate_policy(policy: OpeningPolicyPrerequisites) -> None:
        references = (
            policy.definition_version,
            policy.opening_balance_acceptance_reference,
            policy.reconciliation_precedence_reference,
            policy.retained_earnings_treatment_reference,
            policy.opening_equity_treatment_reference,
            policy.unresolved_ar_ap_treatment_reference,
            policy.unresolved_bank_cash_treatment_reference,
            policy.materiality_policy_reference,
        )
        if any(not value.strip() for value in references):
            raise AccountingValidation("Every opening Finance policy reference is required")
        if len(policy.currency) != 3 or policy.currency != policy.currency.upper():
            raise AccountingValidation("Opening currency must be an ISO currency")
        if len(policy.approval_evidence_digest) != 64 or any(
            value not in "0123456789abcdef"
            for value in policy.approval_evidence_digest
        ):
            raise AccountingValidation("Opening approval evidence digest is invalid")

    async def reconcile(
        self,
        session: AsyncSession,
        *,
        package: OpeningPackage,
        plan: OpeningStatePlan,
        policy: OpeningPolicyPrerequisites,
        account_bindings: tuple[AccountTargetBinding, ...],
        branch_bindings: tuple[BranchTargetBinding, ...],
        preparer: AuthorizationContext,
        finance_approver: AuthorizationContext,
    ) -> OpeningReconciliation:
        OpeningMigrationRuntime.validate_plan(package, plan)
        self._validate_policy(policy)
        company_id = UUID(package.binding.target_company_id)
        if preparer.company.id != company_id or finance_approver.company.id != company_id:
            raise AccountingNotFound("Opening target Company was not found")
        if preparer.user.id == finance_approver.user.id:
            raise AccountingConflict("Opening preparer and Finance approver must differ")
        if not preparer.has_permission(AccountingPermission.JOURNAL_PREPARE) or not preparer.has_permission(
            AccountingPermission.RECONCILE
        ):
            raise AccountingValidation("Opening preparer lacks Accounting authority")
        if not finance_approver.has_permission(AccountingPermission.FINANCE_APPROVE):
            raise AccountingValidation("Opening Finance approval authority is required")
        cutoff = datetime.fromisoformat(package.cutoff)
        if cutoff.tzinfo is None or cutoff.date() != policy.cutover_date:
            raise AccountingValidation("Approved cutover date conflicts with package evidence")
        if package.binding.currency != policy.currency:
            raise AccountingValidation("Opening package currency conflicts with policy")

        chart = await self.repository.active_chart(session, company_id)
        period = await self.repository.period(session, company_id, policy.period_id)
        if chart is None or chart.currency != policy.currency:
            raise AccountingValidation("Active native chart and opening currency are required")
        if chart.accounting_basis != package.binding.accounting_basis:
            raise AccountingValidation("Opening accounting basis conflicts with native chart")
        if period is None or not (
            period.start_date <= policy.cutover_date <= period.end_date
        ):
            raise AccountingValidation("Opening cutover date has no valid Accounting period")
        if period.status not in {"open", "reopened"}:
            raise AccountingConflict("Opening Accounting period does not accept posting")

        account_map: dict[str, AccountTargetBinding] = {}
        duplicate_accounts: set[str] = set()
        for account_binding_item in account_bindings:
            if account_binding_item.source_account_id in account_map:
                duplicate_accounts.add(account_binding_item.source_account_id)
            account_map[account_binding_item.source_account_id] = account_binding_item
        branch_map: dict[str, BranchTargetBinding] = {}
        duplicate_branches: set[str] = set()
        for branch_binding_item in branch_bindings:
            if branch_binding_item.source_branch_id in branch_map:
                duplicate_branches.add(branch_binding_item.source_branch_id)
            branch_map[branch_binding_item.source_branch_id] = branch_binding_item

        artifact_map = {artifact.artifact_id: artifact for artifact in package.artifacts}
        native_lines: list[OpeningReconciliationLine] = []
        limitations: set[str] = set()
        for line in plan.journal_lines:
            artifact = artifact_map[line.source_artifact_id]
            account_binding = account_map.get(line.account_source_id)
            branch_binding = branch_map.get(line.branch_id)
            line_limitations: list[str] = []
            state = ReconciliationState.RECONCILED
            target_account_id = account_binding.target_account_id if account_binding else None
            target_branch_id = branch_binding.target_branch_id if branch_binding else None
            component = account_binding.component if account_binding else None
            if line.account_source_id in duplicate_accounts:
                state = ReconciliationState.CONFLICTING
                line_limitations.append("duplicate_account_mapping")
            elif account_binding is None or not account_binding.finance_mapping_reference.strip():
                state = ReconciliationState.MISSING_EVIDENCE
                line_limitations.append("account_mapping_missing")
            if line.branch_id in duplicate_branches:
                state = ReconciliationState.CONFLICTING
                line_limitations.append("duplicate_branch_mapping")
            elif branch_binding is None:
                state = ReconciliationState.MISSING_EVIDENCE
                line_limitations.append("branch_mapping_missing")
            elif not preparer.can_access_branch(branch_binding.target_branch_id) or not finance_approver.can_access_branch(
                branch_binding.target_branch_id
            ):
                raise AccountingNotFound("Opening target Branch was not found")

            if account_binding is not None:
                account = await self.repository.account(
                    session, company_id, account_binding.target_account_id
                )
                if account is None or account.status != "active":
                    state = ReconciliationState.MISSING_EVIDENCE
                    line_limitations.append("target_account_missing")
                elif account.classification not in {"asset", "liability", "equity"}:
                    state = ReconciliationState.CONFLICTING
                    line_limitations.append("target_not_balance_sheet_account")
                expected_role = _CONTROL_ROLES.get(account_binding.component)
                if expected_role is not None:
                    role = await session.scalar(
                        select(ControlAccountAssignment.control_role).where(
                            ControlAccountAssignment.company_id == company_id,
                            ControlAccountAssignment.account_id
                            == account_binding.target_account_id,
                            ControlAccountAssignment.control_role == expected_role,
                            ControlAccountAssignment.effective_from
                            <= policy.cutover_date,
                            (
                                ControlAccountAssignment.effective_to.is_(None)
                                | (
                                    ControlAccountAssignment.effective_to
                                    >= policy.cutover_date
                                )
                            ),
                        )
                    )
                    if role is None:
                        state = ReconciliationState.MISSING_EVIDENCE
                        line_limitations.append("control_account_assignment_missing")

            expected_debit = line.debit if state is ReconciliationState.RECONCILED else None
            expected_credit = line.credit if state is ReconciliationState.RECONCILED else None
            imported_digest = _digest(
                {
                    "artifact_sha256": artifact.sha256,
                    "source_row": line.source_row,
                    "source_identity": line.account_source_id,
                    "debit": line.debit,
                    "credit": line.credit,
                }
            )
            reconciliation_identity = _digest(
                {
                    "package_id": package.package_id,
                    "line_id": line.line_id,
                    "target_account_id": target_account_id,
                    "target_branch_id": target_branch_id,
                }
            )
            limitations.update(line_limitations)
            native_lines.append(
                OpeningReconciliationLine(
                    source_identity=line.account_source_id,
                    source_authority_classification=artifact.source_authority,
                    source_evidence_digest=artifact.sha256,
                    reconciliation_identity=reconciliation_identity,
                    imported_value_digest=imported_digest,
                    target_account_id=target_account_id,
                    target_branch_id=target_branch_id,
                    component=component,
                    expected_debit=expected_debit,
                    expected_credit=expected_credit,
                    actual_prepared_debit=expected_debit,
                    actual_prepared_credit=expected_credit,
                    difference=Decimal(0)
                    if state is ReconciliationState.RECONCILED
                    else None,
                    state=state,
                    limitations=tuple(sorted(line_limitations)),
                    source_artifact_id=line.source_artifact_id,
                    source_row=line.source_row,
                )
            )

        if plan.rejections:
            limitations.add("source_rows_rejected")
        states = {line.state for line in native_lines}
        if ReconciliationState.CONFLICTING in states:
            overall = ReconciliationState.CONFLICTING
        elif ReconciliationState.MISSING_EVIDENCE in states:
            overall = ReconciliationState.MISSING_EVIDENCE
        elif plan.rejections:
            overall = ReconciliationState.PARTIALLY_RECONCILED
        else:
            overall = ReconciliationState.APPROVED_ELIGIBLE

        policy_digest = _digest(asdict(policy))
        imported_value_digest = _digest(
            [line.imported_value_digest for line in native_lines]
        )
        reconciliation_identity = _digest(
            {
                "package_id": package.package_id,
                "manifest_sha256": package.manifest_sha256,
                "transformation_version": package.transformation_version,
                "target_company_id": company_id,
                "definition_version": policy.definition_version,
            }
        )
        reconciliation_payload = {
            "canonical_package_digest": package.manifest_sha256,
            "imported_value_digest": imported_value_digest,
            "reconciliation_identity": reconciliation_identity,
            "definition_version": policy.definition_version,
            "policy_digest": policy_digest,
            "lines": [asdict(line) for line in native_lines],
            "limitations": sorted(limitations),
            "prepared_by_user_id": preparer.user.id,
            "approved_by_user_id": finance_approver.user.id,
            "approval_evidence_digest": policy.approval_evidence_digest,
        }
        reconciliation = OpeningReconciliation(
            package_id=package.package_id,
            canonical_package_digest=package.manifest_sha256,
            imported_value_digest=imported_value_digest,
            reconciliation_identity=reconciliation_identity,
            reconciliation_digest=_digest(reconciliation_payload),
            definition_version=policy.definition_version,
            transformation_version=package.transformation_version,
            company_id=company_id,
            branch_ids=tuple(
                sorted(
                    {
                        line.target_branch_id
                        for line in native_lines
                        if line.target_branch_id is not None
                    },
                    key=str,
                )
            ),
            period_id=policy.period_id,
            cutover_date=policy.cutover_date,
            currency=policy.currency,
            state=overall,
            eligible_for_posting=overall is ReconciliationState.APPROVED_ELIGIBLE,
            lines=tuple(native_lines),
            limitations=tuple(sorted(limitations)),
            prepared_by_user_id=preparer.user.id,
            approved_by_user_id=finance_approver.user.id,
            approval_evidence_digest=policy.approval_evidence_digest,
            policy_digest=policy_digest,
        )
        if not reconciliation.eligible_for_posting:
            await session.rollback()
            await self.accounting.record_posting_failure(
                session,
                context=preparer,
                source_system="accounting_migration",
                source_type="opening_reconciliation",
                source_identity=f"package:{reconciliation.package_id}",
                source_digest=reconciliation.reconciliation_digest,
                error_code=f"OpeningReconciliation{reconciliation.state.value.title().replace('_', '')}",
                correlation_id=UUID(reconciliation.reconciliation_identity[:32]),
                details={
                    "definition_version": reconciliation.definition_version,
                    "state": reconciliation.state.value,
                    "limitations": list(reconciliation.limitations),
                },
            )
        return reconciliation

    async def post(
        self,
        session: AsyncSession,
        *,
        reconciliation: OpeningReconciliation,
        preparer: AuthorizationContext,
        finance_approver: AuthorizationContext,
        poster: AuthorizationContext,
    ) -> NativeOpeningReceipt:
        if not reconciliation.eligible_for_posting or reconciliation.state is not ReconciliationState.APPROVED_ELIGIBLE:
            raise AccountingValidation("Opening reconciliation is not eligible for posting")
        if (
            preparer.user.id != reconciliation.prepared_by_user_id
            or finance_approver.user.id != reconciliation.approved_by_user_id
        ):
            raise AccountingConflict("Opening reconciliation actor evidence changed")
        if len({preparer.user.id, finance_approver.user.id, poster.user.id}) != 3:
            raise AccountingConflict("Opening posting requires three distinct actors")
        if any(
            context.company.id != reconciliation.company_id
            for context in (preparer, finance_approver, poster)
        ):
            raise AccountingNotFound("Opening target Company was not found")
        if not poster.has_permission(AccountingPermission.JOURNAL_POST):
            raise AccountingValidation("Opening poster lacks Accounting authority")
        if not all(
            all(context.can_access_branch(branch_id) for branch_id in reconciliation.branch_ids)
            for context in (preparer, finance_approver, poster)
        ):
            raise AccountingNotFound("Opening target Branch was not found")
        if len(reconciliation.branch_ids) > 1:
            raise AccountingValidation("Day-1 opening journal cannot span Branches")

        lines = tuple(
            JournalLineCreate(
                account_id=line.target_account_id,
                branch_id=line.target_branch_id,
                debit=line.actual_prepared_debit,
                credit=line.actual_prepared_credit,
                description=f"Opening evidence {line.reconciliation_identity}",
            )
            for line in reconciliation.lines
            if line.target_account_id is not None
            and line.target_branch_id is not None
            and line.actual_prepared_debit is not None
            and line.actual_prepared_credit is not None
        )
        data = JournalCreate(
            period_id=reconciliation.period_id,
            journal_type="opening",
            effective_date=reconciliation.cutover_date,
            currency=reconciliation.currency,
            description=f"Approved opening state {reconciliation.package_id}",
            source_system="accounting_migration",
            source_type="opening_state",
            source_identity=f"package:{reconciliation.package_id}",
            source_digest=reconciliation.reconciliation_digest,
            posting_rule_version=(
                f"{reconciliation.definition_version}:"
                f"{reconciliation.transformation_version}"
            ),
            client_idempotency_key=(
                f"opening:{reconciliation.package_id}:"
                f"{reconciliation.transformation_version}"
            ),
            evidence_digest=reconciliation.approval_evidence_digest,
            control_override_reason=(
                f"Finance-approved opening reconciliation "
                f"{reconciliation.reconciliation_identity}"
            ),
            lines=lines,
        )
        try:
            journal = await self.accounting.create_journal(
                session, context=preparer, data=data, allow_control_override=True
            )
            if journal.status == "draft":
                journal = await self.accounting.prepare_journal(
                    session,
                    context=preparer,
                    journal_id=journal.id,
                    expected_version=journal.version,
                )
            if journal.status == "prepared":
                journal = await self.accounting.approve_journal(
                    session,
                    context=finance_approver,
                    journal_id=journal.id,
                    expected_version=journal.version,
                    evidence_digest=reconciliation.approval_evidence_digest,
                    reason=(
                        f"Approved opening reconciliation "
                        f"{reconciliation.reconciliation_identity}"
                    ),
                )
            if journal.status == "approved":
                journal = await self.accounting.post_journal(
                    session,
                    context=poster,
                    journal_id=journal.id,
                    expected_version=journal.version,
                )
        except (AccountingConflict, AccountingNotFound, AccountingValidation) as error:
            await session.rollback()
            await self.accounting.record_posting_failure(
                session,
                context=poster,
                source_system="accounting_migration",
                source_type="opening_state",
                source_identity=f"package:{reconciliation.package_id}",
                source_digest=reconciliation.reconciliation_digest,
                error_code=error.__class__.__name__,
                correlation_id=UUID(reconciliation.reconciliation_identity[:32]),
                details={
                    "definition_version": reconciliation.definition_version,
                    "state": reconciliation.state.value,
                },
            )
            raise
        return self._receipt(reconciliation, journal)

    @staticmethod
    def _receipt(
        reconciliation: OpeningReconciliation, journal: Journal
    ) -> NativeOpeningReceipt:
        if journal.status != "posted" or journal.posted_at is None:
            raise AccountingConflict("Opening journal did not reach posted state")
        return NativeOpeningReceipt(
            company_id=reconciliation.company_id,
            package_id=reconciliation.package_id,
            reconciliation_identity=reconciliation.reconciliation_identity,
            reconciliation_digest=reconciliation.reconciliation_digest,
            journal_id=journal.id,
            journal_version=journal.version,
            status=journal.status,
            posted_at=journal.posted_at,
        )
