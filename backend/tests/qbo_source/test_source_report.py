from typing import cast

from app.qbo_source.accounting_evidence_projection import QboEvidenceProjectionError
from app.qbo_source.source_report import project_profit_and_loss


def _report() -> dict[str, object]:
    return {
        "Header": {
            "ReportName": "ProfitAndLoss",
            "StartPeriod": "2026-05-01",
            "EndPeriod": "2026-05-31",
            "ReportBasis": "Cash",
            "Currency": "USD",
            "Time": "2026-09-15T12:00:00-04:00",
        },
        "Columns": {
            "Column": [
                {"ColTitle": "Account"},
                {"ColTitle": "Total"},
            ]
        },
        "Rows": {
            "Row": [
                {
                    "Header": {"ColData": [{"value": "Income"}, {"value": ""}]},
                    "Rows": {
                        "Row": [
                            {
                                "type": "Data",
                                "ColData": [
                                    {"value": "Services"},
                                    {"value": "100.00"},
                                ],
                            }
                        ]
                    },
                    "Summary": {
                        "ColData": [{"value": "Total Income"}, {"value": "100.00"}]
                    },
                }
            ]
        },
    }


def test_profit_and_loss_is_visibly_source_backed_and_retains_provider_values() -> None:
    result = project_profit_and_loss(
        _report(), realm_id="9130357972400696", expected_company_name="All County"
    )
    assert result["authority"] == "QBO_SOURCE_BACKED"
    assert result["provider_environment"] == "production"
    assert result["realm_id"] == "9130357972400696"
    assert result["start_date"] == "2026-05-01"
    assert result["end_date"] == "2026-05-31"
    assert result["accepted_as_acp_accounting"] is False
    assert result["mutation_authority"] == "none"
    rows = cast(list[dict[str, object]], result["rows"])
    assert rows[1]["values"] == ["Services", "100.00"]


def test_non_profit_and_loss_provider_response_fails_closed() -> None:
    report = _report()
    header = cast(dict[str, object], report["Header"])
    header["ReportName"] = "BalanceSheet"
    try:
        project_profit_and_loss(
            report, realm_id="realm", expected_company_name="All County"
        )
    except QboEvidenceProjectionError as error:
        assert str(error) == "qbo_profit_and_loss_identity_invalid"
    else:
        raise AssertionError("unexpected report type was accepted")
