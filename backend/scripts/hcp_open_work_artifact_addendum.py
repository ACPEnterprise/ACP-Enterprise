"""Seal corrected GET-only expanded Job details for current HCP open work."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

if __package__:
    from .hcp_operational_cutover_acquisition import (
        OPEN_JOB_STATUSES,
        EvidenceStore,
        GetOnlyClient,
        _digest,
        _get_detail,
        _load_object,
        _now,
        _secret_file,
        _status,
    )
else:
    from hcp_operational_cutover_acquisition import (
        OPEN_JOB_STATUSES,
        EvidenceStore,
        GetOnlyClient,
        _digest,
        _get_detail,
        _load_object,
        _now,
        _secret_file,
        _status,
    )


def _jobs(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(root.glob("jobs-page-*.json")):
        value = _load_object(path)
        rows = value.get("jobs")
        if not isinstance(rows, list):
            raise TypeError(f"{path} does not contain Jobs")
        result.extend(row for row in rows if isinstance(row, dict))
    return result


def build(args: argparse.Namespace) -> dict[str, Any]:
    source = _load_object(
        args.acquisition_root / "operational-acquisition-manifest.json"
    )
    expected = source.get("digest")
    actual = _digest({key: value for key, value in source.items() if key != "digest"})
    if expected != actual:
        raise ValueError("operational acquisition manifest digest mismatch")
    started_at = _now()
    api_base, api_key = _secret_file(args.secret_file)
    client = GetOnlyClient(api_base, api_key)
    store = EvidenceStore(args.output)
    open_jobs = sorted(
        (
            row
            for row in _jobs(args.acquisition_root)
            if _status(row) in OPEN_JOB_STATUSES
        ),
        key=lambda row: row["id"],
    )
    statuses: Counter = Counter()
    child_counts: Counter = Counter()
    child_identity_counts: Counter = Counter()
    for index, job in enumerate(open_jobs, 1):
        status, value = _get_detail(
            client,
            store,
            family="open-job-expanded",
            native_id=job["id"],
            path="/jobs/{}".format(job["id"]),
            query={"expand[]": "attachments"},
        )
        statuses[str(status)] += 1
        if status == 200 and isinstance(value, dict):
            for key in ("notes", "attachments", "forms"):
                rows = value.get(key)
                if not isinstance(rows, list):
                    continue
                child_counts[key] += len(rows)
                child_identity_counts[key] += sum(
                    isinstance(row, dict) and isinstance(row.get("id"), str)
                    for row in rows
                )
        if index % 50 == 0:
            print(
                json.dumps({"open_job_details": index, "total": len(open_jobs)}),
                flush=True,
            )
    artifacts = sorted(store.artifacts, key=lambda row: row["artifact"])
    raw_seal = _digest(
        [
            {
                "artifact": row["artifact"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
            }
            for row in artifacts
        ]
    )
    manifest: dict[str, Any] = {
        "acquisition": {"completed_at": _now(), "started_at": started_at},
        "artifacts": artifacts,
        "child_counts": dict(sorted(child_counts.items())),
        "child_identity_counts": dict(sorted(child_identity_counts.items())),
        "contract": "hcp-open-work-artifact-addendum/v1",
        "http_method_allowlist": ["GET"],
        "http_status_counts": dict(sorted(statuses.items())),
        "open_jobs": len(open_jobs),
        "raw_page_seal": raw_seal,
        "source_manifest_digest": source["digest"],
        "state": "COMPLETE" if set(statuses) <= {"200"} else "PARTIAL",
    }
    manifest["digest"] = _digest(manifest)
    store.write_json("open-work-artifact-addendum-manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-file", required=True, type=Path)
    parser.add_argument("--acquisition-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    value = build(args)
    print(
        json.dumps(
            {
                "child_counts": value["child_counts"],
                "child_identity_counts": value["child_identity_counts"],
                "digest": value["digest"],
                "http_status_counts": value["http_status_counts"],
                "raw_page_seal": value["raw_page_seal"],
                "state": value["state"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
