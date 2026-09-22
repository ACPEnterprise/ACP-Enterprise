from app.customers.schemas import CustomerStatus
from app.customers.service import values_for_model


def test_domain_values_convert_enums_without_mutating_plain_values() -> None:
    values = values_for_model(
        {"status": CustomerStatus.ACTIVE, "display_name": "Customer"}
    )
    assert values == {"status": "active", "display_name": "Customer"}
