from pathlib import Path


def test_customer_context_contract_documents_minimum_necessary_boundary() -> None:
    root = Path(__file__).resolve().parents[3]
    contract = (
        root / "docs/architecture/lia/customer-context-composition-v1.md"
    ).read_text()
    for required in (
        "CUSTOMER.LIA_CONTEXT.v1",
        "does not reveal existence",
        "up to 10",
        "raw Customer or Job notes",
        "Company and Branch predicates",
        "grants no mutation authority",
    ):
        assert required.casefold() in contract.casefold()
