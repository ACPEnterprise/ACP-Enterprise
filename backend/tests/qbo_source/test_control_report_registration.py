from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from app.qbo_source.control_report_registration import (
    RegisterControlReport,
    register_control_report,
)
from app.qbo_source.evidence import ControlReportKind, EvidenceStoreError


def command(source: Path) -> RegisterControlReport:
    return RegisterControlReport(
        source_file=source,
        control_id="qbo-g5-gl-2021-07-07-2022-12-31-accrual-v1",
        kind=ControlReportKind.GENERAL_LEDGER,
        basis="accrual",
        start_date=date(2021, 7, 7),
        end_date=date(2022, 12, 31),
    )


def workbook(path: Path) -> None:
    path.write_bytes(b"PK\x03\x04synthetic-xlsx-archive")
    path.chmod(0o600)


def test_registers_untouched_report_outside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = tmp_path / "owner-report.xlsx"
    workbook(source)
    result = register_control_report(
        command=command(source),
        evidence_root=tmp_path / "protected",
        repository_root=repository,
    )
    assert result["state"] == "CONTROL_REPORT_REGISTERED"
    assert result["source_mutated"] is False
    assert source.read_bytes() == b"PK\x03\x04synthetic-xlsx-archive"
    raw = tuple((tmp_path / "protected/controls/raw").iterdir())
    assert len(raw) == 1
    assert raw[0].stat().st_mode & 0o777 == 0o600


def test_rejects_open_permissions_symlink_and_repository_source(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = tmp_path / "owner-report.xlsx"
    workbook(source)
    source.chmod(0o644)
    with pytest.raises(EvidenceStoreError, match="permissions_too_open"):
        register_control_report(
            command=command(source),
            evidence_root=tmp_path / "protected-a",
            repository_root=repository,
        )
    source.chmod(0o600)
    link = tmp_path / "report-link.xlsx"
    os.symlink(source, link)
    with pytest.raises(EvidenceStoreError, match="regular_file"):
        register_control_report(
            command=command(link),
            evidence_root=tmp_path / "protected-b",
            repository_root=repository,
        )
    inside = repository / "report.xlsx"
    workbook(inside)
    with pytest.raises(EvidenceStoreError, match="inside_repository"):
        register_control_report(
            command=command(inside),
            evidence_root=tmp_path / "protected-c",
            repository_root=repository,
        )


def test_replay_is_idempotent_and_conflict_fails(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = tmp_path / "owner-report.xlsx"
    workbook(source)
    kwargs = {
        "command": command(source),
        "evidence_root": tmp_path / "protected",
        "repository_root": repository,
    }
    first = register_control_report(**kwargs)
    assert register_control_report(**kwargs) == first
    source.write_bytes(b"PK\x03\x04changed")
    source.chmod(0o600)
    with pytest.raises(EvidenceStoreError, match="immutable_content_conflict"):
        register_control_report(**kwargs)
