import base64
import json

from app.main import app
from app.payroll import setup_router


def test_employee_setup_routes_are_bounded_and_separate_approval() -> None:
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/payroll/setup/employees/{employee_id}"]) == {"get"}
    assert set(paths["/api/v1/payroll/setup/employees/{employee_id}/compensations"]) == {"post"}
    assert set(paths["/api/v1/payroll/setup/employees/{employee_id}/inputs"]) == {"post"}
    assert set(paths["/api/v1/payroll/setup/compensations/{authority_id}/approve"]) == {"post"}
    assert set(paths["/api/v1/payroll/setup/inputs/{authority_id}/approve"]) == {"post"}


def test_protected_values_are_write_only() -> None:
    operation = app.openapi()["paths"]["/api/v1/payroll/setup/employees/{employee_id}"]["get"]
    assert "protected_values" not in repr(operation)


def test_protected_input_keyring_loads_from_secret_file(tmp_path, monkeypatch) -> None:
    key_file = tmp_path / "payroll-keyring.json"
    key_file.write_text(
        json.dumps({"preview-v1": base64.urlsafe_b64encode(b"k" * 32).decode()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(setup_router.settings, "payroll_input_active_kid", "preview-v1")
    monkeypatch.setattr(setup_router.settings, "payroll_input_encryption_keys", {})
    monkeypatch.setattr(
        setup_router.settings, "payroll_input_encryption_key_file", str(key_file)
    )

    service = setup_router._input_service()

    assert service._cipher is not None
