"""Fail-closed adapter from sealed QBO custody to opening-control facts.

The browser supplies only a package identity.  This adapter reads a server-owned,
digest-bound authority document produced by the QBO custody workflow.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.accounting.errors import AccountingNotFound, AccountingValidation
from app.accounting.opening_controls import OpeningControlPreviewRequest
from app.qbo_source.bounded_evidence import latest_bounded_evidence


class SealedOpeningPackageAdapter:
    def __init__(self, evidence_root: Path) -> None:
        self.root = evidence_root.expanduser().resolve()

    def resolve(self, package_identity: str) -> OpeningControlPreviewRequest:
        packet = latest_bounded_evidence(self.root)
        if packet is None:
            raise AccountingNotFound("A sealed QBO source package was not found")
        if packet.manifest.get("run_id") != package_identity:
            raise AccountingNotFound("The selected sealed QBO package was not found")
        authority_path = self.root / "controls" / f"opening-{package_identity}.json"
        if not authority_path.is_file():
            raise AccountingNotFound(
                "The selected QBO package has no sealed opening-control authority"
            )
        try:
            document = json.loads(authority_path.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            raise AccountingValidation(
                "Sealed opening authority is unreadable"
            ) from error
        if not isinstance(document, dict):
            raise AccountingValidation("Sealed opening authority is malformed")
        payload = document.get("opening_control_request")
        declared_digest = document.get("opening_control_request_digest")
        if not isinstance(payload, dict) or not isinstance(declared_digest, str):
            raise AccountingValidation("Sealed opening authority is incomplete")
        actual_digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if actual_digest != declared_digest:
            raise AccountingValidation("Sealed opening authority digest conflicts")
        if (
            payload.get("package_identity") != package_identity
            or payload.get("realm_id") != packet.bounded_manifest.get("realm_id")
            or payload.get("source_manifest_digest") != packet.manifest_sha256
        ):
            raise AccountingValidation("Sealed opening authority lineage conflicts")
        try:
            return OpeningControlPreviewRequest.model_validate(payload)
        except ValueError as error:
            raise AccountingValidation("Sealed opening authority is invalid") from error
