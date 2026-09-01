from __future__ import annotations

import json

from app.operational_migration.product_projection import (
    HCP_MASTER_ID,
    build_migration_product_projection,
)


def projection(*, connected: bool = True) -> dict[str, object]:
    return build_migration_product_projection(
        company_id="company-a",
        branch_id="branch-a",
        qbo_sandbox_connected=connected,
    )


def test_projection_is_scoped_safe_and_reconciled() -> None:
    result = projection()
    assert result["company_id"] == "company-a"
    assert result["branch_id"] == "branch-a"
    assert result["scope"] == "branch"
    assert result["overall_status"] == "external_owner_gate"
    counts = result["counts"]
    assert isinstance(counts, tuple)
    assert all(item["delta"] == 0 for item in counts)
    rendered = json.dumps(result, sort_keys=True).lower()
    for protected_term in (
        "client_secret",
        "access_token",
        "refresh_token",
        "customer_name",
        "email",
        "phone",
        "address",
    ):
        assert protected_term not in rendered


def test_projection_truthfully_distinguishes_source_gates() -> None:
    sources = {item["source"]: item for item in projection()["sources"]}
    assert sources["HCP"]["connection_state"] == "rehearsal_complete_replay_verified"
    assert sources["HCP"]["delta_state"] == "external_authorization_required"
    assert sources["QBO Development"]["status"] == "ready"
    assert sources["QBO Development"]["environment"] == "sandbox"
    assert sources["QBO Production"]["status"] == "external_owner_gate"
    assert sources["QBO Production"]["environment"] == "production_disabled"


def test_unavailable_sandbox_never_fabricates_connection_readiness() -> None:
    sources = {item["source"]: item for item in projection(connected=False)["sources"]}
    assert sources["QBO Development"]["status"] == "incomplete"
    assert sources["QBO Development"]["connection_state"] == "unavailable"


def test_bounded_real_qbo_snapshot_is_visible_but_not_promoted() -> None:
    result = build_migration_product_projection(
        company_id="company-a",
        branch_id="branch-a",
        qbo_sandbox_connected=True,
        qbo_production_connected=True,
        qbo_production_snapshot={
            "state": "BOUNDED_COMPLETE",
            "accounting_date_cutoff": "2026-08-31",
            "bounded_snapshot_sha256": "a" * 64,
            "included_counts": {"invoice": 12, "payment": 9},
            "excluded_post_cutoff_counts": {"deposit": 1},
        },
    )
    sources = {item["source"]: item for item in result["sources"]}
    production = sources["QBO Production"]
    assert production["connection_state"] == "active_verified"
    assert production["acquisition_state"] == "bounded_complete"
    assert production["post_cutoff_exclusions"] == {"deposit": 1}
    assert result["historical_window"]["ends_on"] == "2026-08-31"
    assert "real_qbo_reconciliation_required" in result["go_no_go"]["blockers"]
    real_counts = {
        item["domain"]: item
        for item in result["counts"]
        if item["domain"].startswith("Real QBO")
    }
    assert real_counts["Real QBO Invoice"]["deferred"] == 12
    assert real_counts["Real QBO Invoice"]["migrated"] == 0
    assert real_counts["Real QBO Invoice"]["delta"] == 0


def test_company_wide_review_does_not_fabricate_branch_scope() -> None:
    result = build_migration_product_projection(
        company_id="company-a",
        branch_id=None,
        qbo_sandbox_connected=True,
    )
    assert result["company_id"] == "company-a"
    assert result["branch_id"] is None
    assert result["scope"] == "company"


def test_owner_decisions_history_and_opening_gate_remain_visible() -> None:
    result = projection()
    decisions = {item["decision"] for item in result["owner_decisions"]}
    assert "Chart of Accounts mapping" in decisions
    assert "Final go/no-go" in decisions
    assert result["historical_window"]["starts_on"] == "2021-07-07"
    assert (
        result["historical_window"]["opening_evidence_state"]
        == "control_evidence_required_by_family"
    )
    assert result["historical_window"]["decision"] == "full_available_history"
    assert (
        result["accounting_admission"]["historical_window_decision"]
        == "resolved_full_available_history"
    )
    assert result["accounting_admission"]["historical_reporting_basis"] == "cash"
    assert result["run_history"][0]["run_id"] == HCP_MASTER_ID
    assert result["run_history"][0]["replay"] == "verified"
    assert result["run_history"][0]["exceptions"] == sum(
        item["exception"] for item in result["counts"]
    )


def test_cutover_packets_preserve_known_hcp_contradictions() -> None:
    result = projection()
    packets = {item["decision_id"]: item for item in result["decision_packets"]}
    assert packets["HCP.CANCELED_BALANCE_JOBS"]["recommended_default"] == "retain_hold"
    assert "296" in packets["HCP.CANCELED_BALANCE_JOBS"]["current_evidence"]
    assert (
        packets["HCP.UNLINKED_ESTIMATES"]["recommended_default"]
        == "retain_evidence_only"
    )
    assert (
        "fabricated Job link" in packets["HCP.UNLINKED_ESTIMATES"]["current_evidence"]
    )
    assert result["go_no_go"]["state"] == "external_auth_required"
    assert not result["go_no_go"]["activation_eligible"]
    assert (
        result["freeze_authority"]["late_change_behavior"]
        == "invalidate_delta_and_return_to_reconciliation"
    )
