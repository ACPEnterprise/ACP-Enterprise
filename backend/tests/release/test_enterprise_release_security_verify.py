from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path


def _module():
    path = Path(__file__).parents[3] / "scripts" / "enterprise-release-security-verify"
    loader = importlib.machinery.SourceFileLoader(
        "enterprise_release_security_verify", str(path)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def test_expected_cve_set_is_closed() -> None:
    module = _module()
    assert len(module.REQUIRED_CVES) == 15
    assert "CVE-2026-66046" in module.REQUIRED_CVES


def test_disposition_contract_has_all_required_dimensions() -> None:
    module = _module()
    assert len(module.REQUIRED_FIELDS) == 20
    assert {
        "installed_version",
        "runtime_reachability",
        "disposition",
    } <= module.REQUIRED_FIELDS
