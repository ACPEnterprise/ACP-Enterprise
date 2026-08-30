from unittest.mock import MagicMock
from uuid import uuid4

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.reliability.correlation import request_correlation_id


def test_request_correlation_propagates_to_event_and_audit() -> None:
    session = MagicMock()
    correlation_id = uuid4()
    token = request_correlation_id.set(correlation_id)
    try:
        event = BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.SYSTEM_STARTED,
                entity_type="correlation_qualification",
            ),
        )
        audit = AuditService.stage(
            session,
            AuditEntry(
                action="correlation.qualified",
                resource_type="correlation_qualification",
            ),
        )
    finally:
        request_correlation_id.reset(token)

    assert event.correlation_id == correlation_id
    assert audit.correlation_id == correlation_id


def test_explicit_and_background_correlation_semantics_remain_distinct() -> None:
    session = MagicMock()
    explicit = uuid4()
    event = BusinessEventService.stage(
        session,
        BusinessEventCreate(
            event_type=EventType.SYSTEM_STARTED,
            entity_type="correlation_qualification",
            correlation_id=explicit,
        ),
    )
    audit = AuditService.stage(
        session,
        AuditEntry(
            action="correlation.qualified",
            resource_type="correlation_qualification",
        ),
    )

    assert event.correlation_id == explicit
    assert audit.correlation_id is not None
    assert audit.correlation_id != explicit
