from app.operational_migration.module_readiness import (
    CutoverAuthority,
    CutoverPhase,
    EntityAccounting,
    GoNoGoState,
    HistoricalWindow,
    SourceAuthority,
    qualify_cutover,
)

DIGEST = "a" * 64
SHA = "b" * 40


def authority(**changes: object) -> CutoverAuthority:
    values: dict[str, object] = {
        "company_id": "company",
        "branch_id": "branch",
        "target_environment": "migration_rehearsal",
        "repository_sha": SHA,
        "actor_id": "migration-actor",
        "source_authorities": (
            SourceAuthority("hcp", "sealed", DIGEST, "hcp/v1", True, True),
            SourceAuthority("qbo", "sandbox", DIGEST, "qbo/v1", True, True),
        ),
        "entity_accounting": (
            EntityAccounting("jobs", 10, migrated=7, held=1, exception=2),
            EntityAccounting("invoices", 5, migrated=2, deferred_with_authority=3),
        ),
        "historical_window": HistoricalWindow(None, "2026-08-30", DIGEST, None),
        "required_owner_decisions": ("invoice_overlap",),
        "resolved_owner_decisions": (),
        "phase": CutoverPhase.RECONCILED,
    }
    values.update(changes)
    return CutoverAuthority(**values)  # type: ignore[arg-type]


def test_module_is_non_production_ready_with_external_owner_gate() -> None:
    result = qualify_cutover(authority())
    assert result.ready_for_non_production_rehearsal
    assert not result.ready_for_production_cutover
    assert result.blocker_codes == ("owner_policy_decisions_required",)
    assert result.go_no_go_state is GoNoGoState.OWNER_DECISION_REQUIRED


def test_unexplained_delta_blocks_rehearsal() -> None:
    result = qualify_cutover(
        authority(entity_accounting=(EntityAccounting("jobs", 10, migrated=9),))
    )
    assert not result.ready_for_non_production_rehearsal
    assert "jobs_unexplained_delta" in result.blocker_codes
    assert result.go_no_go_state is GoNoGoState.RECONCILIATION_REQUIRED


def test_historical_truncation_requires_opening_evidence() -> None:
    result = qualify_cutover(
        authority(
            historical_window=HistoricalWindow(
                "2024-01-01", "2026-08-30", DIGEST, None
            )
        )
    )
    assert "historical_opening_evidence_required" in result.blocker_codes
    assert result.go_no_go_state is GoNoGoState.OPENING_EVIDENCE_REQUIRED


def test_final_delta_and_freeze_are_required_after_phase_transition() -> None:
    result = qualify_cutover(authority(phase=CutoverPhase.FINAL_DELTAS_ACQUIRED))
    assert "source_freeze_evidence_required" in result.blocker_codes
    assert "final_delta_evidence_required" in result.blocker_codes
    assert result.go_no_go_state is GoNoGoState.EXTERNAL_AUTH_REQUIRED


def test_identical_authority_is_deterministic() -> None:
    assert qualify_cutover(authority()).authority_digest == qualify_cutover(
        authority()
    ).authority_digest
