import re
import unicodedata


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
POSTAL_CODE_PATTERN = re.compile(r"^\d{5}(?:-\d{4})?$")


def optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if not 7 <= len(digits) <= 15:
        raise ValueError("Phone numbers must contain between 7 and 15 digits.")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}"


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 320 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def normalize_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).split())


def build_normalized_name(
    first_name: str | None,
    last_name: str | None,
    business_name: str | None,
) -> str:
    return normalize_search_text(
        " ".join(part for part in (first_name, last_name, business_name) if part)
    )


def build_normalized_address(
    address_line_1: str,
    address_line_2: str | None,
    city: str,
    state: str,
    postal_code: str,
) -> str:
    return normalize_search_text(
        " ".join(
            part
            for part in (
                address_line_1,
                address_line_2,
                city,
                state,
                postal_code,
            )
            if part
        )
    )
