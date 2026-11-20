from __future__ import annotations

import csv
import json
import stat
import zipfile
from pathlib import Path

import pytest
from scripts.qbo_manual_archive_custody import CustodyError, seal_manual_archive


def _write_csv(path: Path, rows: int) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(
            ("Date", "DESCRIPTION", "Payee", "Categorize or match", "AMOUNT")
        )
        for index in range(rows):
            writer.writerow(("11/19/2026", f"row-{index}", "", "", str(index)))


def _sources(root: Path) -> tuple[Path, ...]:
    archive = root / "All County Plumbing and Leak Nov 19, 2026.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr("General_ledger.xlsx", b"xlsx")
    accounting = root / "All County Plumbing and Leak_Trial Balance.xlsx"
    accounting.write_bytes(b"xlsx")
    payroll = root / "AllCountyPlumbingAndLeak_PaycheckHistory_11192026_1816.xls"
    payroll.write_bytes(b"xls")
    subset = root / "American_Express.csv"
    authority = root / "American_Express (1).csv"
    _write_csv(subset, 2)
    _write_csv(authority, 3)
    return archive, accounting, payroll, subset, authority


def test_seals_restricted_non_git_custody_with_unposted_bank_authority(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = tmp_path / "source"
    repository.mkdir()
    source.mkdir()
    tmp_path.chmod(0o700)
    output = tmp_path / "custody"

    manifest = seal_manual_archive(
        inputs=_sources(source),
        output_dir=output,
        repository_root=repository,
        expected_pending_bank_rows=3,
    )

    assert manifest["pending_bank_feed_disposition"] == "UNPOSTED_SOURCE_EVIDENCE"
    assert manifest["financial_posting_performed"] is False
    assert manifest["qbo_write_performed"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "raw").stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "custody-manifest.json").stat().st_mode) == 0o600
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in (output / "raw").iterdir()
    )
    stored = json.loads((output / "custody-manifest.json").read_text())
    bank_files = {
        item["name"]: item["safe_inventory"]
        for item in stored["files"]
        if item["role"] == "pending_bank_feed_source"
    }
    assert bank_files["American_Express (1).csv"]["authority"] == (
        "AUTHORITATIVE_PENDING_UNPOSTED_SOURCE"
    )
    assert bank_files["American_Express.csv"]["authority"] == (
        "SUPERSEDED_SUBSET_RETAINED"
    )


def test_rejects_output_inside_repository_and_divergent_bank_candidates(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = tmp_path / "source"
    repository.mkdir()
    source.mkdir()
    tmp_path.chmod(0o700)
    inputs = list(_sources(source))

    with pytest.raises(CustodyError, match="custody_output_inside_repository"):
        seal_manual_archive(
            inputs=tuple(inputs),
            output_dir=repository / "evidence",
            repository_root=repository,
            expected_pending_bank_rows=3,
        )

    with inputs[3].open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(
            ("Date", "DESCRIPTION", "Payee", "Categorize or match", "AMOUNT")
        )
        writer.writerow(("11/19/2026", "row-0", "", "", "0"))
        writer.writerow(("11/19/2026", "divergent", "", "", "10"))
    with pytest.raises(CustodyError, match="pending_bank_feed_candidates_diverge"):
        seal_manual_archive(
            inputs=tuple(inputs),
            output_dir=tmp_path / "custody",
            repository_root=repository,
            expected_pending_bank_rows=3,
        )


def test_rejects_archive_traversal(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source = tmp_path / "source"
    repository.mkdir()
    source.mkdir()
    tmp_path.chmod(0o700)
    inputs = list(_sources(source))
    with zipfile.ZipFile(inputs[0], "w") as target:
        target.writestr("../escape.xlsx", b"xlsx")

    with pytest.raises(CustodyError, match="source_archive_layout_invalid"):
        seal_manual_archive(
            inputs=tuple(inputs),
            output_dir=tmp_path / "custody",
            repository_root=repository,
            expected_pending_bank_rows=3,
        )
