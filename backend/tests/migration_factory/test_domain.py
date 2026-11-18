from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.migration_factory.domain import (
    AccessMethod,
    CoverageState,
    Domain,
    MigrationFactory,
    MigrationFactoryError,
    PageCheckpoint,
    SourceDiscovery,
    SourceSystem,
    all_county_current_assessment,
    canonical_digest,
    import_report_csv,
)


def factory() -> MigrationFactory:
    return MigrationFactory(uuid4())


def test_matrix_starts_complete_and_not_discovered() -> None:
    value = factory()
    assert set(value.coverage) == set(Domain)
    assert all(
        item.state is CoverageState.NOT_DISCOVERED for item in value.coverage.values()
    )


def test_discovery_requires_digest_protected_identity() -> None:
    with pytest.raises(MigrationFactoryError):
        SourceDiscovery(
            SourceSystem.QUICKBOOKS,
            "raw-realm",
            "x" * 64,
            (),
            (),
            (),
            (),
            (),
            datetime.now(timezone.utc),
        )


def test_acquired_requires_zero_silent_drop_count_proof() -> None:
    value = factory()
    value.transition(Domain.CUSTOMERS, CoverageState.AVAILABLE_API, source_count=3)
    with pytest.raises(MigrationFactoryError, match="zero-silent-drop"):
        value.transition(Domain.CUSTOMERS, CoverageState.ACQUIRED, received_count=2)
    acquired = value.transition(
        Domain.CUSTOMERS, CoverageState.ACQUIRED, received_count=2, quarantined_count=1
    )
    assert acquired.accounted_count == 3


def test_raw_vault_is_digest_bound_and_idempotent() -> None:
    value = factory()
    kwargs = {
        "source": SourceSystem.HOUSECALL_PRO,
        "object_type": "job",
        "object_id": "j1",
        "payload": {"id": "j1"},
        "payload_reference": "vault://j1",
        "api_version": "v1",
        "authority": "source_reported",
        "batch_identity": "b1",
        "page_identity": "p1",
    }
    first = value.retain_raw(**kwargs)
    second = value.retain_raw(**kwargs)
    assert first == second
    assert first.evidence_digest == canonical_digest({"id": "j1"})


def test_page_replay_rejects_changed_content() -> None:
    value = factory()
    page = PageCheckpoint(
        SourceSystem.QUICKBOOKS, "invoice", "1", "100", 2, 0, True, "a" * 64
    )
    value.checkpoint_page(page)
    with pytest.raises(MigrationFactoryError, match="changed"):
        value.checkpoint_page(
            PageCheckpoint(
                SourceSystem.QUICKBOOKS, "invoice", "1", "100", 3, 0, True, "b" * 64
            )
        )


def test_pagination_requires_one_terminal_page_and_exact_count() -> None:
    value = factory()
    value.checkpoint_page(
        PageCheckpoint(
            SourceSystem.QUICKBOOKS, "invoice", "1", "10", 2, 0, False, "a" * 64
        )
    )
    value.checkpoint_page(
        PageCheckpoint(
            SourceSystem.QUICKBOOKS, "invoice", "2", "20", 1, 1, True, "b" * 64
        )
    )
    assert value.prove_pagination(SourceSystem.QUICKBOOKS, "invoice", 4)
    assert not value.prove_pagination(SourceSystem.QUICKBOOKS, "invoice", 5)


def test_crosswalk_conflict_preserves_both_and_surfaces_exception() -> None:
    value = factory()
    value.bind_crosswalk(SourceSystem.HOUSECALL_PRO, "employee-1", uuid4())
    value.bind_crosswalk(SourceSystem.HOUSECALL_PRO, "employee-1", uuid4())
    assert value.coverage[Domain.EMPLOYEES].state is CoverageState.CONFLICTED
    assert value.exceptions[0].classification == "IDENTITY_CONFLICT"


