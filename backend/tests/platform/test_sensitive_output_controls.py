from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.security.safe_output import (
    REDACTED,
    SensitiveDataLogFilter,
    catalog_fingerprint,
    install_sensitive_data_logging_controls,
    safe_digest,
    safe_exception,
    sanitize,
    validate_no_sensitive_fields,
)

CANARIES = {
    "password": "CANARY-PASSWORD-PLAT007",
    "password_hash": "$argon2id$CANARY-HASH-PLAT007",
    "invitation_secret": "CANARY-INVITATION-PLAT007",
    "reset_token": "CANARY-RESET-PLAT007",
    "verification_token": "CANARY-VERIFY-PLAT007",
    "database_url": "postgresql://user:CANARY-DB-PASSWORD@database/acp",
    "login_email": "protected-canary@example.invalid",
    "hourly_rate": "9876.54",
    "bank_account_number": "000111222333",
    "payment_token": "CANARY-PAYMENT-TOKEN-PLAT007",
    "raw_source_payload": {"provider_note": "CANARY-SOURCE-ROW-PLAT007"},
}


def _render(value: object) -> str:
    return str(value)


def test_nested_sensitive_catalog_is_deterministic_and_preserves_safe_references() -> (
    None
):
    company_id = uuid4()
    value = {
        "company_id": company_id,
        "status": "failed",
        "nested": [CANARIES, {"count": 2}],
    }
    first = sanitize(value)
    second = sanitize(value)
    rendered = _render(first)

    assert first == second
    assert first["company_id"] == str(company_id)  # type: ignore[index]
    assert first["status"] == "failed"  # type: ignore[index]
    assert first["nested"][1]["count"] == 2  # type: ignore[index]
    assert REDACTED in rendered
    for canary in CANARIES.values():
        if isinstance(canary, str):
            assert canary not in rendered


@dataclass(frozen=True)
class PayrollResult:
    employee_id: str
    hourly_rate: Decimal
    salary: Decimal


class CredentialModel(BaseModel):
    username: str
    password: str


def test_dataclass_and_model_representations_cannot_bypass_redaction() -> None:
    result = sanitize(
        {
            "payroll_result": PayrollResult(
                employee_id="employee-safe-reference",
                hourly_rate=Decimal("91.25"),
                salary=Decimal(190000),
            ),
            "credential": CredentialModel(
                username="operator", password="MODEL-CANARY-PASSWORD"
            ),
        }
    )
    rendered = _render(result)
    assert "91.25" not in rendered
    assert "190000" not in rendered
    assert "MODEL-CANARY-PASSWORD" not in rendered


def test_logging_filter_sanitizes_structured_fields_and_exception_chains() -> None:
    logger = logging.getLogger("plat007-test")
    logger.handlers.clear()
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    installed = install_sensitive_data_logging_controls(logger)
    assert isinstance(installed, SensitiveDataLogFilter)
    assert install_sensitive_data_logging_controls(logger) is installed

    try:
        try:
            raise ValueError("CANARY-INNER-SECRET")
        except ValueError as inner:
            raise RuntimeError("CANARY-OUTER-SECRET") from inner
    except RuntimeError:
        logger.exception(
            "provider_failed %s",
            {"database_url": CANARIES["database_url"], "safe_code": "timeout"},
            extra={"payment_token": CANARIES["payment_token"]},
        )

    output = stream.getvalue()
    assert "timeout" in output
    assert REDACTED in output
    assert "CANARY" not in output


def test_logging_filter_redacts_secret_assignments_in_plain_messages() -> None:
    logger = logging.getLogger("plat007-plain-message-test")
    logger.handlers.clear()
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    install_sensitive_data_logging_controls(logger)

    logger.warning(
        "provider failed token=PLAIN-TOKEN-CANARY "
        "api_key: 'PLAIN-API-CANARY' "
        'client-secret="PLAIN-CLIENT-CANARY" status=retryable'
    )

    output = stream.getvalue()
    assert "status=retryable" in output
    assert output.count(f"{REDACTED}:secret") == 3
    assert "CANARY" not in output


