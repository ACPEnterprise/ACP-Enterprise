from __future__ import annotations

import os
import inspect

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ACCESS_TOKEN_SIGNING_KEY", "test-customer-import-signing-key-32-chars")
os.environ.setdefault("SECURITY_TOKEN_HMAC_KEY", "test-customer-import-hmac-key-32-chars")

from app.customer_import.models import CustomerImportBatch, CustomerImportRow
from app.customer_import.router import (
    _customer_from_payload,
    _identity_systems,
    _requires_qualified_hcp_admission,
    _source_system,
    _source_identity_counts,
    _verified_new_source_identity,
    router,
    admit_customer_import,
    stage_customer_import,
)


def test_routes_expose_staging_readback_and_resumable_admission() -> None:
    paths = {(route.path, tuple(sorted(route.methods or ()))) for route in router.routes}
    assert ("/api/v1/customer-import/batches", ("POST",)) in paths
    assert ("/api/v1/customer-import/batches/{batch_id}", ("GET",)) in paths
    assert ("/api/v1/customer-import/batches/{batch_id}/admit", ("POST",)) in paths


def test_hcp_aliases_have_distinct_lineage_keys() -> None:
    assert _source_system("housecall_pro", "housecall_pro") != _source_system(
        "housecall_pro", "housecall_pro_source4"
    )
    assert _source_system("housecall_pro", "housecall_pro_source4").startswith(
        "housecall_pro:"
    )
    assert "housecall_pro_source4" in _identity_systems(
        "housecall_pro", "housecall_pro_source4"
    )
    assert "housecall_pro_source4" in _identity_systems("housecall_pro", "housecall_pro")
    assert _requires_qualified_hcp_admission("housecall_pro", "housecall_pro_source4")
    assert not _requires_qualified_hcp_admission("housecall_pro", "housecall_pro")


def test_long_lineage_keys_are_bounded_without_truncation_collision() -> None:
    first = _source_system("provider", "x" * 80)
    second = _source_system("provider", "y" * 80)
    assert len(first) <= 50
    assert len(second) <= 50
    assert first != second


def test_admission_projection_keeps_contact_and_location_evidence() -> None:
    customer, contact, location = _customer_from_payload(
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company_name": "",
            "email": "ada@example.test",
            "phone": "5551234567",
            "address": "1 Analytical Way",
            "city": "Example",
            "state": "NY",
            "postal_code": "10001",
        }
    )
    assert customer.display_name == "Ada Lovelace"
    assert contact is not None and contact.email == "ada@example.test"
    assert location is not None and location.postal_code == "10001"


def test_new_admission_requires_complete_unique_source_identity() -> None:
    payload = {
        "display_name": "Ada Lovelace",
        "email": "ada@example.test",
        "phone": "5551234567",
        "address": "1 Analytical Way",
        "city": "Example",
        "state": "NY",
        "postal_code": "10001",
    }
    assert _verified_new_source_identity(payload, _source_identity_counts([payload]))
    assert not _verified_new_source_identity({**payload, "email": ""}, _source_identity_counts([{**payload, "email": ""}]))
    assert not _verified_new_source_identity(payload, _source_identity_counts([payload, {**payload, "display_name": "Ada L."}]))


def test_persisted_models_include_batch_identity_and_processed_cursor() -> None:
    assert "batch_key" in CustomerImportBatch.__table__.columns
    assert "migration_run_id" in CustomerImportBatch.__table__.columns
    assert "processed" in CustomerImportRow.__table__.columns


def test_http_import_boundaries_commit_staging_and_admission() -> None:
    # The database dependency is request-scoped and deliberately does not
    # auto-commit. Keep this regression beside the route contract so a future
    # refactor cannot turn a successful response into a non-durable preview.
    assert "await session.commit()" in inspect.getsource(stage_customer_import)
    assert "await session.commit()" in inspect.getsource(admit_customer_import)
    assert "attempt_count" in CustomerImportRow.__table__.columns


def test_migration_run_counts_are_recorded_with_each_row_outcome() -> None:
    source = inspect.getsource(admit_customer_import)
    assert "run.source_count += 1; run.duplicate_count += 1" in source
    assert "run.source_count += 1; run.unresolved_count += 1" in source
    assert "run.source_count += 1; run.accepted_count += 1" in source
