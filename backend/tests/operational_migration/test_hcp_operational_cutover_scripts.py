from __future__ import annotations

import argparse
import ast
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from typing_extensions import Self

from scripts import hcp_open_work_artifact_addendum as artifact_addendum
from scripts import hcp_open_work_attachment_custody as attachment_custody
from scripts import hcp_operational_cutover_acquisition as acquisition
from scripts import hcp_operational_cutover_finalize as finalize

MODULES = (
    acquisition,
    artifact_addendum,
    attachment_custody,
    finalize,
)


class _Response:
    status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        return b"{}"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_get_only_client_uses_a_fixed_host_and_get_method(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured = []

    def open_request(request, *, timeout):  # type: ignore[no-untyped-def]
        captured.append((request, timeout))
        return _Response()

    monkeypatch.setattr(acquisition, "urlopen", open_request)
    client = acquisition.GetOnlyClient(acquisition.APPROVED_API_BASE, "test-key")

    status, body = client.get("/company", {"page": 1})

    assert (status, body) == (200, b"{}")
    assert len(captured) == 1
    request, timeout = captured[0]
    assert request.get_method() == "GET"
    assert request.full_url == "https://api.housecallpro.com/company?page=1"
    assert timeout == 45
    assert not any(
        hasattr(client, method) for method in ("post", "put", "patch", "delete")
    )
    with pytest.raises(ValueError, match="API base is not approved"):
        acquisition.GetOnlyClient("https://example.com", "test-key")
    with pytest.raises(ValueError, match="relative API path"):
        client.get("https://example.com/company")


def test_evidence_store_is_create_once_private_and_sealed(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    store = acquisition.EvidenceStore(output)
    body = b'{"id":"provider-id"}'

    artifact = store.write_raw(
        "company-http-200.json",
        body,
        request="GET /company",
        http_status=200,
        family="company",
        record_count=1,
    )

    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
    assert store.artifacts[0]["sha256"] == acquisition._digest_bytes(body)
    with pytest.raises(FileExistsError):
        acquisition.EvidenceStore(output)


def test_secret_configuration_requires_private_mode_and_approved_host(
    tmp_path: Path,
) -> None:
    secret_file = tmp_path / "hcp.env"
    secret_file.write_text(
        "HOUSECALL_PRO_API_KEY=test-only\n"
        "HOUSECALL_PRO_API_BASE=https://api.housecallpro.com\n",
        encoding="utf-8",
    )
    os.chmod(secret_file, 0o600)

    assert acquisition._secret_file(secret_file) == (
        acquisition.APPROVED_API_BASE,
        "test-only",
    )

    secret_file.write_text(
        "HOUSECALL_PRO_API_KEY=test-only\nHOUSECALL_PRO_API_BASE=https://example.com\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="API base is not approved"):
        acquisition._secret_file(secret_file)


def test_classification_covers_create_update_replay_and_hold() -> None:
    payload = {"id": "source-1", "name": "Current"}
    digest = acquisition._digest(payload)

    create = acquisition._classify(
        domain="job", source_id="source-1", payload=payload, prior={}
    )
    update = acquisition._classify(
        domain="job",
        source_id="source-1",
        payload=payload,
        prior={("job", "source-1"): "different"},
    )
    replay = acquisition._classify(
        domain="job",
        source_id="source-1",
        payload=payload,
        prior={("job", "source-1"): digest},
    )
    hold = acquisition._classify(
        domain="invoice", source_id="source-1", payload=payload, prior={}
    )

    assert [row["disposition"] for row in (create, update, replay, hold)] == [
        "CREATE",
        "UPDATE",
        "REPLAY",
        "HOLD",
    ]


def test_network_and_mutation_boundary_is_static_and_get_only() -> None:
    forbidden_imports = {
        "asyncpg",
        "boto3",
        "httpx",
        "psycopg",
        "requests",
        "sqlalchemy",
    }
    forbidden_methods = {"commit", "delete", "execute", "patch", "post", "put"}
    request_calls = 0
    detail_calls = 0

    for module in MODULES:
        source_path = Path(module.__file__ or "")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        strings = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        assert not any(
            value.startswith(("/Users/", "/home/")) or ":\\" in value
            for value in strings
        )

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                assert not any(
                    name.split(".", 1)[0] in forbidden_imports for name in names
                )
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr.lower() not in forbidden_methods
            if isinstance(node.func, ast.Name) and node.func.id == "Request":
                request_calls += 1
                methods = [
                    keyword.value.value
                    for keyword in node.keywords
                    if keyword.arg == "method"
                    and isinstance(keyword.value, ast.Constant)
                ]
                assert methods == ["GET"]
            if isinstance(node.func, ast.Name) and node.func.id == "_get_detail":
                detail_calls += 1
                assert len(node.args) == 2

    assert request_calls == 2
    assert detail_calls == 6


def test_finalizer_derives_legacy_holds_and_is_path_independent(
    tmp_path: Path,
) -> None:
    acquisition_root = tmp_path / "acquisition"
    acquisition_root.mkdir()
    reconciliation = [
        {
            "legacy_source_id": "legacy-a",
            "reason": "successor authority is not admitted",
        },
        {
            "legacy_source_id": "legacy-b",
            "reason": "provider evidence is not unique",
        },
    ]
    source = {
        "acquisition": {"completed_at": "2026-11-10T12:00:00+00:00"},
        "classifications": [],
        "contract": "hcp-operational-cutover-acquisition/v1",
        "coverage": {"appointment_http_statuses": {"200": 0, "400": 0}},
        "open_work_reconciliation": {
            "legacy_appointment_duplicate_risk": reconciliation,
            "prior_locationless_jobs": [],
        },
    }
    source["digest"] = acquisition._digest(source)
    _write_json(acquisition_root / "operational-acquisition-manifest.json", source)
    _write_json(
        acquisition_root / "isolated-clone-provider-observations.json",
        {"records": []},
    )
    prior_delta = tmp_path / "prior-delta.json"
    _write_json(prior_delta, {"contract": "prior/v1", "records": []})

    def build(output: Path) -> dict[str, Any]:
        return finalize.build(
            argparse.Namespace(
                acquisition_root=acquisition_root,
                artifact_addendum=None,
                attachment_custody=None,
                prior_delta=prior_delta,
                output=output,
            )
        )

    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    first = build(first_output)
    second = build(second_output)

    assert first == second
    assert first["unresolved_holds"]["legacy_appointment_duplicate_risk"] == 2
    assert first["classification_totals"] == {"HOLD": 2}
    assert first["provider_observations"] == "provider-observations.json"
    assert stat.S_IMODE(first_output.stat().st_mode) == 0o700
    assert stat.S_IMODE((first_output / "gate-packet.json").stat().st_mode) == 0o600
