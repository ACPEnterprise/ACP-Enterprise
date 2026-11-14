"""Run the isolated Phase-1 synthetic business lifecycle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.simulation.phase1 import (
    human_report,
    run_accounting_lifecycle,
    run_accounting_regression_scenarios,
    run_phase1,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    receipt = run_phase1()
    receipt["accounting_operational_independence"] = run_accounting_lifecycle()
    receipt["accounting_regressions"] = run_accounting_regression_scenarios()
    args.receipt.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    args.receipt.chmod(0o600)
    args.report.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.report.write_text(human_report(receipt))
    args.report.chmod(0o600)
    print(human_report(receipt), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
