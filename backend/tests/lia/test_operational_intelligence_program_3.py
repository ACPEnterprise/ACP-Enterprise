from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.lia.contracts import LiaRequest
from app.lia.retrieval import GovernedRetrievalService, permitted_domain_names
from app.lia.service import LiaService
from app.operational_assets.lia_context import (
    CONTRACT_VERSION as ASSET_CONTRACT,
)
from app.operational_assets.lia_context import (
    PROTECTED_IDENTIFIERS,
)
from app.platform.permissions.codes import (
    AssetPermission,
    CommunicationsPermission,
    WorkforcePermission,
)
from app.workforce.lia_context import CONTRACT_VERSION as WORKFORCE_CONTRACT


def _context(*permissions: str) -> SimpleNamespace:
    company_id, branch_id = uuid4(), uuid4()
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
        authorization_version=17,
        permission_codes=frozenset(permissions),
        has_permission=lambda permission: permission in permissions,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "permission", "domain"),
    (
        ("What equipment is installed?", AssetPermission.READ, "assets"),
        (
            "Which technicians have readiness evidence?",
            WorkforcePermission.READ,
            "workforce",
        ),
        (
            "Why did the customer message delivery fail?",
            CommunicationsPermission.READ,
            "communications",
        ),
    ),
)
async def test_natural_business_questions_route_only_to_authorized_source(
    question: str, permission: str, domain: str
) -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = ()
    await LiaService(retrieval=retrieval).ask(
        AsyncMock(), context=_context(permission), request=LiaRequest(question=question)
    )
    assert retrieval.retrieve.await_args.kwargs["domains"] == {domain}


def test_new_sources_require_explicit_permissions() -> None:
    assert not {"assets", "workforce", "communications"}.intersection(
        permitted_domain_names(_context())
    )
    assert {"assets", "workforce", "communications"} <= permitted_domain_names(
        _context(
            AssetPermission.READ,
            WorkforcePermission.READ,
            CommunicationsPermission.READ,
        )
    )


def test_context_contracts_are_bounded_and_non_mutating() -> None:
    assert ASSET_CONTRACT == "ASSET.LIA_CONTEXT.v1"
    assert WORKFORCE_CONTRACT == "WORKFORCE.LIA_CONTEXT.v1"
    assert {
        "vin",
        "serial_reference",
        "license_plate",
        "provider_identity",
    } <= PROTECTED_IDENTIFIERS
    source = Path(__file__).resolve().parents[2]
    asset_text = (source / "app/operational_assets/lia_context.py").read_text()
    workforce_text = (source / "app/workforce/lia_context.py").read_text()
    for forbidden in ("session.add(", "session.delete(", "session.commit("):
        assert forbidden not in asset_text
        assert forbidden not in workforce_text


def test_qualification_fingerprint_is_deterministic() -> None:
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "docs/architecture/lia/operational-intelligence-program-3-qualification.v1.json"
    )
    payload = json.loads(path.read_text())
    expected = payload.pop("qualification_fingerprint")
    assert (
        expected
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
