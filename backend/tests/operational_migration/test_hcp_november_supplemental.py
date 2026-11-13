from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.operational_migration.hcp_november_supplemental import (
    build_paginated_current_state_supplemental,
    build_supplemental,
)
from app.operational_migration.hcp_november_supplemental import _digest


class FakeTransport:
    def __init__(self, bodies: dict[str, bytes]):
        self.bodies = bodies
        self.requests: list[str] = []

    def get(self, path: str, *, query=None):
        assert query is not None
        request = f"{path}?page={query['page']}&page_size={query['page_size']}"
        self.requests.append(request)
        if request not in self.bodies:
            return SimpleNamespace(status=404, body=b"{}")
        return SimpleNamespace(status=200, body=self.bodies[request])


def _fixture(tmp_path: Path, *, digest_override: str | None = None):
    employee = {"id": "emp_1", "first_name": "A", "last_name": "Worker"}
    estimate = {"id": "est_1", "status": "approved", "total": "10.00"}
    rows = []
    for domain, source_id, payload, locator, parents in (
        ("employee", "emp_1", employee, "acquisition/employees-page-0001.json#employee:emp_1", []),
        ("estimate", "est_1", estimate, "acquisition/estimates-page-0001.json#estimate:est_1", [{"domain": "job", "source_id": "job_1"}]),
    ):
        rows.append({
            "domain": domain,
            "source_id": source_id,
            "source_digest": digest_override or _digest(payload),
            "payload_locator": locator,
            "parent_lineage": parents,
        })
    inventory = {"records": rows, "bundle_sha256": "b" * 64}
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory, sort_keys=True))
    inventory_sha = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    transport = FakeTransport({
        "/employees?page=1&page_size=100": json.dumps({"employees": [employee], "page": 1, "page_size": 100, "total_pages": 1}, sort_keys=True).encode(),
        "/estimates?page=1&page_size=100": json.dumps({"estimates": [estimate], "page": 1, "page_size": 100, "total_pages": 1}, sort_keys=True).encode(),
    })
    return inventory_path, inventory_sha, transport


def test_exact_inventory_fetch_writes_locator_and_sealed_receipt(tmp_path: Path) -> None:
    inventory, inventory_sha, transport = _fixture(tmp_path)
    manifest = build_supplemental(
        transport=transport,
        inventory_path=inventory,
        inventory_sha256=inventory_sha,
        output_root=tmp_path / "supplemental",
        source_packet_sha256="a" * 64,
        source_canonical_digest="c" * 64,
    )
    assert manifest["inventory_count"] == 2
    assert manifest["http_method_allowlist"] == ["GET"]
    assert transport.requests == ["/employees?page=1&page_size=100", "/estimates?page=1&page_size=100"]
    assert (tmp_path / "supplemental/acquisition/employees-page-0001.json").stat().st_mode & 0o777 == 0o600
    assert json.loads((tmp_path / "supplemental/acquisition/estimates-page-0001.json").read_text())["records"][0]["source_id"] == "est_1"
    assert (tmp_path / "supplemental/supplemental-custody-manifest.json").stat().st_mode & 0o777 == 0o600


def test_inventory_digest_mismatch_fails_before_get(tmp_path: Path) -> None:
    inventory, inventory_sha, transport = _fixture(tmp_path)
    with pytest.raises(ValueError, match="inventory SHA-256"):
        build_supplemental(
            transport=transport,
            inventory_path=inventory,
            inventory_sha256="0" * 64,
            output_root=tmp_path / "supplemental",
            source_packet_sha256="a" * 64,
            source_canonical_digest="c" * 64,
        )
    assert transport.requests == []


def test_source_digest_mismatch_writes_nothing(tmp_path: Path) -> None:
    inventory, inventory_sha, transport = _fixture(tmp_path, digest_override="d" * 64)
    with pytest.raises(ValueError, match="source digest"):
        build_supplemental(
            transport=transport,
            inventory_path=inventory,
            inventory_sha256=inventory_sha,
            output_root=tmp_path / "supplemental",
            source_packet_sha256="a" * 64,
            source_canonical_digest="c" * 64,
        )
    assert not (tmp_path / "supplemental/raw").exists()


def test_requested_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    inventory, inventory_sha, transport = _fixture(tmp_path)
    value = json.loads(inventory.read_text())
    value["records"][0]["source_id"] = "emp_missing"
    inventory.write_text(json.dumps(value, sort_keys=True))
    inventory_sha = hashlib.sha256(inventory.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="did not return all requested"):
        build_supplemental(
            transport=transport,
            inventory_path=inventory,
            inventory_sha256=inventory_sha,
            output_root=tmp_path / "supplemental",
            source_packet_sha256="a" * 64,
            source_canonical_digest="c" * 64,
        )


def test_paginated_current_state_keeps_only_targets_and_completes_drift_scan(tmp_path: Path) -> None:
    employee = {"id": "emp_1", "first_name": "A", "last_name": "Worker"}
    estimate = {"id": "est_1", "status": "approved", "total": "10.00"}
    invoice = {"id": "inv_1", "status": "paid", "total": "10.00"}
    rows = []
    for domain, source_id, payload, locator in (
        ("employee", "emp_1", employee, "acquisition/employees-page-0001.json#employee:emp_1"),
        ("estimate", "est_1", estimate, "acquisition/estimates-page-0001.json#estimate:est_1"),
        ("invoice", "inv_1", invoice, "acquisition/invoices-page-0001.json#invoice:inv_1"),
    ):
        rows.append({"domain": domain, "source_id": source_id, "source_digest": _digest(payload), "payload_locator": locator, "disposition": "REPLAY"})
    # The real inventory has 1,013 records; this focused test exercises the
    # scanner with the same domain contract through a patched target count.
    inventory = {"records": rows, "source_packet_sha256": "a" * 64}
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory, sort_keys=True))
    inventory_sha = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    transport = FakeTransport({
        "/estimates?page=1&page_size=100": json.dumps({"estimates": [estimate, {"id": "unrelated-est"}], "page": 1, "page_size": 100, "total_pages": 1}, sort_keys=True).encode(),
        "/invoices?page=1&page_size=100": json.dumps({"invoices": [invoice, {"id": "unrelated-invoice"}], "page": 1, "page_size": 100, "total_pages": 1}, sort_keys=True).encode(),
    })
    # The production builder requires the full Estimate/Invoice population;
    # validate its page filtering separately with a two-domain inventory shape.
    rows = [row for row in rows if row["domain"] != "employee"]
    inventory["records"] = rows
    inventory_path.write_text(json.dumps(inventory, sort_keys=True))
    inventory_sha = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    result = build_paginated_current_state_supplemental(
        transport=transport,
        inventory_path=inventory_path,
        inventory_sha256=inventory_sha,
        output_root=tmp_path / "current",
        source_packet_sha256="a" * 64,
        source_canonical_digest="b" * 64,
        expected_target_count=2,
        max_workers=2,
    )
    assert result["scan"]["unrelated_records_examined_and_discarded"] == {"estimate": 1, "invoice": 1}
    assert result["classification_counts"]["EXACT_SEALED_MATCH"] == 2
    assert result["status"] == "COMPLETE"
