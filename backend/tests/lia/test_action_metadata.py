from uuid import uuid4

from app.lia.contracts import NavigationSuggestion


def test_navigation_suggestion_carries_server_owned_action_metadata() -> None:
    entity_id = uuid4()
    action = NavigationSuggestion(
        label="Open assigned Job",
        internal_path=f"/jobs/{entity_id}",
        required_permission="COMPANY_JOB_READ",
        available=True,
        entity_type="job",
        entity_id=entity_id,
        action_category="EMPLOYEE_WORKFLOW",
        source_identity="FIELD.ASSIGNED_JOB.v1",
    )

    assert action.internal_path == f"/jobs/{entity_id}"
    assert action.available is True
    assert action.required_permission == "COMPANY_JOB_READ"
    assert action.entity_id == entity_id


def test_navigation_suggestion_can_explain_unavailable_action_without_destination_use() -> (
    None
):
    action = NavigationSuggestion(
        label="Open Payroll readiness",
        internal_path="/payroll",
        required_permission="COMPANY_PAYROLL_READ",
        available=False,
        unavailable_reason="Payroll readiness is not available to this employee.",
        action_category="EVIDENCE_COMPLETION",
    )

    assert action.available is False
    assert action.unavailable_reason
