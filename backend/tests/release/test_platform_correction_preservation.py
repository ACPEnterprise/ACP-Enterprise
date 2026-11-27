from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts/verify-platform-corrections.py"


def module():
    spec = importlib.util.spec_from_file_location("platform_corrections", SCRIPT)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def candidate_files(loaded) -> dict[str, str]:
    return {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in loaded.REQUIRED_PATHS
    }


def test_current_candidate_preserves_accepted_platform_corrections() -> None:
    loaded = module()

    assert loaded.evaluate_candidate_files(candidate_files(loaded)) == {
        "ci_runtime": "PASS",
        "node_runtime": "PASS",
        "redis_secret_custody": "PASS",
        "scheduling_timezone": "PASS",
        "release_clock_isolation": "PASS",
        "customer_test_isolation": "PASS",
    }


@pytest.mark.parametrize(
    ("path", "old", "new", "message"),
    (
        (
            ".github/workflows/immutable-ci-artifacts.yml",
            'scripts/qualify-backend-tests --python "$QUALIFICATION_PYTHON"',
            "scripts/qualify-backend-tests --python python",
            "absolute qualification Python",
        ),
        (
            ".node-version",
            "24.22.3",
            "20.19.0",
            "Node.js must remain pinned",
        ),
        (
            "scripts/qualify-backend-tests",
            '--user "$qualification_uid:$qualification_gid"',
            "",
            "mounted secret custody",
        ),
        (
            "frontend/src/routes/SchedulingRoute.test.tsx",
            'new Date("2026-08-13T14:30:00Z")',
            "new Date(2026, 7, 13, 10, 30)",
            "absolute UTC instant",
        ),
        (
            "backend/tests/release/test_preview_release_authorization.py",
            'monkeypatch.setattr(validator, "utc_now", lambda: NOW)',
            "",
            "freshness clock",
        ),
        (
            "frontend/src/components/customers/CustomerManagement.test.tsx",
            'vi.mock("./HistoricalCustomerSearch"',
            'vi.mock("./HistoricalCustomerSearchOmitted"',
            "HistoricalCustomerSearch",
        ),
    ),
)
def test_each_accepted_correction_fails_closed(
    path: str, old: str, new: str, message: str
) -> None:
    loaded = module()
    files = candidate_files(loaded)
    assert old in files[path]
    files[path] = files[path].replace(old, new, 1)

    with pytest.raises(loaded.PreservationError, match=message):
        loaded.evaluate_candidate_files(files)
