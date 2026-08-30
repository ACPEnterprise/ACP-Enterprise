import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "docs/architecture/business-economics-preview-acceptance-dataset.v1.json"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_preview_acceptance_dataset_has_independently_reconciled_expectations() -> None:
    dataset = json.loads(PATH.read_text(encoding="utf-8"))
    unsigned = dict(dataset)
    fingerprint = unsigned.pop("dataset_fingerprint")
    assert fingerprint == _digest(unsigned)
    jobs = dataset["current_period"]["jobs"]
    expected = dataset["current_period"]["expected"]
    assert sum(item["revenue_minor"] for item in jobs) == expected[
        "recognized_revenue_minor"
    ]
    assert sum(item["labor_minor"] for item in jobs) == expected["labor_minor"]
    assert sum(item["materials_minor"] for item in jobs) == expected["materials_minor"]
    assert sum(item["contribution_minor"] for item in jobs) == expected[
        "contribution_minor"
    ]
    assert expected["direct_cost_minor"] == (
        expected["labor_minor"] + expected["materials_minor"]
    )
    branch_totals = {
        branch: {
            "revenue": sum(
                item["revenue_minor"] for item in jobs if item["branch"] == branch
            ),
            "contribution": sum(
                item["contribution_minor"]
                for item in jobs
                if item["branch"] == branch
            ),
        }
        for branch in {item["branch"] for item in jobs}
    }
    assert branch_totals["Main"] == {"revenue": 150000, "contribution": 50000}
    assert branch_totals["North"] == {"revenue": 40000, "contribution": -10000}
    comparison = dataset["comparison_fixture"]
    assert (
        comparison["current_revenue_minor"] - comparison["prior_revenue_minor"]
        == comparison["expected_revenue_change_minor"]
    )
    assert (
        comparison["current_contribution_minor"]
        - comparison["prior_contribution_minor"]
        == comparison["expected_contribution_change_minor"]
    )
    assert dataset["real_financial_data"] == "PROHIBITED"
