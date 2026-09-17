from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[3] / "scripts" / "release-backend-pin-check.py"
    spec = importlib.util.spec_from_file_location("release_backend_pin_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_requirements_are_accepted(tmp_path: Path) -> None:
    module = _module()
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "package==1.2.3\npackage-extra[feature]==4.5.6; python_version >= '3.12'\n",
        encoding="utf-8",
    )

    assert module.unpinned_requirements(requirements) == ()


def test_ranges_and_unbounded_requirements_fail_closed(tmp_path: Path) -> None:
    module = _module()
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "safe==1.0.0\nranged>=2,<3\nunbounded\n",
        encoding="utf-8",
    )

    assert module.unpinned_requirements(requirements) == (
        f"{requirements}:2",
        f"{requirements}:3",
    )
