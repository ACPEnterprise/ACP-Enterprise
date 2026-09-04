"""Safe executable composition boundary for the HCP.MIGRATION.2 rehearsal."""

from __future__ import annotations

import csv
import hashlib
import json
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.adapter_import import (
    ApprovedCustomerImportBoundary,
    ReviewedCustomerAdapterOutput,
)
from app.operational_migration.cutover import HistoryMigrationRecord
from app.operational_migration.financial import (
    EstimateMigrationRecord,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.hcp_hybrid_customer import (
    AssertionKind,
    ControlAssertion,
    CustomerAssertion,
    HybridCustomerAdmission,
    JobParentClosure,
    build_hybrid_admission,
    build_reviewed_customer_output,
    canonical_sha256,
    close_job_parents,
)
from app.operational_migration.hcp_migration2a import UnlinkedEstimateEvidenceCommand
from app.operational_migration.hcp_migration2b import (
    HoldCommand,
    MasterRunCommand,
    PlanOutcomeCommand,
)
from app.operational_migration.hcp_migration2c import (
    CompletionRequirements,
    EmployeeCandidateCommand,
    HcpMigration2Orchestrator,
)
from app.operational_migration.hcp_migration2i import ChildOutcomeCounts
from app.operational_migration.hcp_owner_disposition import NonProductionTarget
from app.operational_migration.hcp_successor_reuse import (
    AdmissionDisposition,
    QualifiedSuccessorManifest,
    qualify_reuse_graph,
)
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
)
from app.platform.permissions.authorization import AuthorizationContext

RUNNER_VERSION = "hcp-migration-2f-source4-runner/v1"
EXPECTED_PACKAGE_DIGEST = (
    "f77e3e09457efcbf6d42137be1af43be6ad0adbea8eab2c12ca320730fd96901"
)
EXPECTED_HYBRID_DIGEST = (
    "228f2e1b1f9050066cd8de5cddfceff6a62461864c0d6a90361040801132cbad"
)
EXPECTED_PARENT_CLOSURE_DIGEST = (
    "05fd508921de0c9521ac7c7be9632489a7ade3ab90ae2f0bb5c59a5d709e502b"
)


