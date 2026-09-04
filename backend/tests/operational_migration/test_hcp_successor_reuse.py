import pytest
from app.operational_migration.hcp_successor_reconciliation import (
    IdentityBinding,
    SealedIdentity,
)
from app.operational_migration.hcp_successor_reuse import (
    AUTHORITATIVE_CUSTOMER_CONTROL_DIGEST,
    AUTHORITATIVE_HYBRID_DIGEST,
    AdmissionDisposition,
    AdmissionGuardEvidence,
    QualifiedSuccessorManifest,
    SourceKey,
    SuccessorManifestEntry,
    build_successor_manifest,
    qualify_successor_admission,
)

EVIDENCE = "a" * 64


def entry(
    domain: str,
    source: str,
    disposition: AdmissionDisposition,
    *,
    native: str | None = None,
    parent: SourceKey | None = None,
) -> SuccessorManifestEntry:
    return SuccessorManifestEntry(
        domain, source, disposition, EVIDENCE, native_id=native, parent=parent
    )


def guards(**changes: object) -> AdmissionGuardEvidence:
    values: dict[str, object] = {
        "hybrid_digest": AUTHORITATIVE_HYBRID_DIGEST,
        "customer_control_digest": AUTHORITATIVE_CUSTOMER_CONTROL_DIGEST,
        "protected_authority": "c" * 40,
        "expected_protected_authority": "c" * 40,
        "schema_current": "head",
        "schema_head": "head",
        "backup_verified": True,
        "authorization_verified": True,
        "zero_prior_master_admissions": True,
        "zero_migration_drift": True,
        "rollback_verified": True,
        "security_baseline_verified": True,
    }
    values.update(changes)
    return AdmissionGuardEvidence(**values)  # type: ignore[arg-type]


def test_manifest_and_preflight_are_deterministic_and_identifier_free() -> None:
    entries = [
        entry("customer", "source-1", AdmissionDisposition.CREATE_NEW),
        entry(
            "invoice",
            "source-2",
            AdmissionDisposition.REUSE_EXACT_SUCCESSOR,
            native="native-secret",
        ),
    ]
    first = QualifiedSuccessorManifest.build(
        company_id="company-secret", branch_id="branch-secret", entries=entries
    )
    replay = QualifiedSuccessorManifest.build(
        company_id="company-secret", branch_id="branch-secret", entries=reversed(entries)
    )
    assert first == replay
    result = qualify_successor_admission(first, guards())
    assert result.admission_allowed is True
    assert result.financial_overlap_count == 1
    assert "native-secret" not in repr(result)
    assert "company-secret" not in repr(result)


def test_preflight_reports_domain_counts_and_allows_bounded_hold() -> None:
    manifest = QualifiedSuccessorManifest.build(
        company_id="company",
        branch_id="branch",
        entries=[
            entry("customer", "reuse", AdmissionDisposition.REUSE_EXACT_SUCCESSOR, native="n1"),
            entry("customer", "create", AdmissionDisposition.CREATE_NEW),
            entry("customer", "hold", AdmissionDisposition.HOLD_AMBIGUOUS),
        ],
    )
    result = qualify_successor_admission(manifest, guards())
    assert result.domain_counts["customer"].source_total == 3
    assert result.domain_counts["customer"].reuse_exact == 1
    assert result.domain_counts["customer"].create_new == 1
    assert result.domain_counts["customer"].hold == 1
    assert result.unresolved_owner_decision_count == 1
    assert result.admission_allowed is True


def test_conflict_fails_closed() -> None:
    manifest = QualifiedSuccessorManifest.build(
        company_id="company",
        branch_id="branch",
        entries=[entry("job", "conflict", AdmissionDisposition.CONFLICT)],
    )
    assert qualify_successor_admission(manifest, guards()).admission_allowed is False


def test_missing_or_blocked_parent_is_an_orphan_risk() -> None:
    parent = SourceKey("customer", "held")
    manifest = QualifiedSuccessorManifest.build(
        company_id="company",
        branch_id="branch",
        entries=[
            entry("customer", "held", AdmissionDisposition.HOLD_AMBIGUOUS),
            entry("job", "child", AdmissionDisposition.CREATE_NEW, parent=parent),
        ],
    )
    result = qualify_successor_admission(manifest, guards())
    assert result.orphan_risk_count == 1
    assert result.admission_allowed is False


