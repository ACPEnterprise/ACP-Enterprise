from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_cutover_smoke_is_read_only_role_bounded_and_secret_safe() -> None:
    script = (
        REPOSITORY_ROOT / "scripts/verify-beta-payroll-dispatch-cutover.sh"
    ).read_text(encoding="utf-8")

    assert "https://beta.twelve-hats.com" in script
    assert 'for route in payroll scheduling dispatch' in script
    assert "/api/v1/payroll/operations/summary" in script
    assert "/api/v1/scheduling/appointments" in script
    assert "/api/v1/dispatch/board" in script
    assert "/api/v1/employee-operations/me/day" in script
    assert "PAYROLL_TOKEN_FILE" in script
    assert "DISPATCH_TOKEN_FILE" in script
    assert "EMPLOYEE_TOKEN_FILE" in script
    assert "Token reference must be mode 0600" in script
    assert "--config" in script
    assert "BLOCKED_SANCTIONED_TOKEN_REQUIRED" in script
    assert "--request POST" not in script
    assert "-X POST" not in script
    assert "Authorization: Bearer $token" not in script
    assert "cat " not in script


def test_cutover_smoke_does_not_target_production() -> None:
    script = (
        REPOSITORY_ROOT / "scripts/verify-beta-payroll-dispatch-cutover.sh"
    ).read_text(encoding="utf-8")

    assert "app.twelve-hats.com" not in script
    assert "preview.allcountyhomeservices.com" not in script
