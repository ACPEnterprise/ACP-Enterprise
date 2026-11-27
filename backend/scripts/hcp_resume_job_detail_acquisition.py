"""Resume missing HCP Job detail acquisition through bounded GET requests only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .hcp_operational_cutover_acquisition import (
    GetOnlyClient,
    _digest,
    _load_object,
    _secret_file,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def _job_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in sorted(root.glob("jobs-page-*.json")):
        value = _load_object(page)
        page_rows = value.get("jobs")
        if not isinstance(page_rows, list):
            raise TypeError(f"{page} does not contain a jobs list")
        rows.extend(row for row in page_rows if isinstance(row, dict))
    return rows


def _existing_ids(root: Path) -> set[str]:
    result: set[str] = set()
    for path in root.glob("job-detail-*-http-200.json"):
        value = _load_object(path)
        if isinstance(value.get("id"), str):
            result.add(value["id"])
    return result


def _validate_private_directory(path: Path) -> None:
    if not path.is_dir():
        raise ValueError(f"directory is missing: {path}")
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise ValueError(f"directory must have mode 0700: {path}")


def build(args: argparse.Namespace) -> dict[str, Any]:
    _validate_private_directory(args.output)
    if stat.S_IMODE(args.output.stat().st_mode) != 0o700:
        raise ValueError("output directory must have mode 0700")
    api_base, api_key = _secret_file(args.secret_file)
    client = GetOnlyClient(api_base, api_key)
    existing = _existing_ids(args.existing_detail_root)
    rows = {str(row["id"]): row for row in _job_rows(args.jobs_root) if row.get("id")}
    missing = sorted(set(rows) - existing)
    checkpoint_path = args.output / "job-detail-resume-checkpoint.json"
    checkpoint: dict[str, Any]
    if checkpoint_path.exists():
        checkpoint = _load_object(checkpoint_path)
        if checkpoint.get("source_jobs_digest") != _digest(rows):
            raise ValueError("source job population changed; start a new checkpoint")
    else:
        checkpoint = {
            "contract": "hcp-job-detail-resume-checkpoint/v1",
            "created_at": _now(),
            "source_jobs_digest": _digest(rows),
            "source_job_count": len(rows),
            "results": {},
        }
    results = checkpoint.setdefault("results", {})
    if not isinstance(results, dict):
        raise TypeError("checkpoint results are invalid")
    statuses: dict[str, int] = {}
    for index, job_id in enumerate(missing, 1):
        prior = results.get(job_id)
        if isinstance(prior, dict) and prior.get("state") == "complete":
            continue
        if index > 1:
            time.sleep(args.min_interval)
        try:
            status, body = client.get(f"/jobs/{job_id}", {"expand[]": "attachments"})
            statuses[str(status)] = statuses.get(str(status), 0) + 1
            if status == 200:
                value = json.loads(body)
                if not isinstance(value, dict) or value.get("id") != job_id:
                    raise ValueError("provider detail identity mismatch")
                target = args.output / f"job-detail-{_hash(job_id)}-http-200.json"
                if target.exists():
                    raise FileExistsError(target)
                target.write_bytes(body)
                os.chmod(target, 0o600)
                results[job_id] = {
                    "attempted_at": _now(),
                    "artifact": target.name,
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "state": "complete",
                    "status": status,
                }
            else:
                results[job_id] = {
                    "attempted_at": _now(),
                    "state": "provider_response",
                    "status": status,
                }
        except Exception as error:  # noqa: BLE001 - checkpoint and continue
            results[job_id] = {
                "attempted_at": _now(),
                "error_class": type(error).__name__,
                "state": "retryable_failure",
            }
        checkpoint["updated_at"] = _now()
        _write_json(checkpoint_path, checkpoint)
        if index % args.checkpoint_every == 0:
            print(json.dumps({"processed": index, "remaining": len(missing) - index}))
    completed = sum(
        isinstance(value, dict) and value.get("state") == "complete"
        for value in results.values()
    )
    checkpoint["digest"] = _digest(
        {key: value for key, value in checkpoint.items() if key != "digest"}
    )
    _write_json(checkpoint_path, checkpoint)
    return {
        "checkpoint": str(checkpoint_path),
        "checkpoint_digest": checkpoint["digest"],
        "missing_before_run": len(missing),
        "newly_completed": completed,
        "status_counts": statuses,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-file", required=True, type=Path)
    parser.add_argument("--jobs-root", required=True, type=Path)
    parser.add_argument("--existing-detail-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--min-interval", type=float, default=2.0)
    parser.add_argument("--checkpoint-every", type=int, default=1)
    args = parser.parse_args()
    if args.min_interval < 0 or args.checkpoint_every < 1:
        raise SystemExit("invalid checkpoint or interval configuration")
    print(json.dumps(build(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
