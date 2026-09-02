from app.data_quality.catalog import CATALOG_DIGEST, QUALITY_CATALOG
from app.data_quality.service import DataQualityService


def test_catalog_is_versioned_unique_and_prohibits_automatic_correction() -> None:
    identities = [(rule.rule_id, rule.version) for rule in QUALITY_CATALOG]
    assert len(identities) == len(set(identities))
    assert all(rule.automated_correction_prohibited for rule in QUALITY_CATALOG)
    assert len(CATALOG_DIGEST) == 64
    assert {rule.domain for rule in QUALITY_CATALOG} >= {
        "CUSTOMERS", "LOCATIONS", "JOBS", "EMPLOYEES", "ESTIMATES",
        "INVOICES", "PAYMENTS", "INVENTORY", "SERVICE_AGREEMENTS",
        "ASSETS", "FLEET", "CUSTODY", "TIMEKEEPING", "MIGRATION_IDENTITIES",
    }


def test_issue_digest_is_stable_and_new_work_distinct_from_history() -> None:
    service = DataQualityService()
    customer = next(rule for rule in QUALITY_CATALOG if rule.rule_id == "DQ-CUSTOMER-001")
    migration = next(rule for rule in QUALITY_CATALOG if rule.rule_id == "DQ-MIGRATION-001")
    first = service._issue(customer, "safe-1", ("display identity",), "company-1")
    replay = service._issue(customer, "safe-1", ("display identity",), "company-1")
    historical = service._issue(migration, "safe-2", ("crosswalk",), "company-1")
    assert first == replay
    assert first.blocks_new_operation is True
    assert historical.blocks_new_operation is False
    assert historical.launch_impact == "HISTORICAL_ONLY"


def test_rule_digest_changes_with_evidence_contract() -> None:
    original = QUALITY_CATALOG[0]
    changed = type(original)(**{**original.__dict__, "version": original.version + 1})
    assert original.digest != changed.digest
