"""Generate the backend's validated runtime copy of the canonical factory roadmap."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.platform.factory_control.roadmap import load_roadmap


def sync(source: Path, destination: Path) -> str:
    roadmap = load_roadmap(source)
    document = json.loads(source.read_bytes())
    generated = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(f"{generated}\n", encoding="ascii")
    destination.with_suffix(".sha256").write_text(
        f"{roadmap.digest}\n", encoding="ascii"
    )
    # Re-read exactly what the image will consume before declaring success.
    load_roadmap(destination, digest_path=destination.with_suffix(".sha256"))
    return roadmap.digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=BACKEND_ROOT.parent / "docs/factory/acp_full_system_roadmap.yaml",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=BACKEND_ROOT / "app/platform/factory_control/data/roadmap.json",
    )
    arguments = parser.parse_args()
    print(sync(arguments.source, arguments.destination))


if __name__ == "__main__":
    main()
