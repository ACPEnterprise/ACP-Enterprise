"""Deterministic, provider-neutral protection for ordinary operational output."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class SensitiveClassification(StrEnum):
    SECRET = "secret"
    SENSITIVE_VALUE = "sensitive_value"
    PROTECTED_SOURCE_PAYLOAD = "protected_source_payload"


REDACTED = "[REDACTED]"

SECRET_FIELDS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "bank_account_number",
        "bearer_token",
        "client_secret",
        "connection_string",
        "cookie",
        "credential",
        "database_url",
        "invitation_secret",
        "nested_token_hash",
        "password",
        "password_hash",
        "payment_token",
        "private_key",
        "private_key_pem",
        "refresh_token",
        "reset_token",
        "routing_number",
        "secret",
        "session_cookie",
        "session_token",
        "ssh_private_key",
        "token",
        "token_hash",
        "verification_token",
        "worker_credential_id",
    }
)

SENSITIVE_FIELDS = frozenset(
    {
        "address",
        "annual_salary",
        "attachment_content",
        "compensation",
        "compensation_amount",
        "email",
        "hourly_rate",
        "login_email",
        "notes",
        "payroll_result",
        "phone",
        "phone_number",
        "salary",
        "tax_deduction",
    }
)

PROTECTED_PAYLOAD_FIELDS = frozenset(
    {
        "financial_source_payload",
        "migration_source_payload",
        "protected_source_payload",
        "provider_payload",
        "raw_acquisition_artifact",
        "raw_provider_row",
        "raw_source_payload",
        "source_financial_payload",
    }
)

SAFE_REFERENCE_FIELDS = frozenset(
    {
        "actor_user_id",
        "branch_id",
        "company_id",
        "correlation_id",
        "entity_id",
        "event_id",
        "idempotency_key",
        "resource_id",
        "subject_id",
    }
)

_CREDENTIAL_URL = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@", re.IGNORECASE
)
_BEARER = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
    r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    re.DOTALL,
)
_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


def normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def classify_field(name: str) -> SensitiveClassification | None:
    normalized = normalize_field_name(name)
    if normalized in SECRET_FIELDS:
        return SensitiveClassification.SECRET
    if normalized in PROTECTED_PAYLOAD_FIELDS:
        return SensitiveClassification.PROTECTED_SOURCE_PAYLOAD
    if normalized in SENSITIVE_FIELDS:
        return SensitiveClassification.SENSITIVE_VALUE
    return None


def safe_digest(value: object) -> str:
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _redaction(classification: SensitiveClassification) -> str:
    return f"{REDACTED}:{classification.value}"


def sanitize_text(value: str) -> str:
    sanitized = _PRIVATE_KEY.sub(f"{REDACTED}:secret", value)
    sanitized = _BEARER.sub(f"Bearer {REDACTED}:secret", sanitized)
    return _CREDENTIAL_URL.sub(rf"\g<scheme>{REDACTED}:secret@", sanitized)


def sanitize(value: object, *, field_name: str | None = None) -> object:
    classification = classify_field(field_name) if field_name else None
    if classification is not None:
        return _redaction(classification)
    if isinstance(value, BaseModel):
        return sanitize(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return sanitize(
            {item.name: getattr(value, item.name) for item in fields(value)}
        )
    if isinstance(value, Mapping):
        return {
            str(key): sanitize(child, field_name=str(key))
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize(child, field_name=field_name) for child in value]
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, UUID):
        return str(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return {"type": type(value).__name__, "digest": safe_digest(type(value).__name__)}


def validate_no_sensitive_fields(
    value: object, *, boundary: str, include_personal: bool = True
) -> None:
    def visit(item: object, path: str = "") -> None:
        if isinstance(item, BaseModel):
            visit(item.model_dump(mode="python"), path)
            return
        if is_dataclass(item) and not isinstance(item, type):
            visit(
                {field.name: getattr(item, field.name) for field in fields(item)}, path
            )
            return
        if isinstance(item, Mapping):
            for key, child in item.items():
                key_name = str(key)
                classification = classify_field(key_name)
                if classification is not None and (
                    include_personal
                    or classification
                    in {
                        SensitiveClassification.SECRET,
                        SensitiveClassification.PROTECTED_SOURCE_PAYLOAD,
                    }
                ):
                    raise ValueError(f"Sensitive values are prohibited in {boundary}.")
                visit(child, f"{path}.{key_name}" if path else key_name)
        elif isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            for child in item:
                visit(child, path)

    visit(value)


class SafeExceptionView(BaseModel):
    code: str
    classification: str
    correlation_id: UUID | None = None
    exception_type: str
    chain_digest: str


def safe_exception(
    error: BaseException,
    *,
    code: str,
    classification: str = "internal_error",
    correlation_id: UUID | None = None,
) -> SafeExceptionView:
    types: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        types.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return SafeExceptionView(
        code=code,
        classification=classification,
        correlation_id=correlation_id,
        exception_type=types[0],
        chain_digest=safe_digest(types),
    )


class SensitiveDataLogFilter(logging.Filter):
    """Last-line protection for standard-library logging handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize(record.msg)
        if isinstance(record.args, Mapping):
            record.args = sanitize(record.args)  # type: ignore[assignment]
        elif isinstance(record.args, tuple):
            record.args = tuple(sanitize(item) for item in record.args)
        if record.exc_info is not None:
            error = record.exc_info[1]
            if error is not None:
                record.safe_exception = safe_exception(
                    error, code="logged_exception"
                ).model_dump(mode="json")
            record.exc_info = None
            record.exc_text = None
        for key, child in tuple(record.__dict__.items()):
            if key not in _LOG_RECORD_FIELDS:
                setattr(record, key, sanitize(child, field_name=key))
        return True


def install_sensitive_data_logging_controls(
    root: logging.Logger | None = None,
) -> SensitiveDataLogFilter:
    logger = root or logging.getLogger()
    existing = next(
        (
            item
            for handler in logger.handlers
            for item in handler.filters
            if isinstance(item, SensitiveDataLogFilter)
        ),
        None,
    )
    if existing is not None:
        return existing
    filter_instance = SensitiveDataLogFilter()
    for handler in logger.handlers:
        handler.addFilter(filter_instance)
    return filter_instance


def catalog_fingerprint() -> str:
    return safe_digest(
        {
            "secret": sorted(SECRET_FIELDS),
            "sensitive": sorted(SENSITIVE_FIELDS),
            "protected_payload": sorted(PROTECTED_PAYLOAD_FIELDS),
            "safe_reference": sorted(SAFE_REFERENCE_FIELDS),
        }
    )
