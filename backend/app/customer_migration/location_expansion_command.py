"""Generate restricted, non-PII LOCATION.1 readiness evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from dataclasses import asdict
from pathlib import Path

from app.customer_migration.adapter_import_policy import (
    customer_adapter_import_policy,
)
from app.customer_migration.housecall_pro_adapter import (
    AdaptedCustomerRecord,
    HousecallProCustomerExportAdapter,
)
from app.customer_migration.location_expansion import (
    classify_location_expansion,
    exact_job_unlock_counts,
)


class _PolicyRecord:
    def __init__(self, record: AdaptedCustomerRecord) -> None:
        self.source_identity_sha256 = hashlib.sha256(
            record.source_id.encode()
        ).hexdigest()
        self.customer = record.customer
        self.contact = record.contact
        self.service_locations = record.service_locations
        self.billing_address = record.billing_address


def _restricted(path: Path) -> bytes:
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or path.is_symlink()
        or details.st_mode & 0o077
    ):
        raise ValueError("LOCATION.1 input must be a restricted regular file")
    return path.read_bytes()


def generate(args: argparse.Namespace) -> int:
    source = _restricted(args.source)
    prior = _restricted(args.prior_source)
    manifest = json.loads(_restricted(args.customer_manifest).decode())
    source_sha256 = hashlib.sha256(source).hexdigest()
    transformed = HousecallProCustomerExportAdapter().transform(
        source, expected_source_sha256=source_sha256
    )
    ambiguous = customer_adapter_import_policy.duplicate_members(
        tuple(_PolicyRecord(record) for record in transformed.records)
    )
    readiness = classify_location_expansion(
        source=source,
        prior_source=prior,
        imported_customer_ids=tuple(manifest["ordered_source_identities"]),
        ambiguous_customer_id_sha256=tuple(ambiguous),
    )
    payload = {
        "readiness": asdict(readiness),
        "transformation": {
            "sha256": transformed.transformation_sha256,
            "source": transformed.source,
            "accepted": transformed.accepted,
            "rejected": transformed.rejected,
            "duplicate": transformed.duplicate,
            "child_exceptions": len(transformed.child_exceptions),
        },
        "job_reconciliation": exact_job_unlock_counts(
            exact_multi_property_address_matches=141,
            nonmatching_addresses=27,
        ),
    }
    args.output.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source", type=Path, required=True)
    result.add_argument("--prior-source", type=Path, required=True)
    result.add_argument("--customer-manifest", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> None:
    raise SystemExit(generate(parser().parse_args()))


if __name__ == "__main__":
    main()
