from app.operational_migration.hcp_discrepancy_quarantine import (
    QUARANTINE_REASON,
    _derive_records,
)


def _record(source_id: str, disposition: str = "REPLAY", parents=()):
    return {
        "domain": "estimate",
        "source_id": source_id,
        "disposition": disposition,
        "assertion": "create",
        "source_digest": "a" * 64,
        "acquired_at": "2026-11-01T00:00:00+00:00",
        "payload": {"source_id": source_id},
        "parent_keys": list(parents),
    }


def _domain_record(domain: str, source_id: str, parents=()):
    return {
        "domain": domain,
        "source_id": source_id,
        "disposition": "REPLAY",
        "assertion": "create",
        "source_digest": "b" * 64,
        "acquired_at": "2026-11-01T00:00:00+00:00",
        "payload": {},
        "parent_keys": list(parents),
    }


def _valid_estimate_record(source_id: str, parents=()):
    item = _record(source_id, parents=parents)
    item["payload"] = {
        "id": "csr_1",
        "customer": {
            "company": None,
            "company_id": "com_1",
            "company_name": None,
            "created_at": None,
            "email": None,
            "first_name": "A",
            "home_number": None,
            "id": "cus_1",
            "kind": "person",
            "last_name": "B",
            "lead_source": None,
            "mobile_number": None,
            "notes": None,
            "notifications_enabled": True,
            "tags": [],
            "updated_at": None,
            "work_number": None,
        },
        "address": {
            "city": "Austin",
            "country": "US",
            "id": "adr_1",
            "latitude": None,
            "longitude": None,
            "state": "TX",
            "street": "1 Main",
            "street_line_2": None,
            "type": "service",
            "zip": "78701",
        },
        "work_timestamps": {
            "completed_at": None,
            "on_my_way_at": None,
            "started_at": None,
        },
        "schedule": {
            "appointments": [],
            "arrival_window": None,
            "scheduled_end": None,
            "scheduled_end_local": None,
            "scheduled_start": None,
            "scheduled_start_local": None,
            "time_zone": None,
        },
        "assigned_employees": [],
        "estimate_fields": {"business_unit": None, "job_type": None},
        "options": [
            {
                "approval_status": "",
                "created_at": "2026-11-01T00:00:00+00:00",
                "id": "est_option_1",
                "message_from_pro": None,
                "name": "Work",
                "notes": None,
                "option_number": 1,
                "status": "active",
                "tags": [],
                "total_amount": 100,
                "updated_at": "2026-11-01T00:00:00+00:00",
            }
        ],
        "work_status": "needs scheduling",
    }
    return item


def test_estimate_without_job_parent_is_quarantined_without_reclassification_loss():
    records, quarantined = _derive_records([_record("estimate-1")])

    assert len(quarantined) == 1
    assert quarantined[0]["source_id"] == "estimate-1"
    assert records[0]["disposition"] == "HOLD"
    assert records[0]["assertion"] == "hold"
    assert records[0]["source_disposition"] == "REPLAY"
    assert records[0]["reason"] == QUARANTINE_REASON


def test_estimate_with_job_parent_remains_executable():
    records, quarantined = _derive_records(
        [_valid_estimate_record("estimate-1", parents=({"domain": "job", "source_id": "job_1"},))]
    )

    assert quarantined == []
    assert records[0]["disposition"] == "REPLAY"
    assert "source_disposition" not in records[0]


def test_existing_hold_is_preserved():
    existing = _record("estimate-held", disposition="HOLD")
    records, quarantined = _derive_records([existing])

    assert quarantined == []
    assert records == [existing]


def test_invalid_location_quarantines_job_and_operational_children():
    location = _domain_record("service_location", "adr-1")
    job = _domain_record(
        "job", "job-1", parents=({"domain": "customer", "source_id": "customer-1"}, {"domain": "service_location", "source_id": "adr-1"})
    )
    appointment = _domain_record(
        "appointment", "appointment-1", parents=({"domain": "job", "source_id": "job-1"},)
    )

    records, quarantined = _derive_records([location, job, appointment])

    assert {item["source_id"] for item in quarantined} == {
        "adr-1",
        "job-1",
        "appointment-1",
    }
    assert {item["reason"] for item in quarantined} == {
        "service_location_payload_not_normalizable",
        "job_service_location_lineage_missing",
        "parent_job_quarantined",
    }
    assert all(item["disposition"] == "HOLD" for item in records)