class SafeEvidenceError(ValueError):
    """An intentionally payload-free protected-evidence error."""

    def __init__(self, code: str, evidence_digest: str) -> None:
        self.code = code
        self.evidence_digest = evidence_digest
        super().__init__(f"{code}:{evidence_digest}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_customer_objects(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if str(value.get("id", "")).startswith("cus_") and "addresses" in value:
            found.append(value)
        else:
            for child in value.values():
                found.extend(_find_customer_objects(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_customer_objects(child))
    return found


def _safe_json(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError, TypeError) as error:
        raise SafeEvidenceError(
            "protected_json_invalid", hashlib.sha256(path.name.encode()).hexdigest()
        ) from error


@dataclass(frozen=True)
class VerifiedSource4CustomerComposition:
    package_digest: str
    collection_digest: str
    admission: HybridCustomerAdmission
    parent_closure: JobParentClosure
    reviewed: ReviewedCustomerAdapterOutput
    boundary: ApprovedCustomerImportBoundary
    safe_counts: dict[str, int]

    def safe_summary(self) -> dict[str, object]:
        return {
            "contract": RUNNER_VERSION,
            "package_digest": self.package_digest,
            "collection_digest": self.collection_digest,
            "admission_digest": self.admission.digest,
            "parent_closure_digest": self.parent_closure.digest,
            "counts": self.safe_counts,
        }


class ProtectedSource4Loader:
    """Reads protected bytes and returns contracts or safe metadata only."""

    def __init__(self, package_root: Path, control_csv: Path) -> None:
        self.package_root = package_root.resolve()
        self.control_csv = control_csv.resolve()

    def _validate_paths(self) -> None:
        if not self.package_root.is_dir() or not self.control_csv.is_file():
            raise SafeEvidenceError("protected_evidence_missing", "0" * 64)
        if self.package_root.name != "hcp-source-4-20260827T223858Z":
            raise SafeEvidenceError("protected_package_identity_invalid", "0" * 64)
        for path in (self.package_root, self.control_csv):
            mode = stat.S_IMODE(path.stat().st_mode)
            if path.is_file() and mode & 0o077:
                raise SafeEvidenceError(
                    "protected_evidence_permissions_invalid",
                    hashlib.sha256(path.name.encode()).hexdigest(),
                )

    def load_customers(self) -> VerifiedSource4CustomerComposition:
        self._validate_paths()
        collection_path = self.package_root / "collection-manifest.json"
        package_path = self.package_root / "acquisition-package-manifest.json"
        collection = _safe_json(collection_path)
        package = _safe_json(package_path)
        if not isinstance(collection, dict) or not isinstance(package, dict):
            raise SafeEvidenceError("protected_manifest_shape_invalid", "0" * 64)
        collection_claim = collection.get("manifest_sha256")
        package_claim = package.get("manifest_sha256")
        collection_payload = {
            k: v for k, v in collection.items() if k != "manifest_sha256"
        }
        package_payload = {k: v for k, v in package.items() if k != "manifest_sha256"}
        if collection_claim != canonical_sha256(collection_payload):
            raise SafeEvidenceError("collection_manifest_digest_mismatch", "1" * 64)
        if package_claim != canonical_sha256(package_payload):
            raise SafeEvidenceError("package_manifest_digest_mismatch", "2" * 64)
        if package_claim != EXPECTED_PACKAGE_DIGEST:
            raise SafeEvidenceError(
                "package_authority_mismatch", canonical_sha256(package_claim)
            )
        if package.get("collection_manifest_sha256") != _file_sha256(collection_path):
            raise SafeEvidenceError("collection_file_digest_mismatch", "3" * 64)

        api: list[CustomerAssertion] = []
        customer_pages = sorted(
            (self.package_root / "raw" / "customers").glob("page-*.json")
        )
        page_claims = collection["collections"]["customers"]["page_sha256s"]
        if [_file_sha256(path) for path in customer_pages] != page_claims:
            raise SafeEvidenceError("customer_page_digest_mismatch", "4" * 64)
        for page in customer_pages:
            payload = _safe_json(page)
            try:
                customers = payload["customers"]
            except (KeyError, TypeError) as error:
                raise SafeEvidenceError(
                    "customer_page_layout_invalid",
                    hashlib.sha256(page.name.encode()).hexdigest(),
                ) from error
            for customer in customers:
                try:
                    api.append(
                        CustomerAssertion.source4(
                            kind=AssertionKind.API_LISTED,
                            payload=customer,
                            container_digest=_file_sha256(page),
                        )
                    )
                except (TypeError, ValueError) as error:
                    raise SafeEvidenceError(
                        "customer_assertion_invalid",
                        hashlib.sha256(page.name.encode()).hexdigest(),
                    ) from error

        details: list[CustomerAssertion] = []
        detail_root = (
            self.package_root / "raw" / "customer-details-referenced-not-listed"
        )
        for path in sorted(detail_root.glob("*.json")):
            found = _find_customer_objects(_safe_json(path))
            if len(found) != 1:
                raise SafeEvidenceError(
                    "referenced_customer_detail_invalid",
                    hashlib.sha256(path.name.encode()).hexdigest(),
                )
            details.append(
                CustomerAssertion.source4(
                    kind=AssertionKind.REFERENCED_DETAIL,
                    payload=found[0],
                    container_digest=_file_sha256(path),
                )
            )

        controls: list[ControlAssertion] = []
        with self.control_csv.open(newline="") as source:
            for row in csv.DictReader(source):
                control_id = row.get("ID")
                if not control_id:
                    raise SafeEvidenceError("control_identity_missing", "5" * 64)
                try:
                    controls.append(
                        ControlAssertion(
                            control_identity=control_id,
                            payload_digest=canonical_sha256(row),
                            disposition="CONTROL_ASSERTION",
                        )
                    )
                except (TypeError, ValueError) as error:
                    raise SafeEvidenceError(
                        "control_assertion_invalid", canonical_sha256(row)
                    ) from error
        admission = build_hybrid_admission(
            api_assertions=api,
            detail_assertions=details,
            control_assertions=controls,
        )
        reviewed, boundary = build_reviewed_customer_output(admission)
        jobs: list[tuple[str, str]] = []
        for path in sorted((self.package_root / "raw" / "jobs").glob("page-*.json")):
            payload = _safe_json(path)
            try:
                jobs.extend(
                    (item["id"], item["customer"]["id"]) for item in payload["jobs"]
                )
            except (KeyError, TypeError) as error:
                raise SafeEvidenceError(
                    "job_parent_layout_invalid",
                    hashlib.sha256(path.name.encode()).hexdigest(),
                ) from error
        closure = close_job_parents(jobs, admission)
        safe_counts = {
            "api_customers": len(api),
            "referenced_details": len(details),
            "control_assertions": len(controls),
            "customer_union": len(admission.candidates),
            "contacts": boundary.expected.contacts,
            "locations": boundary.expected.service_locations,
            "location_exceptions": sum(
                len(item.location_exception_ids) for item in admission.candidates
            ),
            "job_parent_references": len(closure.outcomes),
        }
        if admission.digest != EXPECTED_HYBRID_DIGEST:
            raise SafeEvidenceError(
                "hybrid_admission_authority_mismatch", admission.digest
            )
        if closure.digest != EXPECTED_PARENT_CLOSURE_DIGEST:
            raise SafeEvidenceError("parent_closure_authority_mismatch", closure.digest)
        if safe_counts != {
            "api_customers": 5253,
            "referenced_details": 43,
            "control_assertions": 5248,
            "customer_union": 5296,
            "contacts": 4148,
            "locations": 5339,
            "location_exceptions": 294,
            "job_parent_references": 5801,
        }:
            raise SafeEvidenceError(
                "source4_safe_count_authority_mismatch", canonical_sha256(safe_counts)
            )
        return VerifiedSource4CustomerComposition(
            package_digest=str(package_claim),
            collection_digest=str(collection_claim),
            admission=admission,
            parent_closure=closure,
            reviewed=reviewed,
            boundary=boundary,
            safe_counts=safe_counts,
        )

    @staticmethod
    def verify_owner_receipts(binding_root: Path) -> dict[str, str]:
        expected = {
            "HCP1A.BRANCH_SCOPE.V1",
            "HCP1A.CANCELED_BALANCE_JOBS.V1",
            "HCP1A.EMPLOYEE_CROSSWALK.V1",
            "HCP1A.RECENT_ZERO_BALANCE_CANCELED_JOBS.V1",
            "HCP1A.UNLINKED_DAY1_ESTIMATES.V1",
        }
        receipts: dict[str, str] = {}
        for path in sorted(binding_root.resolve().glob("*.json")):
            value = _safe_json(path)
            if not isinstance(value, dict):
                raise SafeEvidenceError("owner_receipt_shape_invalid", "6" * 64)
            binding = dict(value)
            receipt = binding.pop("receipt_digest", None)
            contract = binding.pop("contract", None)
            identifier = binding.get("group_identifier")
            actual = canonical_sha256(
                {"contract": "hcp-owner-disposition/v1", "binding": binding}
            )
            if (
                contract != "hcp-owner-disposition/v1"
                or not isinstance(identifier, str)
                or receipt != actual
            ):
                raise SafeEvidenceError(
                    "owner_receipt_invalid",
                    hashlib.sha256(path.name.encode()).hexdigest(),
                )
            receipts[identifier] = actual
        if set(receipts) != expected:
            raise SafeEvidenceError(
                "owner_receipt_set_incomplete", canonical_sha256(receipts)
            )
        return receipts


@dataclass(frozen=True)
class HcpMigration2ExecutionPlan:
    master: MasterRunCommand
    customers: VerifiedSource4CustomerComposition
    employees: tuple[EmployeeCandidateCommand, ...]
    jobs: tuple[JobMigrationRecord, ...]
    appointments: tuple[AppointmentMigrationRecord, ...]
    estimates: tuple[EstimateMigrationRecord, ...]
    unlinked_estimates: tuple[UnlinkedEstimateEvidenceCommand, ...]
    invoices: tuple[InvoiceMigrationRecord, ...]
    payments: tuple[PaymentMigrationRecord, ...]
    notes: tuple[HistoryMigrationRecord, ...]
    holds: tuple[HoldCommand, ...]
    plan_outcomes: tuple[PlanOutcomeCommand, ...]
    completion: CompletionRequirements
    verified_owner_receipts: dict[str, str]
    plan_id: UUID
    plan_digest: str
    builder_version: str

    def validate(self) -> None:
        if len(self.plan_digest) != 64 or not self.builder_version:
            raise SafeEvidenceError("execution_plan_identity_invalid", "0" * 64)
        if self.plan_id.int == 0:
            raise SafeEvidenceError("execution_plan_identity_invalid", self.plan_digest)
        required = {
            "customer",
            "contact",
            "service_location",
            "employee",
            "job",
            "appointment",
            "estimate",
            "invoice",
            "payment",
            "note",
            "hold",
            "unlinked_estimate",
        }
        if not required.issubset(self.master.source_counts):
            raise SafeEvidenceError(
                "execution_plan_domain_incomplete", self.plan_digest
            )
        if len({item.native_employee_id for item in self.employees}) != len(
            self.employees
        ):
            raise SafeEvidenceError(
                "execution_plan_employee_duplicate", self.plan_digest
            )
        for values in (
            self.jobs,
            self.appointments,
            self.estimates,
            self.invoices,
            self.payments,
            self.notes,
        ):
            identities = [item.source_id for item in values]
            if len(identities) != len(set(identities)):
                raise SafeEvidenceError(
                    "execution_plan_native_identity_duplicate", self.plan_digest
                )
        unlinked_identities = [
            item.native_estimate_id for item in self.unlinked_estimates
        ]
        if len(unlinked_identities) != len(set(unlinked_identities)):
            raise SafeEvidenceError(
                "execution_plan_native_identity_duplicate", self.plan_digest
            )
        actual_outcomes = Counter(
            (item.outcome, item.entity_kind) for item in self.plan_outcomes
        )
        expected_outcomes = Counter(
            {
                **{
                    ("EXPLICIT_EXCEPTION", key): value
                    for key, value in self.completion.exception_counts.items()
                    if key != "service_location" and value
                },
                **{
                    ("REJECTED", key): value
                    for key, value in self.completion.rejection_counts.items()
                    if value
                },
                **{
                    ("INTENTIONALLY_NON_APPLICABLE", key): value
                    for key, value in self.completion.non_applicable_counts.items()
                    if key != "employee" and value
                },
            }
        )
        if actual_outcomes != expected_outcomes:
            raise SafeEvidenceError(
                "execution_plan_outcome_accounting_incomplete", self.plan_digest
            )
        financial_metadata = [item.external_metadata for item in self.invoices] + [
            item.external_metadata for item in self.payments
        ]
        if any(
            metadata and metadata.get("accepted_accounting_truth") is not False
            for metadata in financial_metadata
        ):
            raise SafeEvidenceError(
                "execution_plan_financial_authority_invalid", self.plan_digest
            )
        self.completion.validate_reconciliation(self.master.source_counts)


class HcpMigration2Runner:
    """The sole executable SOURCE.4 lifecycle composition boundary."""

    def __init__(self, orchestrator: HcpMigration2Orchestrator | None = None) -> None:
        self.orchestrator = orchestrator or HcpMigration2Orchestrator()

    async def execute(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
        plan: HcpMigration2ExecutionPlan,
        successor_manifest: QualifiedSuccessorManifest | None = None,
    ) -> dict[str, object]:
        try:
            return await self._execute(
                factory,
                context=context,
                target=target,
                plan=plan,
                successor_manifest=successor_manifest,
            )
        except SafeEvidenceError:
            raise
        except Exception as error:
            raise SafeEvidenceError(
                "source4_runner_failed",
                hashlib.sha256(type(error).__qualname__.encode()).hexdigest(),
            ) from error

    async def _execute(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
        plan: HcpMigration2ExecutionPlan,
        successor_manifest: QualifiedSuccessorManifest | None,
    ) -> dict[str, object]:
        plan.validate()
        reuse_targets: dict[tuple[str, str], UUID] = {}
        if successor_manifest is not None:
            successor_manifest.verify()
            if context.active_branch is None or (
                successor_manifest.company_id != str(context.company.id)
                or successor_manifest.branch_id != str(context.active_branch.id)
            ):
                raise SafeEvidenceError(
                    "successor_manifest_scope_mismatch", successor_manifest.digest
                )
            expected = {
                ("customer", row.source_identity)
                for row in plan.customers.reviewed.aggregates
            }
            expected.update(
                ("contact", row.source_identity)
                for row in plan.customers.reviewed.aggregates
                if row.contact is not None
            )
            expected.update(
                ("service_location", source_id)
                for row in plan.customers.reviewed.aggregates
                for source_id in row.service_location_source_identities
            )
            for domain in ("jobs", "appointments", "estimates", "invoices", "payments"):
                expected.update(
                    (domain.removesuffix("s"), row.source_id)
                    for row in getattr(plan, domain)
                )
            actual = {(item.domain, item.source_id) for item in successor_manifest.entries}
            if expected != actual:
                raise SafeEvidenceError(
                    "successor_manifest_population_mismatch",
                    successor_manifest.digest,
                )
            if any(
                item.disposition
                in {AdmissionDisposition.HOLD_AMBIGUOUS, AdmissionDisposition.CONFLICT}
                for item in successor_manifest.entries
            ):
                raise SafeEvidenceError(
                    "successor_manifest_not_executable", successor_manifest.digest
                )
            reuse_targets = {
                (item.domain, item.source_id): UUID(item.native_id)
                for item in successor_manifest.entries
                if item.disposition is AdmissionDisposition.REUSE_EXACT_SUCCESSOR
                and item.native_id is not None
            }
            async with factory() as preflight_session:
                await qualify_reuse_graph(
                    preflight_session,
                    company_id=str(context.company.id),
                    branch_id=str(context.active_branch.id),
                    plan=plan,
                    manifest=successor_manifest,
                )
                await preflight_session.rollback()
        if plan.master.owner_receipts != plan.verified_owner_receipts:
            raise SafeEvidenceError(
                "master_owner_receipt_binding_mismatch",
                canonical_sha256(plan.verified_owner_receipts),
            )
        if (
            plan.master.package_digest != plan.customers.package_digest
            or plan.master.transformation_contracts.get(
                "hybrid_customer_admission_digest"
            )
            != plan.customers.admission.digest
            or plan.master.transformation_contracts.get(
                "customer_parent_closure_digest"
            )
            != plan.customers.parent_closure.digest
        ):
            raise SafeEvidenceError(
                "master_source4_composition_binding_mismatch",
                canonical_sha256(
                    plan.master.input_payload(
                        company_id=context.company.id,
                        branch_id=context.active_branch.id
                        if context.active_branch
                        else UUID(int=0),
                        actor_id=context.user.id,
                    )
                ),
            )
        async with factory() as session, session.begin():
            master, created = await self.orchestrator.start_or_resume(
                session, context=context, target=target, command=plan.master
            )
            staging = await self.orchestrator.stage_customers(
                session,
                context=context,
                master_run_id=master.id,
                reviewed=plan.customers.reviewed,
                hybrid_admission=plan.customers.admission,
            )
            master_id = master.id
            input_digest = master.input_digest
        customer_report = await self.orchestrator.run_customers(
            factory,
            context=context,
            master_run_id=master_id,
            reviewed=plan.customers.reviewed,
            boundary=plan.customers.boundary,
            hybrid_admission=plan.customers.admission,
            parent_closure=plan.customers.parent_closure,
            successor_manifest=successor_manifest,
        )
        async with factory() as session, session.begin():
            for employee_command in plan.employees:
                await self.orchestrator.persist_employee_candidate(
                    session,
                    context=context,
                    master_run_id=master_id,
                    command=employee_command,
                )
        operational = await self.orchestrator.run_operational(
            factory,
            context=context,
            master_run_id=master_id,
            jobs=plan.jobs,
            appointments=plan.appointments,
            reuse_targets=reuse_targets,
        )
        async with factory() as session, session.begin():
            for estimate_command in plan.unlinked_estimates:
                await self.orchestrator.persist_unlinked_estimate(
                    session,
                    context=context,
                    master_run_id=master_id,
                    command=estimate_command,
                )
        financial = await self.orchestrator.run_financial(
            factory,
            context=context,
            master_run_id=master_id,
            estimates=plan.estimates,
            invoices=plan.invoices,
            payments=plan.payments,
            reuse_targets=reuse_targets,
        )
        history = await self.orchestrator.run_history(
            factory,
            context=context,
            master_run_id=master_id,
            notes=plan.notes,
        )
        async with factory() as session, session.begin():
            expected_customer = len(plan.customers.admission.candidates)
            customer_actual = ChildOutcomeCounts(
                customer_report.attempted,
                customer_report.accepted,
                customer_report.rejected,
                customer_report.duplicate,
                customer_report.attempted
                - customer_report.accepted
                - customer_report.rejected
                - customer_report.duplicate,
            )
            reports = {
                "operational": (operational, len(plan.jobs) + len(plan.appointments)),
                "financial": (
                    financial,
                    len(plan.estimates) + len(plan.invoices) + len(plan.payments),
                ),
                "history": (history, len(plan.notes)),
            }
            await self.orchestrator.admit_child_outcome(
                session,
                context=context,
                master_run_id=master_id,
                child_run_id=UUID(str(customer_report.run_id)),
                domain="customer",
                plan_digest=plan.plan_digest,
                execution_status="completed",
                expected=ChildOutcomeCounts(
                    expected_customer, expected_customer, 0, 0, 0
                ),
                actual=customer_actual,
                reason_code="validated_plan_outcome_comparison",
            )
            for domain, (report, expected_source) in reports.items():
                await self.orchestrator.admit_child_outcome(
                    session,
                    context=context,
                    master_run_id=master_id,
                    child_run_id=report.run_id,
                    domain=domain,
                    plan_digest=plan.plan_digest,
                    execution_status="completed",
                    expected=ChildOutcomeCounts(
                        expected_source, expected_source, 0, 0, 0
                    ),
                    actual=ChildOutcomeCounts(
                        report.source,
                        report.accepted,
                        report.rejected,
                        report.duplicate,
                        report.unresolved,
                    ),
                    reason_code="validated_plan_outcome_comparison",
                )
        async with factory() as session, session.begin():
            for hold_command in plan.holds:
                await self.orchestrator.persist_held_subject(
                    session,
                    context=context,
                    master_run_id=master_id,
                    command=hold_command,
                )
            for outcome_command in plan.plan_outcomes:
                await self.orchestrator.persist_plan_outcome(
                    session,
                    context=context,
                    master_run_id=master_id,
                    command=outcome_command,
                )
            completed = await self.orchestrator.complete(
                session,
                context=context,
                master_run_id=master_id,
                expected_input_digest=input_digest,
                requirements=plan.completion,
            )
        return {
            "contract": RUNNER_VERSION,
            "master_run_id": str(master_id),
            "master_created": created,
            "master_status": completed.status,
            "staging_digest": staging.staging_digest,
            "customer_run_id": customer_report.run_id,
            "operational_run_id": str(operational.run_id),
            "financial_run_id": str(financial.run_id),
            "history_run_id": str(history.run_id),
            "safe_counts": plan.customers.safe_counts,
        }
