from app.qbo_source.om2b_evidence import (
    QboEvidenceCompleteness,
    QboEvidenceMode,
    QboReportControl,
    build_om2b_evidence_packet,
)


def test_live_packet_preserves_identity_pagination_cutoff_and_basis() -> None:
    packet = build_om2b_evidence_packet(
        mode=QboEvidenceMode.LIVE,
        provider_environment="production",
        connection_marker={
            "environment": "production",
            "realm_id": "123456",
            "company_info_id": "company-1",
            "company_name": "Exact Company",
            "company_info_verified_at": "2026-09-10T22:00:00+00:00",
        },
        source_manifest={
            "state": "complete",
            "started_at": "2026-09-10T22:01:00+00:00",
            "ended_at": "2026-09-10T22:02:00+00:00",
            "snapshot": {
                "accounting_date_cutoff": "2026-09-10",
                "cutoff_timezone": "America/New_York",
                "api_minor_version": 75,
            },
            "entity_counts": {"invoice": 2},
            "pages": [
                {"entity_kind": "invoice", "page": 1},
                {"entity_kind": "invoice", "page": 2},
            ],
            "catalog_dispositions": [],
        },
        source_manifest_sha256="a" * 64,
        report_controls=(
            QboReportControl(
                report_kind="profit_and_loss",
                accounting_basis="cash",
                report_end_date="2026-09-10",
                generated_at="2026-09-10T22:03:00+00:00",
                registration_sha256="b" * 64,
            ),
        ),
    )
    assert packet.completeness is QboEvidenceCompleteness.COMPLETE
    assert packet.page_counts == {"invoice": 2}
    assert packet.company_identity_sha256 is not None
    assert packet.report_controls[0].accounting_basis == "cash"
    assert "not_live_provider_evidence" not in packet.limitations


def test_blocked_packet_never_promotes_historical_controls_to_live() -> None:
    packet = build_om2b_evidence_packet(
        mode=QboEvidenceMode.BLOCKED,
        provider_environment="historical_control",
        connection_marker=None,
        source_manifest=None,
        source_manifest_sha256=None,
        limitations=("production_oauth_authority_unavailable",),
    )
    assert packet.completeness is QboEvidenceCompleteness.UNAVAILABLE
    assert packet.company_identity_sha256 is None
    assert "not_live_provider_evidence" in packet.limitations
    assert "production_oauth_authority_unavailable" in packet.limitations
    assert "no_ledger_posting_authority" in packet.limitations


def test_packet_digest_is_deterministic_and_order_independent() -> None:
    values = {
        "mode": QboEvidenceMode.HISTORICAL,
        "provider_environment": "historical_control",
        "connection_marker": None,
        "source_manifest": {
            "state": "partial",
            "entity_counts": {"payment": 1, "invoice": 2},
            "pages": [{"entity_kind": "invoice"}, {"entity_kind": "payment"}],
            "catalog_dispositions": [],
        },
        "source_manifest_sha256": "c" * 64,
    }
    first = build_om2b_evidence_packet(**values)
    values["source_manifest"] = {
        **values["source_manifest"],
        "entity_counts": {"invoice": 2, "payment": 1},
    }
    second = build_om2b_evidence_packet(**values)
    assert first.packet_sha256 == second.packet_sha256
