import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.economics.domain import (
    Allocation,
    BusinessFact,
    EvidenceKind,
    EvidenceReference,
)


@dataclass(frozen=True, slots=True)
class AllocationTarget:
    subject_type: str
    subject_id: UUID
    weight: int


AllocationFunction = Callable[
    [BusinessFact, tuple[AllocationTarget, ...]], tuple[Allocation, ...]
]


class AllocationRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, tuple[str, AllocationFunction]] = {}

    def register(self, name: str, version: str, function: AllocationFunction) -> None:
        if not name.strip() or not version.strip():
            raise ValueError("allocation strategy name and version are required")
        if name in self._strategies:
            raise ValueError(f"allocation strategy already registered: {name}")
        self._strategies[name] = (version, function)

    def allocate(
        self, name: str, fact: BusinessFact, targets: Iterable[AllocationTarget]
    ) -> tuple[Allocation, ...]:
        try:
            version, function = self._strategies[name]
        except KeyError as error:
            raise ValueError(f"unknown allocation strategy: {name}") from error
        target_tuple = tuple(targets)
        allocations = function(fact, target_tuple)
        return tuple(
            Allocation(
                id=item.id,
                source_fact_id=item.source_fact_id,
                subject_type=item.subject_type,
                subject_id=item.subject_id,
                strategy=name,
                numerator=item.numerator,
                denominator=item.denominator,
                allocated_amount_minor=item.allocated_amount_minor,
                strategy_version=version,
                input_digest=item.input_digest,
                evidence=item.evidence,
            )
            for item in allocations
        )


def proportional_allocation(
    fact: BusinessFact, targets: tuple[AllocationTarget, ...]
) -> tuple[Allocation, ...]:
    if fact.amount_minor is None:
        raise ValueError("unknown facts cannot be allocated")
    if not targets or any(target.weight < 0 for target in targets):
        raise ValueError("allocation targets require non-negative weights")
    denominator = sum(target.weight for target in targets)
    if denominator <= 0:
        raise ValueError("allocation target weights must total more than zero")

    amounts = [fact.amount_minor * target.weight // denominator for target in targets]
    remainder = fact.amount_minor - sum(amounts)
    for index in range(abs(remainder)):
        amounts[index % len(amounts)] += 1 if remainder > 0 else -1

    ordered_input = ",".join(
        f"{target.subject_type}:{target.subject_id}:{target.weight}"
        for target in targets
    )
    input_digest = hashlib.sha256(
        (
            f"{fact.id}:{fact.version}:{fact.amount_minor}:"
            f"{fact.currency}:{ordered_input}"
        ).encode()
    ).hexdigest()
    return tuple(
        Allocation(
            id=uuid4(),
            source_fact_id=fact.id,
            subject_type=target.subject_type,
            subject_id=target.subject_id,
            strategy="pending_registry_name",
            numerator=target.weight,
            denominator=denominator,
            allocated_amount_minor=amount,
            strategy_version="pending_registry_version",
            input_digest=input_digest,
            evidence=(
                EvidenceReference(
                    kind=EvidenceKind.ALLOCATION,
                    reference_id=str(fact.id),
                    source_system="business_economics",
                    source_version=str(fact.version),
                    source_record_type="business_fact",
                    content_digest=input_digest,
                    observed_at=fact.occurred_at,
                    explanation=(
                        f"Allocated {target.weight}/{denominator} of source fact {fact.id}."
                    ),
                ),
            ),
        )
        for target, amount in zip(targets, amounts, strict=True)
    )


allocation_registry = AllocationRegistry()
for _strategy in (
    "labor_hours",
    "revenue",
    "truck_days",
    "job_duration",
    "branch",
    "company",
    "labor",
    "truck",
    "equipment",
    "overhead",
):
    allocation_registry.register(_strategy, "1", proportional_allocation)