def test_safe_exception_exposes_type_code_and_digest_not_messages() -> None:
    try:
        try:
            raise ValueError("CANARY-INNER")
        except ValueError as inner:
            raise RuntimeError("CANARY-OUTER") from inner
    except RuntimeError as error:
        first = safe_exception(error, code="provider_failure")
        second = safe_exception(error, code="provider_failure")

    assert first == second
    rendered = first.model_dump_json()
    assert first.exception_type == "RuntimeError"
    assert first.code == "provider_failure"
    assert "CANARY" not in rendered


def test_audit_preserves_accountability_but_rejects_sensitive_details() -> None:
    company_id = uuid4()
    entry = AuditEntry(
        action="credential.rotation.requested",
        resource_type="credential",
        actor_user_id=uuid4(),
        company_id=company_id,
        resource_id=uuid4(),
        reason_code="scheduled_rotation",
        details={"password": CANARIES["password"]},
    )
    with pytest.raises(ValueError, match="audit details"):
        AuditService._validate(entry)
    safe = AuditEntry(
        action=entry.action,
        resource_type=entry.resource_type,
        actor_user_id=entry.actor_user_id,
        company_id=company_id,
        resource_id=entry.resource_id,
        reason_code=entry.reason_code,
        details={"decision_digest": safe_digest("credential-rotation")},
    )
    AuditService._validate(safe)


@pytest.mark.parametrize(
    "payload",
    [
        {"verification_token": CANARIES["verification_token"]},
        {"raw_source_payload": CANARIES["raw_source_payload"]},
        {"employee": {"social-security-number": "999-88-7777"}},
        {"vendor": {"taxpayer_identification_number": "12-3456789"}},
    ],
)
def test_business_event_rejects_secret_and_raw_source_metadata(
    payload: dict[str, object],
) -> None:
    class Session:
        def add(self, value: object) -> None:
            raise AssertionError("secret event must fail before persistence")

    with pytest.raises(ValueError, match="Business Event payload"):
        BusinessEventService.stage(  # type: ignore[arg-type]
            Session(),
            BusinessEventCreate(
                event_type=EventType.SYSTEM_STARTED,
                entity_type="synthetic",
                company_id=uuid4(),
                payload=payload,
            ),
        )


def test_ordinary_business_event_facts_remain_available() -> None:
    class Session:
        added: list[object]

        def __init__(self) -> None:
            self.added = []

        def add(self, value: object) -> None:
            self.added.append(value)

    session = Session()
    event = BusinessEventService.stage(  # type: ignore[arg-type]
        session,
        BusinessEventCreate(
            event_type=EventType.SYSTEM_STARTED,
            entity_type="synthetic",
            company_id=uuid4(),
            payload={"status": "ready", "count": 3, "evidence_digest": "a" * 64},
        ),
    )
    assert event.payload == {
        "status": "ready",
        "count": 3,
        "evidence_digest": "a" * 64,
    }


def test_connection_strings_bearer_tokens_and_private_keys_are_sanitized() -> None:
    text = sanitize(
        "postgresql://user:db-canary@example/acp "
        "Bearer token-canary.abc "
        "-----BEGIN PRIVATE KEY-----key-canary-----END PRIVATE KEY-----"
    )
    assert isinstance(text, str)
    assert "db-canary" not in text
    assert "token-canary" not in text
    assert "key-canary" not in text
    assert text.count(REDACTED) == 3


def test_catalog_fingerprint_and_validation_are_deterministic() -> None:
    assert catalog_fingerprint() == (
        "f2244fb4204cec1c582146dcfdf63a13e07cd59ed961b2a83090ed3c7ea8ca84"
    )
    validate_no_sensitive_fields(
        {"company_id": str(uuid4()), "status": "accepted"},
        boundary="safe result",
    )


def test_unexpected_api_error_does_not_serialize_exception_or_request_secret() -> None:
    application = FastAPI(debug=False)

    @application.post("/synthetic")
    async def synthetic_failure() -> None:
        raise RuntimeError("CANARY-API-EXCEPTION")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post(
            "/synthetic", json={"password": "CANARY-REQUEST-PASSWORD"}
        )

    assert response.status_code == 500
    assert "CANARY" not in response.text
    assert response.text == "Internal Server Error"
