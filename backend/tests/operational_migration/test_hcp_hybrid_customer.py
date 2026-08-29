from copy import deepcopy

import pytest

from app.operational_migration.hcp_hybrid_customer import (
    AdmissionOutcome,
    AssertionKind,
    ControlAssertion,
    CustomerAssertion,
    ParentOutcome,
    build_hybrid_admission,
    build_reviewed_customer_output,
    canonical_sha256,
    close_job_parents,
)


def customer(native_id: str, *, name: str = "Source Customer") -> dict[str, object]:
    return {
        "addresses": [
            {
                "city": "Tampa",
                "country": "US",
                "id": f"adr_{native_id[4:]}",
                "latitude": None,
                "longitude": None,
                "state": "FL",
                "street": "1 Source St",
                "street_line_2": None,
                "type": "service",
                "zip": "33601",
            }
        ],
        "company": None,
        "company_id": "company",
        "company_name": "",
        "created_at": "2023-01-01T00:00:00Z",
        "email": None,
        "first_name": name.split()[0],
        "home_number": None,
        "id": native_id,
        "kind": "homeowner",
        "last_name": name.split()[-1],
        "lead_source": None,
        "mobile_number": None,
        "notes": None,
        "notifications_enabled": True,
        "tags": [],
        "updated_at": "2023-01-02T00:00:00Z",
        "work_number": None,
    }


def assertion(
    native_id: str, kind: AssertionKind, *, name: str = "Source Customer"
) -> CustomerAssertion:
    return CustomerAssertion.source4(
        kind=kind, payload=customer(native_id, name=name), container_digest="a" * 64
    )


def test_exact_layout_and_changed_layout_rejection() -> None:
    assert assertion("cus_1", AssertionKind.API_LISTED).source_identity == "cus_1"
    changed = customer("cus_1")
    changed["unknown"] = "changed"
    with pytest.raises(ValueError, match="unsupported SOURCE.4 Customer layout"):
        CustomerAssertion.source4(
            kind=AssertionKind.API_LISTED,
            payload=changed,
            container_digest="a" * 64,
        )


def test_native_union_is_order_independent_and_control_remains_separate() -> None:
    api = [
        assertion("cus_2", AssertionKind.API_LISTED),
        assertion("cus_1", AssertionKind.API_LISTED),
    ]
    detail = [assertion("cus_3", AssertionKind.REFERENCED_DETAIL)]
    rejected_control = ControlAssertion(
        "legacy-1", "b" * 64, "REJECTED", "contact_name_unresolved"
    )
    first = build_hybrid_admission(
        api_assertions=api,
        detail_assertions=detail,
        control_assertions=[rejected_control],
    )
    second = build_hybrid_admission(
        api_assertions=reversed(api),
        detail_assertions=detail,
        control_assertions=[rejected_control],
    )
    assert first.digest == second.digest
    assert first.counts == {
        "PERSISTABLE": 3,
        "EXPLICIT_EXCEPTION": 0,
        "REJECTED": 0,
        "INTENTIONALLY_NON_APPLICABLE": 0,
        "AUTHORITATIVE_UNION": 3,
        "UNLINKED_CONTROL_ASSERTIONS": 1,
    }
    assert first.candidates[2].membership == "REFERENCED_DETAIL_ONLY"
    assert first.unlinked_control_assertions[0].reason == "contact_name_unresolved"


def test_same_name_never_merges_and_conflicting_assertions_stay_visible() -> None:
    api = [
        assertion("cus_1", AssertionKind.API_LISTED),
        assertion("cus_2", AssertionKind.API_LISTED),
    ]
    detail = [
        assertion("cus_1", AssertionKind.REFERENCED_DETAIL, name="Changed Customer")
    ]
    result = build_hybrid_admission(api_assertions=api, detail_assertions=detail)
    assert len(result.candidates) == 2
    assert result.candidates[0].conflict_fields == ("first_name",)
    duplicate = deepcopy(api[0])
    object.__setattr__(duplicate, "payload_digest", "f" * 64)
    with pytest.raises(ValueError, match="contradictory native Customer identity"):
        build_hybrid_admission(api_assertions=[api[0], duplicate], detail_assertions=[])


def test_child_exception_does_not_reject_parent_and_projection_is_native() -> None:
    payload = customer("cus_1")
    payload["addresses"].append({**payload["addresses"][0], "id": "adr_bad", "zip": ""})
    admitted = build_hybrid_admission(
        api_assertions=[
            CustomerAssertion.source4(
                kind=AssertionKind.API_LISTED,
                payload=payload,
                container_digest="a" * 64,
            )
        ],
        detail_assertions=[],
    )
    assert admitted.candidates[0].outcome == AdmissionOutcome.PERSISTABLE
    assert admitted.candidates[0].location_exception_ids == ("adr_bad",)
    reviewed, boundary = build_reviewed_customer_output(admitted)
    assert reviewed.accepted_count == 1
    assert reviewed.aggregates[0].source_identity == "cus_1"
    assert len(reviewed.aggregates[0].service_locations) == 1
    assert boundary.expected.customers == 1


def test_job_parent_closure_is_exhaustive_and_deterministic() -> None:
    admission = build_hybrid_admission(
        api_assertions=[assertion("cus_1", AssertionKind.API_LISTED)],
        detail_assertions=[],
    )
    closure = close_job_parents(
        [("job_2", "cus_missing"), ("job_1", "cus_1")], admission
    )
    replay = close_job_parents(
        reversed([("job_2", "cus_missing"), ("job_1", "cus_1")]), admission
    )
    assert closure.digest == replay.digest
    assert closure.counts[ParentOutcome.RESOLVED_TO_PERSISTABLE_CUSTOMER] == 1
    assert closure.counts[ParentOutcome.MISSING_AUTHORITATIVE_CUSTOMER_EVIDENCE] == 1
    assert sum(closure.counts.values()) == 2


def test_changed_assertion_changes_hybrid_digest() -> None:
    first = build_hybrid_admission(
        api_assertions=[assertion("cus_1", AssertionKind.API_LISTED)],
        detail_assertions=[],
    )
    second = build_hybrid_admission(
        api_assertions=[
            assertion("cus_1", AssertionKind.API_LISTED, name="Other Person")
        ],
        detail_assertions=[],
    )
    assert first.digest != second.digest
    assert canonical_sha256(first) != canonical_sha256(second)
