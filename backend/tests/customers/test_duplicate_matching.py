from difflib import SequenceMatcher

from app.customers.normalization import build_normalized_name


def test_similar_name_threshold_accepts_minor_variation() -> None:
    requested = build_normalized_name("Jonathan", "Smith", None)
    existing = build_normalized_name("Jonathon", "Smith", None)
    assert SequenceMatcher(None, requested, existing).ratio() >= 0.80


def test_similar_name_threshold_rejects_unrelated_names() -> None:
    requested = build_normalized_name("Jonathan", "Smith", None)
    existing = build_normalized_name("Maria", "Garcia", None)
    assert SequenceMatcher(None, requested, existing).ratio() < 0.80