def test_authority_rules_are_explicit_and_versioned() -> None:
    value = factory()
    first = value.add_authority_rule(
        Domain.JOBS,
        "scheduled_at",
        (SourceSystem.HOUSECALL_PRO, SourceSystem.OWNER_FILE),
        1,
    )
    second = value.add_authority_rule(
        Domain.JOBS,
        "scheduled_at",
        (SourceSystem.HOUSECALL_PRO, SourceSystem.OWNER_FILE),
        2,
    )
    assert first.rule_digest != second.rule_digest
    with pytest.raises(MigrationFactoryError):
        value.add_authority_rule(
            Domain.JOBS, "scheduled_at", (SourceSystem.HOUSECALL_PRO,), 4
        )


def test_fallback_prefers_api_then_report_then_file() -> None:
    value = factory()
    value.transition(
        Domain.PAYROLL,
        CoverageState.AVAILABLE_REPORT,
        methods=(AccessMethod.AUTO_FILE_IMPORT, AccessMethod.AUTO_REPORT),
    )
    assert value.fallback(Domain.PAYROLL, "paycheck") is AccessMethod.AUTO_REPORT


def test_certificate_cannot_be_green_for_partial_domains() -> None:
    result = factory().certify("transform/v1")
    assert result.status == "BLOCKED"
    assert result.zero_silent_drops


def test_certificate_requires_every_domain() -> None:
    value = factory()
    for domain in Domain:
        value.transition(domain, CoverageState.AVAILABLE_API, source_count=0)
        value.transition(domain, CoverageState.CERTIFIED, received_count=0)
    assert value.certify("transform/v1").status == "CERTIFIED"


def test_dashboard_uses_owner_language() -> None:
    result = factory().dashboard()
    assert result["owner_steps"][0] == "Connect QuickBooks"
    assert "pagination" not in " ".join(result["owner_steps"]).lower()


def test_all_county_assessment_does_not_claim_payroll_from_accounting_scope() -> None:
    result = all_county_current_assessment()
    assert result["oauth_scopes"] == ("com.intuit.quickbooks.accounting",)
    assert result["accounting"] == "AVAILABLE"
    assert result["payroll_compensation"] == "ADDITIONAL SCOPE REQUIRED"
    assert result["employee_workforce"] == "PARTNER APPROVAL REQUIRED"
    assert result["sensitive_payroll"] == "ADDITIONAL AGREEMENT REQUIRED"
    assert result["answer_key_opened"] is False
    assert result["source_writes"] is False


def test_normalization_requires_raw_lineage_and_is_replay_safe() -> None:
    value = factory()
    with pytest.raises(MigrationFactoryError, match="retained raw"):
        value.normalize(uuid4(), "v1", {"name": "A"})
    raw = value.retain_raw(
        source=SourceSystem.QUICKBOOKS,
        object_type="Customer",
        object_id="1",
        payload={"Id": "1"},
        payload_reference="vault://1",
        api_version="75",
        authority="source_reported",
        batch_identity="b",
        page_identity="p",
    )
    value.normalize(raw.evidence_id, "v1", {"name": "A"})
    value.normalize(raw.evidence_id, "v1", {"name": "A"})
    with pytest.raises(MigrationFactoryError, match="changed"):
        value.normalize(raw.evidence_id, "v1", {"name": "B"})


def test_report_import_quarantines_bad_rows_and_preserves_digest() -> None:
    accepted, quarantined, digest = import_report_csv(
        b"Employee,Rate\nAlex,25\nMel,\n", ("Employee", "Rate")
    )
    assert accepted == ({"Employee": "Alex", "Rate": "25"},)
    assert quarantined[0]["line"] == 3
    assert len(digest) == 64


def test_webhook_gap_creates_backfill_exception() -> None:
    value = factory()
    value.record_delta(SourceSystem.HOUSECALL_PRO, "ignored", webhook_sequence=10)
    value.record_delta(SourceSystem.HOUSECALL_PRO, "ignored", webhook_sequence=12)
    assert value.exceptions[0].classification == "WEBHOOK_GAP"
    assert "backfill" in value.exceptions[0].actionable_message


def test_provider_calls_and_cost_are_metered() -> None:
    value = factory()
    value.record_provider_call(SourceSystem.QUICKBOOKS, 25)
    value.record_provider_call(SourceSystem.QUICKBOOKS, 25)
    assert value.provider_calls[SourceSystem.QUICKBOOKS] == 2
    assert value.provider_cost_microunits[SourceSystem.QUICKBOOKS] == 50
