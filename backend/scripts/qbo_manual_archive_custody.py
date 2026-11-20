"""Seal owner-supplied QBO accounting, payroll, and bank-feed exports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

CONTRACT: Final = "qbo-manual-archive-custody/v1"
EXPECTED_BANK_FEED_HEADER: Final = (
    "Date",
    "DESCRIPTION",
    "Payee",
    "Categorize or match",
    "AMOUNT",
)


class CustodyError(RuntimeError):
    """Raised when source evidence cannot be sealed without ambiguity."""


@dataclass(frozen=True)
class _CsvInventory:
    rows: int
    unique_rows: int
    row_hashes: frozenset[str]
    dataset_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    details = os.fstat(descriptor)
    if not stat.S_ISREG(details.st_mode):
        os.close(descriptor)
        raise CustodyError(f"source_not_regular:{path.name}")
    with os.fdopen(descriptor, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _validate_source(path: Path, repository_root: Path) -> None:
    details = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(details.st_mode):
        raise CustodyError(f"source_not_regular:{path.name}")
    if details.st_size <= 0:
        raise CustodyError(f"source_empty:{path.name}")
    if _is_within(path.resolve(), repository_root):
        raise CustodyError(f"source_inside_repository:{path.name}")


def _classify(path: Path) -> str:
    name = path.name
    if name == "All County Plumbing and Leak Nov 19, 2026.zip":
        return "accounting_source_archive"
    if name.startswith("All County Plumbing and Leak_") and path.suffix == ".xlsx":
        return "accounting_report"
    if name.startswith("AllCountyPlumbingAndLeak_") and path.suffix == ".xls":
        return "payroll_report_restricted_pii"
    if name.startswith("American_Express") and path.suffix == ".csv":
        return "pending_bank_feed_source"
    raise CustodyError(f"source_name_not_approved:{name}")


def _inventory_csv(path: Path) -> _CsvInventory:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        header = tuple(next(reader, ()))
        if header != EXPECTED_BANK_FEED_HEADER:
            raise CustodyError(f"bank_feed_header_invalid:{path.name}")
        rows = [tuple(value.strip() for value in row) for row in reader]
    if any(len(row) != len(EXPECTED_BANK_FEED_HEADER) for row in rows):
        raise CustodyError(f"bank_feed_row_width_invalid:{path.name}")
    canonical = [json.dumps(row, separators=(",", ":")) for row in rows]
    row_hashes = frozenset(
        hashlib.sha256(row.encode()).hexdigest() for row in canonical
    )
    dataset = json.dumps(rows, separators=(",", ":")).encode()
    return _CsvInventory(
        rows=len(rows),
        unique_rows=len(row_hashes),
        row_hashes=row_hashes,
        dataset_sha256=hashlib.sha256(dataset).hexdigest(),
    )


def _inventory_zip(path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            entry_path = Path(item.filename)
            if (
                item.is_dir()
                or entry_path.is_absolute()
                or ".." in entry_path.parts
                or len(entry_path.parts) != 1
                or item.filename in seen
            ):
                raise CustodyError("source_archive_layout_invalid")
            unix_mode = item.external_attr >> 16
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise CustodyError("source_archive_symlink_rejected")
            seen.add(item.filename)
            entries.append(
                {
                    "name": item.filename,
                    "uncompressed_bytes": item.file_size,
                    "compressed_bytes": item.compress_size,
                    "crc32": f"{item.CRC:08x}",
                }
            )
    if not entries:
        raise CustodyError("source_archive_empty")
    return sorted(entries, key=lambda value: str(value["name"]))


def _copy_exclusive(source: Path, destination: Path) -> str:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    destination_descriptor = os.open(destination, flags, 0o600)
    source_descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        details = os.fstat(source_descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_size <= 0:
            raise CustodyError(f"source_not_regular:{source.name}")
        digest = hashlib.sha256()
        with (
            os.fdopen(source_descriptor, "rb") as incoming,
            os.fdopen(destination_descriptor, "wb") as outgoing,
        ):
            while chunk := incoming.read(1024 * 1024):
                outgoing.write(chunk)
                digest.update(chunk)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    except BaseException:
        try:
            os.close(source_descriptor)
        except OSError:
            pass
        try:
            os.close(destination_descriptor)
        except OSError:
            pass
        destination.unlink(missing_ok=True)
        raise
    os.chmod(destination, 0o600)
    return digest.hexdigest()


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def seal_manual_archive(
    *,
    inputs: tuple[Path, ...],
    output_dir: Path,
    repository_root: Path,
    expected_pending_bank_rows: int = 102,
) -> dict[str, object]:
    """Copy exact sources into restricted custody and write a non-PII manifest."""
    repository = repository_root.resolve()
    destination = output_dir.resolve()
    if _is_within(destination, repository):
        raise CustodyError("custody_output_inside_repository")
    if destination.exists():
        raise CustodyError("custody_output_already_exists")
    if not inputs:
        raise CustodyError("custody_inputs_required")

    resolved_inputs = tuple(path.resolve() for path in inputs)
    if len(set(resolved_inputs)) != len(resolved_inputs):
        raise CustodyError("custody_duplicate_input")
    for source in resolved_inputs:
        _validate_source(source, repository)

    try:
        parent_details = destination.parent.lstat()
    except FileNotFoundError as error:
        raise CustodyError("custody_parent_missing") from error
    if (
        destination.parent.is_symlink()
        or not stat.S_ISDIR(parent_details.st_mode)
        or stat.S_IMODE(parent_details.st_mode) & 0o077
    ):
        raise CustodyError("custody_parent_not_restricted")
    destination.mkdir(mode=0o700)
    os.chmod(destination, 0o700)
    raw = destination / "raw"
    raw.mkdir(mode=0o700)
    os.chmod(raw, 0o700)
    try:
        copied: dict[Path, tuple[Path, str]] = {}
        for source in sorted(resolved_inputs, key=lambda item: item.name):
            target = raw / source.name
            source_digest = _copy_exclusive(source, target)
            if _sha256(target) != source_digest:
                raise CustodyError(f"custody_copy_digest_mismatch:{source.name}")
            if stat.S_IMODE(target.stat().st_mode) != 0o600:
                raise CustodyError(f"custody_copy_mode_invalid:{source.name}")
            copied[source] = (target, source_digest)

        bank_inventory = {
            source: _inventory_csv(target)
            for source, (target, _) in copied.items()
            if _classify(source) == "pending_bank_feed_source"
        }
        authoritative = [
            source
            for source, inventory in bank_inventory.items()
            if inventory.rows == expected_pending_bank_rows
        ]
        if len(authoritative) != 1:
            raise CustodyError("pending_bank_feed_authority_ambiguous")
        authoritative_source = authoritative[0]
        authority_hashes = bank_inventory[authoritative_source].row_hashes
        for source, inventory in bank_inventory.items():
            if (
                source != authoritative_source
                and not inventory.row_hashes <= authority_hashes
            ):
                raise CustodyError("pending_bank_feed_candidates_diverge")

        files: list[dict[str, object]] = []
        for source in sorted(resolved_inputs, key=lambda item: item.name):
            target, source_digest = copied[source]
            role = _classify(source)
            item: dict[str, object] = {
                "name": source.name,
                "role": role,
                "bytes": target.stat().st_size,
                "sha256": source_digest,
                "custody_mode": "0600",
            }
            if role == "pending_bank_feed_source":
                inventory = bank_inventory[source]
                item["safe_inventory"] = {
                    "rows": inventory.rows,
                    "unique_rows": inventory.unique_rows,
                    "dataset_sha256": inventory.dataset_sha256,
                    "authority": (
                        "AUTHORITATIVE_PENDING_UNPOSTED_SOURCE"
                        if source == authoritative_source
                        else "SUPERSEDED_SUBSET_RETAINED"
                    ),
                }
            elif role == "accounting_source_archive":
                item["safe_inventory"] = {"entries": _inventory_zip(target)}
            files.append(item)

        custody_set = hashlib.sha256(
            json.dumps(
                [{"name": item["name"], "sha256": item["sha256"]} for item in files],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        manifest: dict[str, object] = {
            "contract": CONTRACT,
            "sealed_at": datetime.now(timezone.utc).isoformat(),
            "repository_exclusion_verified": True,
            "financial_posting_performed": False,
            "qbo_write_performed": False,
            "payroll_execution_performed": False,
            "pending_bank_feed_rows": expected_pending_bank_rows,
            "pending_bank_feed_disposition": "UNPOSTED_SOURCE_EVIDENCE",
            "custody_set_sha256": custody_set,
            "file_count": len(files),
            "files": files,
        }
        _write_exclusive(
            destination / "custody-manifest.json",
            (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(),
        )
        return manifest
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path, action="append", required=True)
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--repository-root", type=Path, required=True)
    result.add_argument("--expected-pending-bank-rows", type=int, default=102)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        manifest = seal_manual_archive(
            inputs=tuple(args.input),
            output_dir=args.output_dir,
            repository_root=args.repository_root,
            expected_pending_bank_rows=args.expected_pending_bank_rows,
        )
    except CustodyError as error:
        print(json.dumps({"result": "REJECTED", "code": str(error)}))
        raise SystemExit(2) from None
    print(
        json.dumps(
            {
                "result": "SEALED",
                "file_count": manifest["file_count"],
                "custody_set_sha256": manifest["custody_set_sha256"],
                "pending_bank_feed_rows": manifest["pending_bank_feed_rows"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
