from app.payroll.qbo_employee_input_migration import (
    NEVER_INFER_FIELDS,
    EmployeeCrosswalk,
    ExistingAuthorityState,
    ExistingPayrollAuthority,
    ReconciliationDisposition,
    SourceClassification,
    SourceEvidence,
    classify_accounting_catalog,
    reconcile_employee,
)


def crosswalk(target: str = "employee-1") -> EmployeeCrosswalk:
    return EmployeeCrosswalk(
        "company-1", "realm-digest-1", "qbo-employee-1", target, "a" * 64, True
    )


def source(
    field: str,
    *,
    classification: SourceClassification = SourceClassification.AUTHORITATIVE_SOURCE_AVAILABLE,
    authoritative: bool = True,
    value_digest: str = "b" * 64,
    explicit_zero: bool = False,
) -> SourceEvidence:
    return SourceEvidence(
        field,
        classification,
        ("qbo-record-1",),
        "c" * 64,
        "2026",
        value_digest,
        explicit_zero,
        authoritative,
    )


def packet(
    *,
    crosswalks: tuple[EmployeeCrosswalk, ...] = (crosswalk(),),
    sources: tuple[SourceEvidence, ...] = (),
    existing: tuple[ExistingPayrollAuthority, ...] = (),
):
    return reconcile_employee(
        company_id="company-1",
        realm_company_identity="realm-digest-1",
        qbo_employee_id="qbo-employee-1",
        crosswalks=crosswalks,
        source=sources,
        existing=existing,
    )


def field(result, name: str):
    return next(item for item in result.fields if item.field == name)


def test_accounting_catalog_is_partial_or_absent_never_authoritative() -> None:
    result = classify_accounting_catalog(
        entity_counts={"employee": 2, "time_activity": 10, "journal_entry": 3}
    )
    assert all(
        item.classification
        in {SourceClassification.PARTIAL_SOURCE_EVIDENCE, SourceClassification.ABSENT}
        for item in result
    )
    assert next(item for item in result if item.field == "w4_step_2").classification is SourceClassification.ABSENT


def test_exact_approved_crosswalk_is_required() -> None:
    missing = packet(crosswalks=())
    assert missing.crosswalk_disposition is ReconciliationDisposition.SOURCE_MISSING
    ambiguous = packet(crosswalks=(crosswalk(), crosswalk("employee-2")))
    assert ambiguous.crosswalk_disposition is ReconciliationDisposition.HOLD_FOR_OWNER_REVIEW


def test_authoritative_provider_value_can_only_become_draft_instruction() -> None:
    result = packet(sources=(source("social_security_wages_ytd"),))
    value = field(result, "social_security_wages_ytd")
    assert value.disposition is ReconciliationDisposition.RESOLVED_FROM_QBO
    assert value.importable_as_draft is True


def test_partial_history_is_review_only_and_missing_is_not_zero() -> None:
    result = packet(
        sources=(
            source(
                "deduction_history",
                classification=SourceClassification.PARTIAL_SOURCE_EVIDENCE,
                authoritative=False,
                value_digest="",
            ),
        )
    )
    assert field(result, "deduction_history").disposition is ReconciliationDisposition.REVIEW_REQUIRED
    missing = field(result, "medicare_wages_ytd")
    assert missing.source_classification is SourceClassification.ABSENT
    assert missing.disposition is ReconciliationDisposition.SOURCE_MISSING
    assert missing.importable_as_draft is False


def test_w4_is_never_inferred_even_when_source_claims_authority() -> None:
    result = packet(sources=tuple(source(name) for name in NEVER_INFER_FIELDS))
    for name in NEVER_INFER_FIELDS:
        value = field(result, name)
        assert value.disposition is ReconciliationDisposition.OWNER_INPUT_REQUIRED
        assert value.importable_as_draft is False


def test_provider_cannot_overwrite_stronger_approved_authority() -> None:
    existing = ExistingPayrollAuthority(
        "social_security_wages_ytd",
        ExistingAuthorityState.APPROVED,
        "d" * 64,
        "e" * 64,
    )
    result = packet(
        sources=(source("social_security_wages_ytd"),), existing=(existing,)
    )
    value = field(result, "social_security_wages_ytd")
    assert value.disposition is ReconciliationDisposition.CONFLICTING
    assert value.preserve_existing is True
    assert value.importable_as_draft is False


def test_exact_replay_is_deterministic_and_realm_isolation_blocks_import() -> None:
    evidence = (source("federal_withholding_ytd"),)
    first = packet(sources=evidence)
    second = packet(sources=evidence)
    assert first.packet_digest == second.packet_digest
    foreign = reconcile_employee(
        company_id="company-1",
        realm_company_identity="foreign-realm",
        qbo_employee_id="qbo-employee-1",
        crosswalks=(crosswalk(),),
        source=evidence,
        existing=(),
    )
    assert foreign.crosswalk_disposition is ReconciliationDisposition.SOURCE_MISSING
    assert field(foreign, "federal_withholding_ytd").importable_as_draft is False


def test_explicit_zero_still_requires_provider_authority() -> None:
    partial_zero = source(
        "medicare_tax_ytd",
        classification=SourceClassification.PARTIAL_SOURCE_EVIDENCE,
        authoritative=False,
        value_digest="0" * 64,
        explicit_zero=True,
    )
    assert field(packet(sources=(partial_zero,)), "medicare_tax_ytd").importable_as_draft is False
