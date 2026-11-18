"""Emit protected-value-free field readiness for a blind Payroll input packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.payroll.blind_replay import collect_readiness, parse_blind_replay_input


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("blind Payroll packet must be a JSON object")
    employees = payload.get("employees")
    if not isinstance(employees, list):
        raise SystemExit("blind Payroll packet must contain an employees list")
    readiness = collect_readiness(employees)
    complete = False
    validation_error: str | None = None
    if readiness and all(
        all(state == "PRESENT" for state in fields.values())
        for fields in readiness.values()
    ):
        try:
            parse_blind_replay_input(payload)
            complete = True
        except ValueError as error:
            validation_error = str(error)
    result = {
        "contract": "payroll.blind-replay-readiness.v1",
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "employees": [
            {
                "employee": employee,
                "status": "COMPLETE"
                if all(state == "PRESENT" for state in fields.values())
                else "INCOMPLETE",
                "fields": fields,
                "missing_fields": [
                    field for field, state in fields.items() if state == "MISSING"
                ],
            }
            for employee, fields in readiness.items()
        ],
        "validation_error": validation_error,
        "sensitive_values_included": False,
        "calculation_performed": False,
        "qbo_answer_key_read": False,
    }
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
