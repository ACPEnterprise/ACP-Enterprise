from uuid import UUID

from app.migration_factory.exception_readback import (
    HeldSourceException,
    exception_readback,
)

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
OTHER_COMPANY = UUID("10000000-0000-0000-0000-000000000002")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")


def held(company: UUID, key: str, kind: str, digest: str) -> HeldSourceException:
    return HeldSourceException(
        company,
        BRANCH,
        key,
        kind,
        f"Evidence explanation for {key}",
        digest,
        ("customer:c1",),
    )


def test_queue_preserves_ambiguous_missing_parent_and_version_holds() -> None:
    rows = (
        held(COMPANY, "customer:c2", "AMBIGUOUS_IDENTITY", "a" * 64),
        held(COMPANY, "job:j1", "MISSING_PARENT", "b" * 64),
        held(COMPANY, "invoice:i1", "SOURCE_VERSION_CONFLICT", "c" * 64),
    )
    queue = exception_readback(
        rows, company_id=COMPANY, accessible_branch_ids=frozenset({BRANCH})
    )
    assert {item.exception_type for item in queue.items} == {
        "AMBIGUOUS_IDENTITY",
        "MISSING_PARENT",
        "SOURCE_VERSION_CONFLICT",
    }
    assert all(item.explanation for item in queue.items)
    assert queue == exception_readback(
        tuple(reversed(rows)),
        company_id=COMPANY,
        accessible_branch_ids=frozenset({BRANCH}),
    )


def test_queue_has_no_merge_action_and_is_tenant_scoped() -> None:
    queue = exception_readback(
        (
            held(COMPANY, "customer:c1", "AMBIGUOUS_IDENTITY", "a" * 64),
            held(OTHER_COMPANY, "customer:c2", "AMBIGUOUS_IDENTITY", "b" * 64),
        ),
        company_id=COMPANY,
        accessible_branch_ids=frozenset({BRANCH}),
    )
    assert [item.source_key for item in queue.items] == ["customer:c1"]
    assert queue.automatic_merge_enabled is False
    assert all("MERGE" not in item.available_actions for item in queue.items)
