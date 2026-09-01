"""Deterministic, provider-neutral transactional message rendering."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from urllib.parse import urlparse


class TemplateSecurityError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedTransactionalMessage:
    template_identifier: str
    template_version: str
    subject: str
    plain_text: str
    html: str
    content_digest: str


def _safe_header(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise TemplateSecurityError("Message header contains invalid characters.")
    return value.strip()


def _https_url(value: str, *, expected_origin: str) -> str:
    parsed = urlparse(value)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or origin != expected_origin.rstrip("/")
    ):
        raise TemplateSecurityError("Protected action URL is not authorized.")
    if parsed.username or parsed.password or parsed.fragment:
        raise TemplateSecurityError("Protected action URL is not authorized.")
    return value


def _digest(payload: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def render_employee_invitation(
    *,
    recipient_display_name: str,
    company_display_name: str,
    activation_url: str,
    expected_origin: str,
    expiration_copy: str,
) -> RenderedTransactionalMessage:
    """Render a fixed v1 invitation without logging or persisting its token."""
    person = _safe_header(recipient_display_name) or "there"
    company = _safe_header(company_display_name) or "your company"
    action = _https_url(activation_url, expected_origin=expected_origin)
    expiration = _safe_header(expiration_copy)
    subject = _safe_header(f"Activate your ACP account for {company}")
    plain = (
        f"Hello {person},\n\n{company} invited you to ACP Enterprise. "
        f"Activate your account: {action}\n\n{expiration}\n\n"
        "If you were not expecting this invitation, contact your company administrator."
    )
    markup = (
        f"<p>Hello {html.escape(person)},</p>"
        f"<p>{html.escape(company)} invited you to ACP Enterprise.</p>"
        f'<p><a href="{html.escape(action, quote=True)}">Activate Account</a></p>'
        f"<p>{html.escape(expiration)}</p>"
        "<p>If you were not expecting this invitation, contact your company administrator.</p>"
    )
    facts = {
        "template_identifier": "identity-onboarding-invitation",
        "template_version": "identity-onboarding-invitation-v1",
        "subject": subject,
        "plain_text": plain,
        "html": markup,
    }
    return RenderedTransactionalMessage(**facts, content_digest=_digest(facts))


def render_protected_document_notice(
    *,
    template_identifier: str,
    title: str,
    protected_url: str,
    expected_origin: str,
    artifact_digest: str,
) -> RenderedTransactionalMessage:
    if len(artifact_digest) != 64:
        raise TemplateSecurityError("Artifact evidence digest is invalid.")
    safe_title = _safe_header(title)
    action = _https_url(protected_url, expected_origin=expected_origin)
    subject = _safe_header(f"{safe_title} is ready in ACP")
    plain = f"Your {safe_title} is ready. View the protected document: {action}"
    markup = (
        f"<p>Your {html.escape(safe_title)} is ready.</p>"
        f'<p><a href="{html.escape(action, quote=True)}">View protected document</a></p>'
    )
    facts = {
        "template_identifier": template_identifier,
        "template_version": f"{template_identifier}-v1",
        "subject": subject,
        "plain_text": plain,
        "html": markup,
    }
    return RenderedTransactionalMessage(**facts, content_digest=_digest(facts))
