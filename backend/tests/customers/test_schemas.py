import pytest
from pydantic import ValidationError

from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    CustomerType,
    ServiceLocationCreate,
)


def test_customer_taxonomy_and_unknown_fields_are_strict() -> None:
    customer = CustomerCreate(
        customer_type=CustomerType.PROPERTY_MANAGEMENT,
        display_name="  Gulf Coast Management  ",
        legal_name="Gulf Coast Management LLC",
    )
    assert customer.display_name == "Gulf Coast Management"
    with pytest.raises(ValidationError):
        CustomerCreate.model_validate(
            {
                "customer_type": "individual",
                "display_name": "Legacy taxonomy",
            }
        )
    with pytest.raises(ValidationError):
        CustomerCreate.model_validate(
            {
                "customer_type": "residential",
                "display_name": "Strict Customer",
                "company_id": "00000000-0000-0000-0000-000000000001",
            }
        )


def test_contact_and_service_location_validation() -> None:
    contact = ContactCreate(
        first_name="Ada",
        last_name="Lovelace",
        email="ADA@EXAMPLE.COM",
        mobile_phone="7275550100",
        is_preferred=True,
    )
    assert contact.email == "ada@example.com"
    with pytest.raises(ValidationError):
        ContactCreate(
            first_name="Ada",
            last_name="Lovelace",
            is_preferred=True,
            active=False,
        )

    location = ServiceLocationCreate(
        address="123 Main Street",
        city="Clearwater",
        state="Florida",
        postal_code="33755",
        country="us",
        gps_latitude=27.9659,
        gps_longitude=-82.8001,
    )
    assert location.country == "US"
    with pytest.raises(ValidationError):
        ServiceLocationCreate(
            address="123 Main Street",
            city="Clearwater",
            state="Florida",
            postal_code="33755",
            gps_latitude=91,
        )
