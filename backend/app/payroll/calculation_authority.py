"""Payroll-owned adapters for assembling protected calculation authorities.

The HTTP layer must not know how protected tax input keys are configured or how
provider-specific tax instructions are built.  This module keeps that boundary
server-side and deliberately fails closed when an authority is incomplete.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

from app.core.config import settings

from .calculation_adapter import deduction_instruction_from_authority
from .contracts import PayrollConflictError
from .federal_tax_rules_2026 import (
    Federal2026TaxRuleProvider,
    FederalComponent,
    FederalTaxContext,
    FilingStatus,
    PayFrequency,
    W4Election,
)
from .models import PayrollInputAuthorityVersion, PayrollProtectedInputEnvelope
from .tax_authority import ProtectedPayrollInputCipher
from .tax_calculation import (
    DeductionInstruction,
    ProviderEnvironment,
    TaxComponentInstruction,
    TaxResponsibility,
    TaxRuleProvider,
)


def protected_payload(
    *, company_id: UUID, authority: PayrollInputAuthorityVersion,
    envelope: PayrollProtectedInputEnvelope | None,
    cipher: ProtectedPayrollInputCipher,
) -> dict[str, object]:
    """Decrypt one authority envelope at the service boundary."""
    if authority.company_id != company_id:
        raise PayrollConflictError("Payroll input authority Company scope mismatch")
    if authority.protected_envelope_id is None:
        return {}
    if envelope is None:
        raise PayrollConflictError("protected Payroll input envelope is missing")
    return cipher.decrypt(
        company_id=company_id,
        key_id=envelope.key_id,
        nonce=envelope.nonce,
        ciphertext=envelope.ciphertext,
        expected_digest=envelope.content_digest,
    )


def configured_input_cipher() -> ProtectedPayrollInputCipher:
    """Return the configured server-side keyring, never exposing plaintext."""
    if not settings.payroll_input_active_kid:
        raise PayrollConflictError("protected Payroll input configuration is unavailable")
    configured = settings.payroll_input_encryption_keys
    if settings.payroll_input_encryption_key_file:
        configured = json.loads(Path(settings.payroll_input_encryption_key_file).read_text(encoding="utf-8"))
    if not isinstance(configured, dict):
        raise PayrollConflictError("protected Payroll input keyring is invalid")
    try:
        keys = {str(key): base64.urlsafe_b64decode(str(value)) for key, value in configured.items()}
        return ProtectedPayrollInputCipher(active_key_id=settings.payroll_input_active_kid, keys=keys)
    except Exception as error:  # pragma: no cover - defensive configuration boundary
        raise PayrollConflictError("protected Payroll input keyring is unavailable") from error


@dataclass(frozen=True)
class FederalAuthorityInputs:
    context: FederalTaxContext
    tax_instructions: tuple[TaxComponentInstruction, ...]
    deduction_instructions: tuple[DeductionInstruction, ...]
    authority_ids: tuple[UUID, ...]


def _decimal(payload: Mapping[str, object], key: str) -> Decimal:
    value = payload.get(key)
    if value is None:
        raise PayrollConflictError(f"protected Payroll input is missing {key}")
    try:
        return Decimal(str(value))
    except Exception as error:
        raise PayrollConflictError(f"protected Payroll input {key} is invalid") from error


def _bool(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise PayrollConflictError(f"protected Payroll input is missing {key}")
    return value


def _filing_status(value: object) -> FilingStatus:
    try:
        return FilingStatus(str(value))
    except ValueError as error:
        raise PayrollConflictError("protected Payroll filing status is invalid") from error


def build_federal_authority_inputs(
    *,
    company_id: UUID,
    employee_id: UUID,
    effective_on: date,
    pay_frequency: str,
    authorities: tuple[PayrollInputAuthorityVersion, ...],
    envelopes: Mapping[UUID, PayrollProtectedInputEnvelope],
    cipher: ProtectedPayrollInputCipher,
) -> FederalAuthorityInputs:
    """Build provider contracts exclusively from approved explicit authority."""
    if not authorities:
        raise PayrollConflictError("approved tax/deduction authority is missing")
    payload: dict[str, object] = {}
    ids: list[UUID] = []
    tax_instructions: list[TaxComponentInstruction] = []
    deductions: list[DeductionInstruction] = []
    for authority in authorities:
        if authority.company_id != company_id or authority.employee_id != employee_id:
            raise PayrollConflictError("Payroll input authority scope mismatch")
        if authority.lifecycle not in {"approved", "superseded"}:
            raise PayrollConflictError("Payroll input authority is not approved")
        ids.append(authority.id)
        public = authority.public_parameters or {}
        envelope_id = authority.protected_envelope_id
        if envelope_id is not None:
            envelope = envelopes.get(envelope_id)
            if envelope is None:
                raise PayrollConflictError("protected Payroll input envelope is missing")
            payload.update(cipher.decrypt(company_id=company_id, key_id=envelope.key_id, nonce=envelope.nonce, ciphertext=envelope.ciphertext, expected_digest=envelope.content_digest))
        if authority.authority_domain == "deduction":
            deductions.append(deduction_instruction_from_authority(authority_id=authority.id, authority_digest=authority.authority_digest, authority_key=authority.authority_key, currency="USD", public_parameters=public, priority=authority.priority or 0))
            continue
        key = authority.authority_key
        component = {
            "federal_income_tax": FederalComponent.FEDERAL_INCOME_TAX,
            "social_security_employee": FederalComponent.SOCIAL_SECURITY_EMPLOYEE,
            "medicare_employee": FederalComponent.MEDICARE_EMPLOYEE,
        }.get(key)
        if component is None:
            continue
        jurisdiction = authority.jurisdiction_reference
        if not jurisdiction:
            raise PayrollConflictError(f"Payroll tax jurisdiction is missing for {key}")
        federal_provider = Federal2026TaxRuleProvider(
            context=FederalTaxContext(
                effective_on=effective_on,
                pay_frequency=PayFrequency(str(pay_frequency)),
                w4=W4Election(
                    filing_status=_filing_status(payload.get("filing_status")),
                    step_2_checked=_bool(payload, "step_2_checked"),
                    step_3_credits=_decimal(payload, "step_3_credits"),
                    step_4a_other_income=_decimal(payload, "step_4a_other_income"),
                    step_4b_deductions=_decimal(payload, "step_4b_deductions"),
                    step_4c_extra_withholding=_decimal(payload, "step_4c_extra_withholding"),
                ),
                social_security_wages_ytd=_decimal(payload, "social_security_wages_ytd"),
                medicare_wages_ytd=_decimal(payload, "medicare_wages_ytd"),
            ),
            component=component,
            environment=ProviderEnvironment.PRODUCTION,
        )
        tax_instructions.append(TaxComponentInstruction(component_key=component.value, responsibility=TaxResponsibility.EMPLOYEE_WITHHOLDING if component is FederalComponent.FEDERAL_INCOME_TAX else TaxResponsibility.EMPLOYEE_PAYROLL_TAX, authority_id=authority.id, authority_digest=authority.authority_digest, jurisdiction_reference=jurisdiction, requires_protected_input=envelope_id is not None, provider=cast(TaxRuleProvider, federal_provider)))
    provider = tax_instructions[0].provider if tax_instructions else None
    if provider is None:
        raise PayrollConflictError("federal tax authority is missing")
    concrete = cast(Federal2026TaxRuleProvider, provider)
    return FederalAuthorityInputs(context=concrete.context, tax_instructions=tuple(tax_instructions), deduction_instructions=tuple(deductions), authority_ids=tuple(ids))
