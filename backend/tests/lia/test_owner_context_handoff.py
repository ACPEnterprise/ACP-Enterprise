from uuid import uuid4

from app.lia.contracts import LiaContext, LiaContextMetric, LiaContextRecord, LiaRequest


def test_owner_intelligence_context_carries_triggering_records_and_metrics() -> None:
    job_id = uuid4()
    invoice_id = uuid4()
    request = LiaRequest(
        question="What should I do about this?",
        context=LiaContext(
            domain="beacon",
            entity_id=uuid4(),
            records=(
                LiaContextRecord(entity_type="job", entity_id=job_id),
                LiaContextRecord(entity_type="invoice", entity_id=invoice_id),
            ),
            metrics=(
                LiaContextMetric(name="overdue_amount", value="8420", unit="USD"),
            ),
        ),
    )

    assert request.context is not None
    assert [record.entity_id for record in request.context.records] == [
        job_id,
        invoice_id,
    ]
    assert request.context.metrics[0].name == "overdue_amount"
