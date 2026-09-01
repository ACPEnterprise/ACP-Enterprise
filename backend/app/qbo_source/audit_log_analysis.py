"""Safe analysis of the owner-supplied QBO current-environment Audit Log."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .evidence import (
    ControlEvidenceRegistry,
    EvidenceStoreError,
    ProtectedFilesystemEvidenceStore,
)

_DATE_FORMAT = "%b %d, %Y, %I:%M %p Eastern Standard Time"
_ENVIRONMENT_START = "2024-02-19"
_EASTERN = ZoneInfo("America/New_York")


def analyze_registered_audit_log(
    *,
    store: ProtectedFilesystemEvidenceStore,
    control_id: str,
    expected_raw_sha256: str,
) -> dict[str, object]:
    registration_path = store.root / "controls" / f"{control_id}.json"
    registration = store._read_json(registration_path)
    if registration.get("kind") != "audit_log":
        raise EvidenceStoreError("audit_control_kind_invalid")
    if registration.get("raw_sha256") != expected_raw_sha256:
        raise EvidenceStoreError("audit_control_digest_mismatch")
    source_path = store.root / "controls" / "raw" / f"{expected_raw_sha256}.csv"
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_raw_sha256:
        raise EvidenceStoreError("audit_control_digest_mismatch")
    metrics = _metrics(source_path)
    if metrics["earliest_event_date"] != _ENVIRONMENT_START:
        raise EvidenceStoreError("audit_environment_boundary_mismatch")
    document: dict[str, object] = {
        "schema_version": "qbo-current-environment-authority/v1",
        "control_id": control_id,
        "registration_digest": hashlib.sha256(
            registration_path.read_bytes()
        ).hexdigest(),
        "raw_sha256": expected_raw_sha256,
        **metrics,
        "owner_environment_start_authority": _ENVIRONMENT_START,
        "current_qbo_environment_authority_boundary": "2024-02-19",
        "historical_transaction_effective_dates": "PRESERVED_AS_SOURCE_EFFECTIVE_DATES",
        "import_backfill_classification": "POPULATION_LEVEL_BACKFILL_PROVED",
        "individual_backfill_lineage": "NOT_PROVED_BY_AUDIT_EXPORT_ALONE",
        "purge_classification": "CURRENT_ENVIRONMENT_PRE_IMPORT_RESET_EVENT",
        "purge_accounting_effect": "NOT_OPENING_BALANCE_AUTHORITY",
        "opening_balance_equity_events": "SETUP_EVIDENCE_NOT_BALANCE_CONTROL",
        "prior_file_opening_search": "CEASE_2021_2022_CURRENT_QBO_FILE_EVENT_SEARCH",
        "full_available_history": "PRESERVE_EFFECTIVE_DATED_IMPORTED_HISTORY_WITH_IMPORT_LINEAGE",
        "opening_accounting_authority": "CONTROL_REPORTS_REQUIRED_AT_2024-02-19_TRANSITION",
    }
    document["evidence_digest"] = _digest(document)
    analysis_digest = ControlEvidenceRegistry(store).register_authority_document(
        authority_id="qbo-current-environment-authority-v1", document=document
    )
    return {
        "state": "CURRENT_QBO_ENVIRONMENT_BOUNDARY_PROVED",
        "analysis_digest": analysis_digest,
        "raw_sha256": expected_raw_sha256,
        "earliest_event_date": metrics["earliest_event_date"],
        "import_administration_events": metrics["import_administration_events"],
        "desktop_company_import_event": metrics["desktop_company_import_event"],
        "purge_event": metrics["purge_event"],
        "opening_balance_marker_events": metrics["opening_balance_marker_events"],
    }


def _metrics(path: Path) -> dict[str, object]:
    dates: list[datetime] = []
    import_dates: list[datetime] = []
    categories: Counter[str] = Counter()
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["Date Changed", "User", "Event"]:
            raise EvidenceStoreError("audit_control_header_invalid")
        for row in reader:
            try:
                changed = datetime.strptime(
                    row["Date Changed"].strip(), _DATE_FORMAT
                ).replace(tzinfo=_EASTERN)
            except (KeyError, ValueError) as error:
                raise EvidenceStoreError("audit_control_date_invalid") from error
            actor = row["User"].strip().casefold()
            event = row["Event"].strip().casefold()
            dates.append(changed)
            if "import administration" in actor:
                import_dates.append(changed)
            if event == "imported quickbooks desktop edition company":
                categories["desktop_import"] += 1
            if event == "purge data":
                categories["purge"] += 1
            if "opening balance equity" in event:
                categories["opening_balance_marker"] += 1
    if not dates or not import_dates:
        raise EvidenceStoreError("audit_control_events_missing")
    if categories != Counter(
        {"opening_balance_marker": 2, "desktop_import": 1, "purge": 1}
    ):
        raise EvidenceStoreError("audit_setup_events_ambiguous")
    return {
        "event_count": len(dates),
        "earliest_event_date": min(dates).date().isoformat(),
        "latest_event_date": max(dates).date().isoformat(),
        "import_administration_events": len(import_dates),
        "import_window_start": min(import_dates).isoformat(),
        "import_window_end": max(import_dates).isoformat(),
        "desktop_company_import_event": categories["desktop_import"],
        "purge_event": categories["purge"],
        "opening_balance_marker_events": categories["opening_balance_marker"],
    }


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seal safe current-QBO-environment Audit Log authority"
    )
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--raw-sha256", required=True)
    arguments = parser.parse_args()
    result = analyze_registered_audit_log(
        store=ProtectedFilesystemEvidenceStore(
            root=arguments.evidence_root,
            repository_root=arguments.repository_root,
        ),
        control_id=arguments.control_id,
        expected_raw_sha256=arguments.raw_sha256,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
