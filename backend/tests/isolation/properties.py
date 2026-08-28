from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid5

NAMESPACE = UUID("35bfb596-5e55-41e5-ae9d-7b8d5ae8db42")


@dataclass(frozen=True)
class IsolationIdentity:
    company_id: UUID
    branch_id: UUID
    business_id: str


@dataclass(frozen=True)
class IsolationScenario:
    principal: IsolationIdentity
    same_scope: IsolationIdentity
    wrong_branch: IsolationIdentity
    wrong_company: IsolationIdentity
    unknown_resource_id: UUID


class IsolationAdapter(Protocol):
    def read(self, principal: IsolationIdentity, resource: IsolationIdentity) -> bool: ...

    def mutate(self, principal: IsolationIdentity, resource: IsolationIdentity) -> bool: ...

    def link(
        self,
        principal: IsolationIdentity,
        parent: IsolationIdentity,
        child: IsolationIdentity,
    ) -> bool: ...

    def list_visible(
        self,
        principal: IsolationIdentity,
        resources: Iterable[IsolationIdentity],
    ) -> tuple[IsolationIdentity, ...]: ...

    def event_visible(
        self, principal: IsolationIdentity, event: IsolationIdentity
    ) -> bool: ...


def deterministic_scenarios(count: int = 16) -> tuple[IsolationScenario, ...]:
    """Construct reproducible adversarial identities without random fuzzing."""
    if count < 1:
        raise ValueError("at least one isolation scenario is required")
    scenarios: list[IsolationScenario] = []
    for index in range(count):
        company_a = uuid5(NAMESPACE, f"company-a:{index}")
        company_b = uuid5(NAMESPACE, f"company-b:{index}")
        branch_a1 = uuid5(NAMESPACE, f"company-a:{index}:branch-1")
        branch_a2 = uuid5(NAMESPACE, f"company-a:{index}:branch-2")
        branch_b1 = uuid5(NAMESPACE, f"company-b:{index}:branch-1")
        shared_business_id = f"SHARED-{index:04d}"
        scenarios.append(
            IsolationScenario(
                principal=IsolationIdentity(company_a, branch_a1, shared_business_id),
                same_scope=IsolationIdentity(company_a, branch_a1, shared_business_id),
                wrong_branch=IsolationIdentity(company_a, branch_a2, shared_business_id),
                wrong_company=IsolationIdentity(company_b, branch_b1, shared_business_id),
                unknown_resource_id=uuid5(NAMESPACE, f"unknown:{index}"),
            )
        )
    return tuple(scenarios)


def assert_company_and_branch_isolation(
    adapter: IsolationAdapter,
    *,
    branch_is_hard_boundary: bool,
    count: int = 16,
) -> None:
    for scenario in deterministic_scenarios(count):
        assert adapter.read(scenario.principal, scenario.same_scope)
        assert adapter.mutate(scenario.principal, scenario.same_scope)
        assert not adapter.read(scenario.principal, scenario.wrong_company)
        assert not adapter.mutate(scenario.principal, scenario.wrong_company)
        assert not adapter.link(
            scenario.principal, scenario.same_scope, scenario.wrong_company
        )
        assert not adapter.event_visible(
            scenario.principal, scenario.wrong_company
        )
        assert adapter.list_visible(
            scenario.principal,
            (scenario.same_scope, scenario.wrong_branch, scenario.wrong_company),
        ) == (
            (scenario.same_scope,)
            if branch_is_hard_boundary
            else (scenario.same_scope, scenario.wrong_branch)
        )
        if branch_is_hard_boundary:
            assert not adapter.read(scenario.principal, scenario.wrong_branch)
            assert not adapter.mutate(scenario.principal, scenario.wrong_branch)
        else:
            assert adapter.read(scenario.principal, scenario.wrong_branch)
            assert adapter.mutate(scenario.principal, scenario.wrong_branch)
