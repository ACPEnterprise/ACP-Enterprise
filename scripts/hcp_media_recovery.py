#!/usr/bin/env python3
"""Reconcile or recover sealed HCP attachment bodies with resumable checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.source_history.hcp_media_recovery import (
    AttachmentReference,
    RecoveredMedia,
    artifact_name,
    reconcile_media,
)

MAX_MEDIA_BYTES = 100 * 1024 * 1024


def _load(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"protected input is unavailable or a symlink: {path}")
    return json.loads(path.read_text())


def _write_private(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _references(value: object) -> tuple[AttachmentReference, ...]:
    if not isinstance(value, dict) or not isinstance(value.get("attachments"), list):
        raise TypeError("reference manifest must contain attachments")
    return tuple(AttachmentReference(**row) for row in value["attachments"])


def _checkpoint(value: object) -> tuple[RecoveredMedia, ...]:
    if not isinstance(value, dict) or not isinstance(value.get("recovered"), list):
        raise TypeError("checkpoint must contain recovered media")
    return tuple(RecoveredMedia(**row) for row in value["recovered"])


def _download(url: str, target: Path) -> RecoveredMedia:
    digest = hashlib.sha256()
    size = 0
    temporary = target.with_suffix(".partial")
    request = Request(url, headers={"Accept": "*/*"}, method="GET")
    try:
        with urlopen(request, timeout=90) as response, temporary.open("xb") as stream:
            if response.geturl() != url:
                raise ValueError("redirected media retrieval is not allowed")
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_MEDIA_BYTES:
                    raise ValueError("attachment exceeds recovery size limit")
                stream.write(chunk)
                digest.update(chunk)
        os.chmod(temporary, 0o600)
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return RecoveredMedia("", digest.hexdigest(), size, target.name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()

    references = _references(_load(args.references))
    recovered = _checkpoint(_load(args.checkpoint)) if args.checkpoint.exists() else ()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    plan = reconcile_media(references, recovered)

    if args.recover:
        current = {row.source_attachment_id: row for row in recovered}
        for item in plan.items:
            if item.disposition != "RETRIEVE" or item.reference.signed_get_url is None:
                continue
            target = args.output / artifact_name(item.reference.source_attachment_id)
            result = _download(item.reference.signed_get_url, target)
            current[item.reference.source_attachment_id] = RecoveredMedia(
                item.reference.source_attachment_id,
                result.content_sha256,
                result.size_bytes,
                result.artifact_name,
            )
            _write_private(
                args.checkpoint,
                {
                    "contract": "hcp-media-recovery-checkpoint/v1",
                    "recovered": [
                        asdict(row)
                        for row in sorted(
                            current.values(),
                            key=lambda value: value.source_attachment_id,
                        )
                    ],
                },
            )
        plan = reconcile_media(references, tuple(current.values()))

    receipt = {
        "contract": "hcp-media-recovery-receipt/v1",
        "counts": plan.counts,
        "http_method_allowlist": list(plan.http_method_allowlist),
        "plan_digest": plan.plan_digest,
        "protected_recovery_executed": args.recover,
        "provider_writes_allowed": plan.provider_writes_allowed,
    }
    _write_private(args.output / "recovery-receipt.json", receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
