"""Deterministic non-production operating-day acceptance orchestrator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

SCENARIO_VERSION: Final = "ENTERPRISE.OPERATIONAL.ACCEPTANCE.FACTORY.v1"
ALLOWED_CLASSIFICATIONS: Final = {
    "PASSED",
    "PASSED_WITH_EXTERNAL_GATE",
    "POLICY_REQUIRED",
    "SOURCE_REQUIRED",
    "DEPENDENCY_BLOCKED",
    "ACTIVE_OWNER_DEFERRED",
}


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    persona: str
    expected: str
    test_nodes: tuple[str, ...] = ()
    gate_classification: str | None = None
    limitation: str | None = None


SCENARIOS: Final[tuple[Scenario, ...]] = (
    Scenario("new_customer_call", "SERVICE_CSR", "idempotent tenant-scoped intake and evidence", ("tests/customers/test_launch_gaps.py::test_launch_intake_duplicate_note_consent_and_location_workflow",)),
    Scenario("existing_customer_call", "SERVICE_CSR", "bounded scoped search and context", ("tests/customers/test_search_timeline.py::test_customer_search_and_timeline_are_tenant_and_permission_scoped",)),
    Scenario("job_creation", "SERVICE_CSR", "one scoped Job and Event under replay", ("tests/jobs/test_jobs_api.py::test_job_create_concurrent_replay_and_contradiction",)),
    Scenario("scheduling", "DISPATCHER", "schedule, reschedule, cancel and stale rejection", ("tests/scheduling/test_scheduling_service.py::test_launch_workflow_links_retries_reschedules_cancels_and_reopens", "tests/scheduling/test_scheduling_service.py::test_reschedule_moves_capacity_and_rejects_stale_version")),
    Scenario("dispatch", "DISPATCHER", "assignment readiness, audit and release", ("tests/dispatch/test_dispatch_service.py::test_assignment_is_idempotent_audited_and_releasable", "tests/dispatch/test_dispatch_service.py::test_missing_availability_is_reported_unknown")),
    Scenario("employee_readiness", "COMPANY_ADMINISTRATOR", "explicit role, Branch, capability and credential evidence", ("tests/workforce/test_operations_projection.py::test_readiness_uses_explicit_capability_credential_and_branch_evidence",)),
    Scenario("mobile_my_day", "TECHNICIAN", "self-resolved bounded current assignments", ("tests/employee_operations/test_my_day_projection.py::test_employee_sees_primary_and_active_crew_assignments", "tests/employee_operations/test_my_day_projection.py::test_projection_contains_only_bounded_operational_fields")),
    Scenario("on_my_way_arrival", "TECHNICIAN", "one arrival authority and assigned-employee enforcement", ("tests/dispatch/test_dispatch_service.py::test_arrival_and_controlled_exception_evidence_is_idempotent", "tests/dispatch/test_dispatch_service.py::test_unassigned_employee_cannot_record_arrival")),
    Scenario("communications_intent", "SERVICE_CSR", "one consent-bound logical intent under replay", ("tests/communications/test_launch_communications.py::test_request_is_structured_consent_checked_and_idempotent",)),
    Scenario("communications_provider_truth", "OFFICE_MANAGER", "accepted, rejected and uncertain delivery remain distinct", ("tests/communications/test_transactional_delivery.py::test_synthetic_provider_outcomes_map_to_truthful_lifecycle", "tests/communications/test_transactional_delivery.py::test_provider_acceptance_without_reference_becomes_uncertain")),
    Scenario("timekeeping", "TECHNICIAN", "employee-owned punch and independent approved workday", ("tests/timekeeping/test_workday_authority.py::test_manual_entry_requires_authority_and_punch_is_employee_owned", "tests/timekeeping/test_workday_authority.py::test_phone_safe_api_manual_first_idempotency_and_payroll_snapshot")),
    Scenario("assets_equipment", "TECHNICIAN", "equipment identity and service-history evidence without inference", ("tests/operational_assets/test_operational_assets.py::test_unknown_customer_equipment_evidence_does_not_block_identity", "tests/operational_assets/test_operational_assets.py::test_typed_action_exact_replay_and_contradiction")),
    Scenario("fleet", "TECHNICIAN", "vehicle readiness fails closed without configured evidence", ("tests/operational_assets/test_operational_assets.py::test_vehicle_readiness_fails_closed_without_identity_evidence", "tests/operational_assets/test_operational_assets.py::test_failed_vehicle_check_creates_attention_not_safety_inference")),
    Scenario("price_book", "SERVICE_CSR", "authorized scoped retrieval and immutable snapshot", ("tests/price_book/test_price_book_service.py::test_branch_and_company_scope_fail_closed", "tests/estimates/test_estimate_foundation.py::test_create_uses_immutable_price_book_snapshot")),
    Scenario("estimate", "SERVICE_CSR", "revision, decision, stale and replay safety", ("tests/estimates/test_estimate_workflow.py::test_revision_lineage_is_deterministic_and_historical_revision_survives", "tests/estimates/test_estimate_workflow.py::test_stale_version_fails_closed")),
    Scenario("estimate_declined", "SERVICE_CSR", "decline persists without conversion inference", ("tests/estimates/test_estimate_workflow.py::test_rejection_requires_and_preserves_reason", "tests/estimates/test_estimate_conversion.py::test_conversion_requires_approved_estimate")),
    Scenario("estimate_delivery", "SERVICE_CSR", "delivery binds exact artifact digest", ("tests/communications/test_transactional_delivery.py::test_document_notice_binds_exact_artifact_digest_without_path",)),
    Scenario("field_evidence_completion", "TECHNICIAN", "snapshot, blockers, completion and replay converge", ("tests/field_service/test_field_service_conformance.py::test_field_evidence_snapshot_replay_events_and_non_billable_completion", "tests/field_service/test_field_service_conformance.py::test_stale_field_versions_fail_closed")),
    Scenario("invoice", "OFFICE_MANAGER", "accepted work creates one scoped receivable", ("tests/invoicing/test_invoice_ar.py::test_accepted_work_creates_and_issues_one_exact_receivable", "tests/invoicing/test_invoice_ar.py::test_company_branch_and_source_linkage_are_closed")),
    Scenario("stale_invoice", "OFFICE_MANAGER", "stale mutation fails closed", ("tests/invoicing/test_invoice_ar.py::test_stale_invoice_mutation_fails_closed",)),
    Scenario("payment_same_day", "OFFICE_MANAGER", "one collection/application authority under concurrency", ("tests/payments/test_payment_service_concurrency.py::test_concurrent_collection_and_refund_replay_have_one_economic_authority", "tests/payments/test_payment_service_concurrency.py::test_concurrent_identical_application_changes_receipt_once")),
    Scenario("payment_partial", "OFFICE_MANAGER", "partial application conserves receipt and open balance", ("tests/invoicing/test_invoice_ar.py::test_verified_receipt_application_and_accounting_receipt_seams",)),
    Scenario("payment_uncertain", "OFFICE_MANAGER", "possible provider acceptance requires reconciliation", ("tests/payments/test_payment_service_concurrency.py::test_ambiguous_provider_outcome_is_reconciled_without_blind_retry",)),
    Scenario("cash_ar_distinction", "OFFICE_MANAGER", "invoice, payment, settlement and cash remain distinct", ("tests/lia/test_cash_operational_adapter.py::test_lia_adapter_explains_separation_without_exposing_amounts", "tests/business_economics/test_owner_acceptance.py")),
    Scenario("vendor_ap", "OFFICE_MANAGER", "Vendor obligation, application and settlement conserve amounts", ("tests/accounts_payable/test_concurrency.py::test_concurrent_disbursement_replay_has_one_application_and_conserves_amounts",)),
    Scenario("inventory_material", "OFFICE_MANAGER", "receipt/movement/reservation preserve quantity and Branch scope", ("tests/inventory/test_inventory_foundation.py::test_concurrent_exact_movement_replay_has_one_authoritative_winner", "tests/inventory/test_inventory_application.py::test_repository_lists_do_not_leak_other_branches")),
    Scenario("service_agreement", "OFFICE_MANAGER", "versioned lifecycle and replay evidence", ("tests/service_agreements/test_service_agreements.py",)),
    Scenario("customer_communication_history", "SERVICE_CSR", "bounded Company/Branch/Customer history", ("tests/communications/test_launch_communications.py::test_history_preserves_company_branch_and_customer_scope",)),
    Scenario("owner_operations", "COMPANY_ADMINISTRATOR", "owner projection reflects supported evidence without fabrication", ("tests/business_economics/test_owner_workspace.py::test_owner_projection_reconciles_jobs_rollups_and_losses",)),
    Scenario("economics", "COMPANY_ADMINISTRATOR", "work, obligations and cash readiness remain distinct", ("tests/business_economics/test_owner_acceptance.py", "tests/business_economics/test_evidence_acceptance.py::test_workday_and_job_participation_are_distinct_reconcilable_contracts")),
    Scenario("luminary", "COMPANY_ADMINISTRATOR", "briefing requires read authority and avoids unsupported causality", ("tests/luminary/test_api_boundary.py::test_analyze_permission_does_not_imply_luminary_read", "tests/business_economics/test_owner_acceptance.py")),
    Scenario("beacon", "OFFICE_MANAGER", "existing signal replay and tenant evidence binding", ("tests/beacon/test_workflow.py::test_exact_replay_uses_durable_event_without_re_evaluating_signal", "tests/beacon/test_native_financial_signals.py::test_company_branch_and_evidence_bind_identity")),
    Scenario("lia", "OFFICE_MANAGER", "bounded read-only answers preserve evidence distinctions", ("tests/lia/test_governed_assistant.py", "tests/lia/test_cash_operational_adapter.py")),
    Scenario("audit_events", "COMPANY_ADMINISTRATOR", "traceability is scoped, replay-safe and payload-safe", ("tests/events/test_router_security.py::test_event_reads_are_company_and_authorized_branch_scoped", "tests/audit_completeness/test_audit_completeness.py::test_company_and_branch_binding_reject_cross_scope_evidence")),
    Scenario("reschedule_stale_communication", "DISPATCHER", "reschedule creates current version and stale commands fail", ("tests/scheduling/test_scheduling_api.py::test_reschedule_moves_reservation_and_stages_event", "tests/communications/test_launch_communications.py::test_replayed_identity_with_changed_inputs_fails_closed")),
    Scenario("cancellation", "DISPATCHER", "versioned cancellation releases capacity and retains truth", ("tests/scheduling/test_scheduling_api.py::test_cancellation_is_versioned_idempotent_and_releases_capacity", "tests/jobs/test_jobs_api.py::test_cancel_and_reopen_are_exposed")),
    Scenario("backend_outage_recovery", "TECHNICIAN", "failure rollback and replay do not duplicate mutation", ("tests/scheduling/test_scheduling_service.py::test_event_staging_failure_rolls_back_appointment_and_reservation", "tests/jobs/test_jobs_service.py::test_event_failure_rolls_back_job_number_and_all_persistence")),
    Scenario("response_loss", "OFFICE_MANAGER", "commit plus retry converges on one authority", ("tests/payments/test_payment_service_concurrency.py::test_concurrent_identical_application_changes_receipt_once", "tests/communications/test_transactional_delivery.py::test_exact_synthetic_delivery_preserves_logical_identity")),
    Scenario("permission_revoked", "OFFICE_MANAGER", "reopened context reauthorizes permission and version", ("tests/lia/test_foundation_safety.py::test_conversation_reopen_reauthorizes_permission_branch_and_membership_version",)),
    Scenario("branch_revoked", "DISPATCHER", "foreign or removed Branch fails closed", ("tests/scheduling/test_scheduling_api.py::test_create_conceals_tenant_and_branch_references", "tests/employee_operations/test_my_day_projection.py::test_branch_scope_is_passed_unchanged")),
    Scenario("membership_deactivated", "RESTRICTED_EMPLOYEE", "inactive Membership loses server authority", ("tests/platform/test_authorization_service.py::test_inactive_identity_and_tenant_states_are_rejected",)),
    Scenario("rapid_actions", "OFFICE_MANAGER", "representative create/transition/apply operations converge", ("tests/customers/test_api.py::test_customer_create_replay_conflict_and_company_scope", "tests/jobs/test_jobs_service.py::test_concurrent_lifecycle_transition_has_one_authoritative_winner", "tests/scheduling/test_scheduling_service.py::test_concurrent_idempotent_creation_returns_one_appointment")),
    Scenario("tenant_attack", "RESTRICTED_EMPLOYEE", "foreign tenant and Branch identities are concealed", ("tests/isolation/test_isolation_property_suite.py", "tests/customers/test_launch_gaps.py::test_launch_endpoints_hide_other_company_customer")),
    Scenario("persona_attack", "RESTRICTED_EMPLOYEE", "positive and negative permission composition remains explicit", ("tests/platform/test_permission_explainability_product.py", "tests/jobs/test_jobs_api.py::test_management_endpoint_permission_matrix")),
    Scenario("error_safety", "RESTRICTED_EMPLOYEE", "no internal detail is reflected", ("tests/platform/test_sensitive_output_controls.py", "tests/platform/test_enterprise_security_hardening.py")),
    Scenario("migration_readiness", "COMPANY_ADMINISTRATOR", "synthetic readiness remains deterministic and fail closed", ("tests/customer_migration/test_dry_run_readiness.py::test_manifest_is_immutable_deterministic_tenant_scoped_and_complete",)),
    Scenario("redis_failure", "COMPANY_ADMINISTRATOR", "rate limiting fails closed without required Redis", gate_classification="DEPENDENCY_BLOCKED", limitation="Supported Redis service unavailable on this host; no in-memory authority substituted."),
    Scenario("communications_readiness", "COMPANY_ADMINISTRATOR", "governed channel selection and provider admission remain truthful", ("tests/communications/test_omnichannel_operations.py",)),
    Scenario("real_communications_provider", "OFFICE_MANAGER", "provider delivery acceptance", gate_classification="PASSED_WITH_EXTERNAL_GATE", limitation="Synthetic provider qualified; real email/SMS prohibited."),
    Scenario("physical_mobile", "TECHNICIAN", "physical-device workflow", gate_classification="PASSED_WITH_EXTERNAL_GATE", limitation="Server and Jest contracts qualified; physical device owned externally."),
    Scenario("real_migration_source", "COMPANY_ADMINISTRATOR", "protected source acquisition", gate_classification="SOURCE_REQUIRED", limitation="Real QBO/HCP access prohibited."),
    Scenario("asset_policy", "COMPANY_ADMINISTRATOR", "authoritative import and readiness policy classify without inference", ("tests/operational_assets/test_operational_assets.py::test_vehicle_with_powertrain_still_requires_configured_readiness_policy", "tests/operational_assets/test_operational_assets.py::test_import_classification_preserves_replacement_and_conflict")),
)


def _digest_output(output: str) -> str:
    return hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest()


def run(*, authority_sha: str, schema_head: str, output_path: Path) -> int:
    started = time.time()
    results: list[dict[str, object]] = []
    failures = 0
    environment = os.environ.copy()
    environment.setdefault("ENVIRONMENT", "test")
    environment.setdefault("PYTHONPATH", ".")
    for scenario in SCENARIOS:
        if scenario.gate_classification:
            classification = scenario.gate_classification
            result = "GATED"
            duration_ms = 0
            evidence_digest = _digest_output(
                f"{scenario.scenario_id}:{classification}:{scenario.limitation}"
            )
        else:
            scenario_started = time.perf_counter()
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", *scenario.test_nodes],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            duration_ms = round((time.perf_counter() - scenario_started) * 1000)
            combined = f"{completed.stdout}\n{completed.stderr}"
            evidence_digest = _digest_output(combined)
            result = "PASS" if completed.returncode == 0 else "FAIL"
            classification = "PASSED" if completed.returncode == 0 else "FAILED"
            failures += completed.returncode != 0
        results.append(
            {
                **asdict(scenario),
                "classification": classification,
                "actual_result": result,
                "duration_ms": duration_ms,
                "evidence_digest": evidence_digest,
            }
        )
    evidence = {
        "scenario_version": SCENARIO_VERSION,
        "authority_sha": authority_sha,
        "schema_head": schema_head,
        "execution_environment": "ISOLATED_NON_PRODUCTION",
        "executed_at_epoch": round(started),
        "duration_ms": round((time.time() - started) * 1000),
        "summary": {
            "total": len(results),
            "passed": sum(item["classification"] == "PASSED" for item in results),
            "gated": sum(item["actual_result"] == "GATED" for item in results),
            "failed": failures,
        },
        "scenarios": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", required=True)
    parser.add_argument("--schema-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return run(
        authority_sha=args.authority,
        schema_head=args.schema_head,
        output_path=args.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
