"""Build a deterministic, no-write QBO native Accounting admission plan."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.qbo_source.native_admission_plan import verify_native_admission_plan


def write_private_output(*, path: Path, plan: dict[str, object]) -> str:
    payload = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return str(plan["plan_sha256"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Qualify sealed QBO evidence for native Accounting admission"
    )
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    plan = verify_native_admission_plan(archive_root=args.archive_root)
    if args.output is not None:
        write_private_output(path=args.output.expanduser().resolve(), plan=plan)
    print(json.dumps(plan, sort_keys=True))


if __name__ == "__main__":
    main()
