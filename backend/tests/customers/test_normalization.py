import pytest

from app.customers.normalization import (
    build_normalized_address,
    build_normalized_name,
    normalize_email,
    normalize_phone,
    normalize_search_text,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(727) 555-0100", "+17275550100"),
        ("1-727-555-0100", "+17275550100"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["123", "not-a-number", "1" * 16])
def test_normalize_phone_rejects_invalid_lengths(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_normalize_email_is_case_insensitive() -> None:
    assert normalize_email(" Owner@Example.COM ") == "owner@example.com"


def test_normalize_search_text_removes_punctuation_and_accents() -> None:
    assert normalize_search_text("  José's Plumbing, LLC  ") == "jose s plumbing llc"


def test_build_normalized_customer_name() -> None:
    assert (
        build_normalized_name("Ada", "Lovelace", "Analytical Engines")
        == "ada lovelace analytical engines"
    )


def test_build_normalized_address() -> None:
    assert (
        build_normalized_address("123 Main St.", None, "Clearwater", "FL", "33755")
        == "123 main st clearwater fl 33755"
    )
