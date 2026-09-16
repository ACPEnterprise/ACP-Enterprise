from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[3] / "scripts" / "release-secret-custody-check.py"
    spec = importlib.util.spec_from_file_location("release_secret_custody_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_detects_high_confidence_secret_without_returning_value(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "configuration.txt"
    # Assemble the synthetic credential at runtime so the repository-wide scanner
    # does not correctly flag its own regression fixture as tracked secret material.
    synthetic_key = "AKIA" + "ABCDEFGHIJKLMNOP"
    path.write_text(f"credential={synthetic_key}", encoding="utf-8")

    assert module.scan_tracked_files([path]) == [(str(path), "aws_access_key")]


def test_ignores_documented_private_key_marker_without_key_material(
    tmp_path: Path,
) -> None:
    module = _module()
    path = tmp_path / "test_fixture.py"
    path.write_text('marker = "-----BEGIN PRIVATE KEY-----"', encoding="utf-8")

    assert module.scan_tracked_files([path]) == []
