"""Download and seal open-work HCP attachments through signed GET URLs only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

if __package__:
    from .hcp_operational_cutover_acquisition import _digest, _load_object, _now
else:
    from hcp_operational_cutover_acquisition import _digest, _load_object, _now

APPROVED_ATTACHMENT_HOST = (
    "housecall-web-request-attachments-production-us-west-2.s3-accelerate.amazonaws.com"
)
APPROVED_PATH_PREFIXES = ("/request_attachments/files/", "/attachments/")
MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024 * 1024


def _attachments(root: Path) -> list[dict[str, str]]:
    values: dict[str, dict[str, str]] = {}
    for path in sorted(root.glob("open-job-expanded-*-http-200.json")):
        detail = _load_object(path)
        rows = detail.get("attachments")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            source_id = row.get("id")
            url = row.get("url")
            if not isinstance(source_id, str) or not isinstance(url, str):
                raise TypeError("attachment is missing source ID or signed URL")
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or parsed.hostname != APPROVED_ATTACHMENT_HOST
                or not parsed.path.startswith(APPROVED_PATH_PREFIXES)
            ):
                raise ValueError("attachment URL is outside the approved GET host/path")
            candidate = {
                "source_id": source_id,
                "url": url,
                "file_name": str(row.get("file_name") or ""),
                "file_type": str(row.get("file_type") or ""),
            }
            existing = values.get(source_id)
            if existing is not None and existing != candidate:
                raise ValueError("conflicting attachment source identity")
            values[source_id] = candidate
    return [values[key] for key in sorted(values)]


def _download(root: Path, row: dict[str, str]) -> dict[str, Any]:
    source_id = row["source_id"]
    artifact = "attachment-{}.bin".format(
        hashlib.sha256(source_id.encode("utf-8")).hexdigest()
    )
    target = root / artifact
    digest = hashlib.sha256()
    size = 0
    request = Request(row["url"], headers={"Accept": "*/*"}, method="GET")
    with urlopen(request, timeout=90) as response, target.open("xb") as stream:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != APPROVED_ATTACHMENT_HOST:
            raise ValueError("attachment GET redirected outside the approved host")
        content_type = str(response.headers.get("Content-Type") or row["file_type"])
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ATTACHMENT_BYTES:
                raise ValueError("attachment exceeds the per-file custody limit")
            stream.write(chunk)
            digest.update(chunk)
    os.chmod(str(target), 0o600)
    return {
        "artifact": artifact,
        "content_sha256": digest.hexdigest(),
        "content_type": content_type,
        "size_bytes": size,
        "source_id": source_id,
        "source_url_sha256": hashlib.sha256(row["url"].encode("utf-8")).hexdigest(),
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    source = _load_object(
        args.artifact_addendum / "open-work-artifact-addendum-manifest.json"
    )
    expected = source.get("digest")
    actual = _digest({key: value for key, value in source.items() if key != "digest"})
    if expected != actual:
        raise ValueError("artifact addendum digest mismatch")
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(mode=0o700, parents=True)
    os.chmod(str(args.output), 0o700)
    started_at = _now()
    attachments = _attachments(args.artifact_addendum)
    results: list[dict[str, Any]] = []
    completed = 0
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_download, args.output, row): row["source_id"]
            for row in attachments
        }
        for future in as_completed(futures):
            results.append(future.result())
            with lock:
                completed += 1
                if completed % 25 == 0:
                    print(
                        json.dumps(
                            {
                                "attachments_downloaded": completed,
                                "total": len(attachments),
                            }
                        ),
                        flush=True,
                    )
    results.sort(key=lambda row: row["source_id"])
    total_bytes = sum(row["size_bytes"] for row in results)
    if total_bytes > MAX_TOTAL_BYTES:
        raise ValueError("attachment custody exceeds the total byte limit")
    if any(
        stat.S_IMODE((args.output / row["artifact"]).stat().st_mode) != 0o600
        for row in results
    ):
        raise ValueError("attachment custody file mode check failed")
    raw_seal = _digest(
        [
            {
                "artifact": row["artifact"],
                "content_sha256": row["content_sha256"],
                "size_bytes": row["size_bytes"],
                "source_id": row["source_id"],
            }
            for row in results
        ]
    )
    manifest: dict[str, Any] = {
        "acquisition": {"completed_at": _now(), "started_at": started_at},
        "attachments": results,
        "contract": "hcp-open-work-attachment-custody/v1",
        "count": len(results),
        "http_method_allowlist": ["GET"],
        "raw_content_seal": raw_seal,
        "source_artifact_addendum_digest": source["digest"],
        "state": "COMPLETE",
        "total_bytes": total_bytes,
    }
    manifest["digest"] = _digest(manifest)
    body = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    target = args.output / "attachment-custody-manifest.json"
    with target.open("xb") as stream:
        stream.write(body)
    os.chmod(str(target), 0o600)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-addendum", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 9))
    args = parser.parse_args()
    value = build(args)
    print(
        json.dumps(
            {
                "count": value["count"],
                "digest": value["digest"],
                "raw_content_seal": value["raw_content_seal"],
                "state": value["state"],
                "total_bytes": value["total_bytes"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
