import hashlib
import html
import json
from typing import Any

from app.estimates.schemas import EstimateArtifact, EstimateItem

TEMPLATE_VERSION = "estimate-html-v1"


def render_estimate_artifact(estimate: EstimateItem) -> EstimateArtifact:
    revision = estimate.current_revision
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "template_version": TEMPLATE_VERSION,
        "estimate_id": str(estimate.id),
        "estimate_number": estimate.estimate_number,
        "estimate_version": estimate.version,
        "revision_id": str(revision.id),
        "revision_number": revision.revision_number,
        "status": estimate.status,
        "customer_id": str(estimate.customer_id),
        "service_location_id": (
            str(estimate.service_location_id)
            if estimate.service_location_id is not None
            else None
        ),
        "currency": revision.currency,
        "subtotal_amount": str(revision.subtotal_amount),
        "discount_amount": str(revision.discount_amount),
        "tax_amount": str(revision.tax_amount),
        "total_amount": str(revision.total_amount),
        "expires_at": revision.expires_at.isoformat() if revision.expires_at else None,
        "lines": [
            {
                "id": str(line.id),
                "snapshot_id": str(line.snapshot_id),
                "snapshot_digest": line.snapshot_digest,
                "title": line.title,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
                "option_group_id": str(line.option_group_id)
                if line.option_group_id
                else None,
                "option_id": str(line.option_id) if line.option_id else None,
            }
            for line in revision.lines
        ],
    }
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    artifact_digest = hashlib.sha256(encoded).hexdigest()
    rows = "".join(
        f"<tr><td>{html.escape(line.title)}</td><td>{html.escape(str(line.quantity))}</td><td>{html.escape(str(line.unit_price))}</td><td>{html.escape(revision.currency)} {html.escape(str(line.line_total))}</td></tr>"
        for line in revision.lines
    )
    draft_notice = (
        '<p class="notice">DRAFT PREVIEW — not presented for Customer decision.</p>'
        if estimate.status == "draft"
        else ""
    )
    content = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(estimate.estimate_number)}</title><style>body{{font:14px system-ui;margin:3rem;color:#172033}}h1{{margin-bottom:.25rem}}table{{width:100%;border-collapse:collapse;margin:2rem 0}}th,td{{padding:.65rem;border-bottom:1px solid #ccd3dd;text-align:left}}.totals{{margin-left:auto;width:20rem}}.notice{{padding:1rem;border:2px solid #a35b00}}footer{{margin-top:3rem;font-size:.75rem;color:#526071}}</style></head><body>{draft_notice}<h1>Estimate {html.escape(estimate.estimate_number)}</h1><p>{html.escape(revision.proposal_title)} · Revision {revision.revision_number}</p><p>Customer reference: {html.escape(str(estimate.customer_id))}</p><table><thead><tr><th>Scope</th><th>Quantity</th><th>Unit price</th><th>Total</th></tr></thead><tbody>{rows}</tbody></table><dl class="totals"><dt>Subtotal</dt><dd>{revision.currency} {revision.subtotal_amount}</dd><dt>Discount</dt><dd>{revision.currency} {revision.discount_amount}</dd><dt>Tax</dt><dd>{revision.currency} {revision.tax_amount}</dd><dt><strong>Total</strong></dt><dd><strong>{revision.currency} {revision.total_amount}</strong></dd></dl>{f"<p>{html.escape(revision.customer_message)}</p>" if revision.customer_message else ""}{f"<h2>Terms</h2><p>{html.escape(revision.terms)}</p>" if revision.terms else ""}<footer>Commercial evidence {artifact_digest} · Template {TEMPLATE_VERSION}. No delivery or payment authority is implied.</footer></body></html>"""
    return EstimateArtifact(
        schema_version=1,
        template_version=TEMPLATE_VERSION,
        estimate_id=estimate.id,
        estimate_version=estimate.version,
        revision_id=revision.id,
        revision_number=revision.revision_number,
        status=estimate.status,
        artifact_digest=artifact_digest,
        filename=f"{estimate.estimate_number}-r{revision.revision_number}.html",
        media_type="text/html",
        content=content,
    )
