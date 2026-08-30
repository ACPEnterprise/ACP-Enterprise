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
    *, company_id: str, branch_id: str, qbo_sandbox_connected: bool
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
    return {
        "company_id": company_id,
        "branch_id": branch_id,
        "overall_status": "external_owner_gate",
        "current_phase": "owner_ready",
        "authority_digest": HCP_DIGEST,
        "reconciliation_digest": QBO_DIGEST,
        "stale": False,
        "safe_failure_code": None,
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
        "run_history": (
            {
                "run_id": HCP_MASTER_ID,
                "source": "HCP",
                "state": "completed",
                "reconciliation": "plan_conforming",
                "replay": "verified",
                "holds": 594,
                "exceptions": 12970,
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
