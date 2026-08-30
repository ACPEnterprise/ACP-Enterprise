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


def test_owner_decisions_history_and_opening_gate_remain_visible() -> None:
    result = projection()
    decisions = {item["decision"] for item in result["owner_decisions"]}
    assert "Chart of Accounts mapping" in decisions
    assert "Final go/no-go" in decisions
    assert result["historical_window"]["starts_on"] is None
    assert (
        result["historical_window"]["opening_evidence_state"]
        == "owner_decision_required"
    )
    assert result["run_history"][0]["run_id"] == HCP_MASTER_ID
    assert result["run_history"][0]["replay"] == "verified"
