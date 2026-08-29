from app.qbo_source.source_authority import (
    CrossSourceDisposition,
    FactAuthority,
    SourceFact,
    reconcile_source_fact,
)


def _fact(provider: str, value: str, link: str | None = "link-1") -> SourceFact:
    return SourceFact(
        provider=provider,
        evidence_id=f"{provider}-evidence",
        fact_name="invoice_amount",
        canonical_value=value,
        authoritative_link_id=link,
    )


def test_cross_source_reconciliation_requires_authoritative_linkage() -> None:
    finding = reconcile_source_fact(
        hcp=_fact("hcp", "100.00", None), qbo=_fact("qbo", "100.00", None)
    )
    assert finding.disposition is CrossSourceDisposition.MISSING_LINKAGE
    assert finding.authority is FactAuthority.UNRESOLVED


def test_cross_source_reconciliation_corroborates_only_equal_linked_fact() -> None:
    finding = reconcile_source_fact(
        hcp=_fact("hcp", "100.00"), qbo=_fact("qbo", "100.00")
    )
    replay = reconcile_source_fact(
        hcp=_fact("hcp", "100.00"), qbo=_fact("qbo", "100.00")
    )
    assert finding.disposition is CrossSourceDisposition.CORROBORATED
    assert finding.authority is FactAuthority.CORROBORATED
    assert replay.finding_digest == finding.finding_digest


def test_cross_source_reconciliation_preserves_conflict() -> None:
    finding = reconcile_source_fact(
        hcp=_fact("hcp", "100.00"), qbo=_fact("qbo", "99.00")
    )
    assert finding.disposition is CrossSourceDisposition.CONFLICTING_AMOUNT
    assert finding.authority is FactAuthority.CONFLICTING