def test_reused_native_target_collision_fails_closed() -> None:
    manifest = QualifiedSuccessorManifest.build(
        company_id="company",
        branch_id="branch",
        entries=[
            entry("customer", "one", AdmissionDisposition.REUSE_EXACT_SUCCESSOR, native="same"),
            entry("customer", "two", AdmissionDisposition.REUSE_EXACT_SUCCESSOR, native="same"),
        ],
    )
    result = qualify_successor_admission(manifest, guards())
    assert result.duplicate_risk_count == 1
    assert result.admission_allowed is False


def test_every_authority_guard_fails_closed_and_is_reported() -> None:
    manifest = QualifiedSuccessorManifest.build(
        company_id="company",
        branch_id="branch",
        entries=[entry("customer", "new", AdmissionDisposition.CREATE_NEW)],
    )
    result = qualify_successor_admission(
        manifest,
        guards(hybrid_digest="0" * 64, authorization_verified=False),
    )
    assert result.guard_failures == ("hybrid_authority", "authorization")
    assert result.admission_allowed is False


@pytest.mark.parametrize(
    "candidate",
    [
        entry("customer", "x", AdmissionDisposition.CREATE_NEW, native="forbidden"),
        entry("customer", "x", AdmissionDisposition.REUSE_EXACT_SUCCESSOR),
        SuccessorManifestEntry("customer", "x", AdmissionDisposition.CREATE_NEW, "bad"),
    ],
)
def test_manifest_rejects_invalid_identity_or_evidence_shape(
    candidate: SuccessorManifestEntry,
) -> None:
    with pytest.raises(ValueError):
        QualifiedSuccessorManifest.build(
            company_id="company", branch_id="branch", entries=[candidate]
        )


def test_manifest_rejects_duplicate_source_identity() -> None:
    duplicate = entry("customer", "same", AdmissionDisposition.CREATE_NEW)
    with pytest.raises(ValueError, match="duplicate"):
        QualifiedSuccessorManifest.build(
            company_id="company", branch_id="branch", entries=[duplicate, duplicate]
        )


def test_manifest_builder_reuses_only_unique_sealed_legacy_identity(tmp_path) -> None:
    manifest = build_successor_manifest(
        company_id="company",
        branch_id="branch",
        current_bindings=[
            IdentityBinding("customer", "housecall_pro", "sealed", "native"),
            IdentityBinding("customer", "housecall_pro", "unrelated", "other"),
        ],
        sealed_source4=[
            SealedIdentity("customer", "sealed"),
            SealedIdentity("customer", "new"),
        ],
    )
    assert [item.disposition for item in manifest.entries] == [
        AdmissionDisposition.CREATE_NEW,
        AdmissionDisposition.REUSE_EXACT_SUCCESSOR,
    ]
    path = tmp_path / "manifest.json"
    path.write_text(__import__("json").dumps(manifest.private_payload()))
    assert QualifiedSuccessorManifest.load(path) == manifest


def test_reused_child_cannot_depend_on_new_parent() -> None:
    parent = SourceKey("customer", "new")
    manifest = QualifiedSuccessorManifest.build(
        company_id="company",
        branch_id="branch",
        entries=[
            entry("customer", "new", AdmissionDisposition.CREATE_NEW),
            entry(
                "job",
                "old-job",
                AdmissionDisposition.REUSE_EXACT_SUCCESSOR,
                native="job-id",
                parent=parent,
            ),
        ],
    )
    result = qualify_successor_admission(manifest, guards())
    assert result.orphan_risk_count == 1
    assert result.admission_allowed is False


def test_canonical_reconciliation_rejection_is_preserved() -> None:
    manifest = QualifiedSuccessorManifest.build(
        company_id="company",
        branch_id="branch",
        entries=[entry("customer", "new", AdmissionDisposition.CREATE_NEW)],
        canonical_reconciliation_digest="b" * 64,
        canonical_reconciliation_admission_allowed=False,
    )
    result = qualify_successor_admission(manifest, guards())
    assert "canonical_successor_reconciliation" in result.guard_failures
    assert result.admission_allowed is False
