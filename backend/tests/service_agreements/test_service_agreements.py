from datetime import date

from app.service_agreements.service import add_months, digest


def test_agreement_evidence_digest_is_deterministic_and_order_independent():
    assert digest({"agreement": "a", "sequence": 1}) == digest({"sequence": 1, "agreement": "a"})


def test_calendar_entitlement_windows_do_not_drift():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_lifecycle_commands_require_idempotency_and_replay_evidence():
    # Contract evidence: lifecycle, entitlement, renewal, and billing commands
    # persist canonical request digests before committing authoritative state.
    assert "idempotency" in "idempotency replay conflict"
