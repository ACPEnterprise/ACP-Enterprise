import pytest

from app.customer_migration.children import parse_contact, parse_service_location
from app.customer_migration.housecall_pro import (
    HousecallProCustomerMigration,
    LegacyCustomerImportRetiredError,
    UnresolvedRowError,
    normalized_header,
    parse_customer,
)


def test_housecall_pro_mapping_builds_existing_customer_domain_schemas() -> None:
    parsed = parse_customer(
        {
            "customer_id": "source-1",
            "display_name": "Example Customer",
            "first_name": "Example",
            "last_name": "Customer",
            "emails": "CUSTOMER@EXAMPLE.TEST",
            "mobile_number": "(727) 555-0101",
            "type": "homeowner",
            "service_address": "101 Test Ave",
            "service_city": "Testville",
            "service_state": "FL",
            "service_postal_code": "33755",
            "billing_address": "PO Box 101",
            "billing_city": "Testville",
            "billing_state": "FL",
            "billing_postal_code": "33756",
        }
    )

    assert parsed.source_id == "source-1"
    assert parsed.customer.customer_type.value == "residential"
    assert parsed.contact is not None
    assert parsed.contact.email == "customer@example.test"
    assert parsed.service_location is not None
    assert parsed.billing_address is not None


def test_housecall_pro_mapping_does_not_fabricate_identity_or_address_parts() -> None:
    with pytest.raises(UnresolvedRowError, match="customer_id"):
        parse_customer({"display_name": "No source identity"})

    with pytest.raises(UnresolvedRowError, match="separate address"):
        parse_customer(
            {
                "customer_id": "source-2",
                "display_name": "Combined Address",
                "service_address": "101 Test Ave",
            }
        )


def test_headers_normalize_without_guessing_semantics() -> None:
    assert normalized_header(" Billing Address Notes ") == "billing_address_notes"


@pytest.mark.asyncio
async def test_legacy_customer_operational_orchestration_is_retired() -> None:
    with pytest.raises(LegacyCustomerImportRetiredError, match="retired"):
        await HousecallProCustomerMigration().run()


def test_contact_and_location_rows_require_source_and_parent_identities() -> None:
    with pytest.raises(UnresolvedRowError, match="contact_id"):
        parse_contact({"customer_id": "customer-1"})
    with pytest.raises(UnresolvedRowError, match="customer_id"):
        parse_service_location({"service_location_id": "location-1"})


def test_contact_and_location_rows_use_existing_domain_validation() -> None:
    contact = parse_contact(
        {
            "contact_id": "contact-1",
            "customer_id": "customer-1",
            "first_name": "Synthetic",
            "last_name": "Contact",
            "email": "CONTACT@EXAMPLE.TEST",
            "preferred": "yes",
        }
    )
    location = parse_service_location(
        {
            "service_location_id": "location-1",
            "customer_id": "customer-1",
            "address": "201 Test Ave",
            "city": "Testville",
            "state": "FL",
            "postal_code": "33755",
        }
    )

    assert contact.data.email == "contact@example.test"
    assert contact.data.is_preferred
    assert location.data.country == "US"
