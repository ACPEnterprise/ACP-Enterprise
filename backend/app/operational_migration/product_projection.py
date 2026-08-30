from __future__ import annotations

from dataclasses import asdict, dataclass

HCP_MASTER_ID = "63273602-8619-5c0b-8b49-8537338b04b5"
HCP_DIGEST = "74b9b902a95fd9890881d2df478ac79190622f54abc33fa5f7a83a198bc86d5f"
QBO_FIXTURE_DIGEST = "788eb41cf475022c258505a109bf0e1845f0ade37a7c965c34c3ddda3551efb1"
QBO_DIGEST = "c14919b06cc1f9dfa5d93db430ca82b20afd3f28d0554f1d49d804f7b2288d75"


@dataclass(frozen=True)
class DomainCount:
    domain: str
    source: int
    migrated: int = 0
    held: int = 0
    exception: int = 0
    non_applicable: int = 0
    deferred: int = 0
    unresolved: int = 0

    @property
    def delta(self) -> int:
        return self.source - sum(
            (
                self.migrated,
                self.held,
                self.exception,
                self.non_applicable,
                self.deferred,
                self.unresolved,
            )
        )


def build_migration_product_projection(
    *, company_id: str, branch_id: str | None, qbo_sandbox_connected: bool
) -> dict[str, object]:
    counts = (
        DomainCount("Customers", 5296, 5296),
        DomainCount("Contacts", 4148, 4148),
        DomainCount("Locations", 5633, 5339, exception=294),
        DomainCount("Employees", 7, 6, non_applicable=1),
        DomainCount("Jobs", 5801, 1094, held=296, exception=4411),
        DomainCount("Appointments", 3219, 1249, exception=1970),
        DomainCount(
            "Estimates", 1307, 14, exception=31, non_applicable=1238, deferred=24
        ),
        DomainCount(
            "Invoices",
            5756,
            663,
            held=298,
            exception=4587,
            non_applicable=91,
            deferred=117,
        ),
        DomainCount("Payments", 4308, 684, exception=3337, non_applicable=287),
        DomainCount("Notes", 2640, exception=2640),
        DomainCount("QBO Accounts", 53, 53),
        DomainCount("QBO Vendors", 1, 1),
        DomainCount("QBO Items", 4, 4),
        DomainCount("QBO Bills/AP", 2, 2),
        DomainCount("QBO Journals", 2, 2),
    )
    timeline = (
        "Preflight",
        "Pre-cutover acquisition",
        "Reconciliation",
        "Owner readiness",
        "Source freeze",
        "Final HCP/QBO deltas",
        "Final reconciliation",
        "Go/No-Go",
        "Activation eligibility",
    )
    decisions = (
        "Chart of Accounts mapping",
        "Historical acquisition start",
        "Opening evidence",
        "Customer overlap",
        "Invoice overlap",
        "Payment overlap",
        "AR/AP authority",
        "Bank/cash authority",
        "Payroll/tax liability authority",
        "Cross-source conflicts",
        "HCP source freeze",
        "Final go/no-go",
    )
    decision_packets = (
        {
            "decision_id": "HCP.FINAL.EMPLOYEE_CROSSWALK",
            "question": "Do all final-delta technician identities retain an approved ACP Employee mapping?",
            "current_evidence": "Seven sealed source identities; six accepted employee candidates carry 1,825 relevant historical assignments.",
            "options": ("confirm_existing_mapping", "authorize_candidate", "hold_assignments"),
            "recommended_default": None,
            "risk": "An unresolved identity blocks affected assignments and open-work admission.",
            "unlocks": "Employee and technician-bound final-delta reconciliation.",
            "state": "owner_decision_required_at_final_delta",
        },
        {
            "decision_id": "HCP.FINAL.BRANCH_CROSSWALK",
            "question": "Does the sealed Plumbing/no-business-unit mapping remain valid for the final delta?",
            "current_evidence": "The rehearsal bound the source Plumbing unit and missing-unit pattern to its approved isolated Branch; live target identity must be re-authorized.",
            "options": ("confirm_target_branch", "hold_unmapped_open_work"),
            "recommended_default": None,
            "risk": "Inventing a Branch would cause cross-scope operational persistence.",
            "unlocks": "Branch-scoped open Jobs, Appointments, Estimates, and assignments.",
            "state": "owner_decision_required_at_final_delta",
        },
        {
            "decision_id": "HCP.CANCELED_BALANCE_JOBS",
            "question": "How should canceled Jobs with source-reported balances be treated after HCP/QBO reconciliation?",
            "current_evidence": "296 source Jobs are preserved on HOLD with nonzero balance assertions.",
            "options": ("retain_hold", "admit_after_accounting_reconciliation", "explicit_exception"),
            "recommended_default": "retain_hold",
            "risk": "Treating disputed balances as ACP economic truth may create false AR or work.",
            "unlocks": "Final disposition of the Job and related financial evidence.",
            "state": "owner_decision_required",
        },
        {
            "decision_id": "HCP.UNLINKED_ESTIMATES",
            "question": "How should Day-1 Estimate evidence without an authoritative Job relationship be carried?",
            "current_evidence": "Twenty-four accepted unlinked Estimate evidence rows are preserved without a fabricated Job link.",
            "options": ("retain_evidence_only", "link_with_authoritative_job_evidence", "explicit_exception"),
            "recommended_default": "retain_evidence_only",
            "risk": "A guessed Job link would corrupt operational and profitability lineage.",
            "unlocks": "Final Estimate disposition without weakening the native Job relationship.",
            "state": "mechanically_ready",
        },
    )
    hcp_exception_count = sum(item.exception for item in counts)
    return {
        "company_id": company_id,
        "branch_id": branch_id,
        "scope": "branch" if branch_id is not None else "company",
        "overall_status": "external_owner_gate",
        "current_phase": "owner_ready",
        "authority_digest": HCP_DIGEST,
        "reconciliation_digest": QBO_DIGEST,
        "stale": False,
        "safe_failure_code": None,
        "go_no_go": {
            "state": "external_auth_required",
            "activation_eligible": False,
            "blockers": (
                "real_qbo_authorization_required",
                "real_hcp_final_delta_required",
                "source_freeze_evidence_required",
                "opening_evidence_required",
                "owner_policy_decisions_required",
            ),
        },
        "historical_window": {
            "starts_on": None,
            "ends_on": "2026-08-30",
            "opening_evidence_state": "owner_decision_required",
            "completeness": "configuration_required",
        },
        "sources": (
            {
                "source": "HCP",
                "environment": "protected_rehearsal",
                "status": "external_owner_gate",
                "connection_state": "rehearsal_complete_replay_verified",
                "acquisition_state": "baseline_complete",
                "manifest_state": "sealed",
                "delta_state": "external_authorization_required",
                "freeze_state": "not_frozen",
                "authority_digest": HCP_DIGEST,
            },
            {
                "source": "QBO Development",
                "environment": "sandbox",
                "status": "ready" if qbo_sandbox_connected else "incomplete",
                "connection_state": "active_verified"
                if qbo_sandbox_connected
                else "unavailable",
                "acquisition_state": "representative_history_reconciled",
                "manifest_state": "sealed_replay_verified",
                "delta_state": "controlled_change_verified",
                "freeze_state": "not_applicable",
                "authority_digest": QBO_FIXTURE_DIGEST,
            },
            {
                "source": "QBO Production",
                "environment": "production_disabled",
                "status": "external_owner_gate",
                "connection_state": "external_authorization_required",
                "acquisition_state": "not_started",
                "manifest_state": "not_available",
                "delta_state": "not_started",
                "freeze_state": "not_frozen",
                "authority_digest": QBO_DIGEST,
            },
        ),
        "counts": tuple({**asdict(item), "delta": item.delta} for item in counts),
        "timeline": tuple(
            {"phase": phase, "status": "ready" if index < 3 else "external_owner_gate"}
            for index, phase in enumerate(timeline)
        ),
        "authority_states": (
            {"fact": "HCP operational history", "state": "hcp_authoritative"},
            {"fact": "QBO accounting history", "state": "qbo_authoritative"},
            {"fact": "Native destination", "state": "acp_native_authoritative"},
            {"fact": "Real overlap", "state": "unresolved"},
        ),
        "owner_decisions": tuple(
            {"decision": decision, "state": "owner_decision_required"}
            for decision in decisions
        ),
        "decision_packets": decision_packets,
        "freeze_authority": {
            "state": "external_authorization_required",
            "required_authority": "owner_go_no_go_actor",
            "sources": ("HCP", "QBO Production"),
            "evidence": "immutable_source_timestamps_and_manifest_digests",
            "late_change_behavior": "invalidate_delta_and_return_to_reconciliation",
            "reopen_behavior": "new_freeze_generation_required",
        },
        "run_history": (
            {
                "run_id": HCP_MASTER_ID,
                "source": "HCP",
                "state": "completed",
                "reconciliation": "plan_conforming",
                "replay": "verified",
                "holds": 594,
                "exceptions": hcp_exception_count,
            },
            {
                "run_id": QBO_FIXTURE_DIGEST[:32],
                "source": "QBO Development",
                "state": "completed",
                "reconciliation": "zero_delta",
                "replay": "verified",
                "holds": 0,
                "exceptions": 0,
            },
        ),
        "recovery_state": "completed_runs_replay_safe; final_sources_not_authorized",
    }
