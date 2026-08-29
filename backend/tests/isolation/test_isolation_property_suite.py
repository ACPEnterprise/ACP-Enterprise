import ast
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict, cast

from tests.isolation.properties import (
    IsolationIdentity,
    assert_company_and_branch_isolation,
    deterministic_scenarios,
)

ROOT = Path(__file__).parents[2]
COVERAGE_PATH = Path(__file__).with_name("coverage.v1.json")


class Evidence(TypedDict):
    path: str
    test: str


class DomainCoverage(TypedDict):
    domain: str
    classification: str
    layers: list[str]
    evidence: list[Evidence]


class Coverage(TypedDict):
    schema_version: str
    milestone: str
    classifications: list[str]
    domains: list[DomainCoverage]
    exclusions: list[str]
    fingerprint: str


class DeterministicBoundary:
    def __init__(self, *, branch_is_hard_boundary: bool) -> None:
        self.branch_is_hard_boundary = branch_is_hard_boundary

    def _allowed(
        self, principal: IsolationIdentity, resource: IsolationIdentity
    ) -> bool:
        return principal.company_id == resource.company_id and (
            not self.branch_is_hard_boundary
            or principal.branch_id == resource.branch_id
        )

    def read(self, principal: IsolationIdentity, resource: IsolationIdentity) -> bool:
        return self._allowed(principal, resource)

    def mutate(
        self, principal: IsolationIdentity, resource: IsolationIdentity
    ) -> bool:
        return self._allowed(principal, resource)

    def link(
        self,
        principal: IsolationIdentity,
        parent: IsolationIdentity,
        child: IsolationIdentity,
    ) -> bool:
        return self._allowed(principal, parent) and self._allowed(principal, child)

    def list_visible(
        self,
        principal: IsolationIdentity,
        resources: Iterable[IsolationIdentity],
    ) -> tuple[IsolationIdentity, ...]:
        return tuple(
            resource
            for resource in resources
            if self._allowed(principal, resource)
        )

    def event_visible(
        self, principal: IsolationIdentity, event: IsolationIdentity
    ) -> bool:
        return self._allowed(principal, event)


def _coverage() -> Coverage:
    return cast(Coverage, json.loads(COVERAGE_PATH.read_text(encoding="utf-8")))


def test_generated_company_and_hard_branch_properties_are_deterministic() -> None:
    first = deterministic_scenarios(32)
    second = deterministic_scenarios(32)
    assert first == second
    assert len({scenario.unknown_resource_id for scenario in first}) == 32
    assert_company_and_branch_isolation(
        DeterministicBoundary(branch_is_hard_boundary=True),
        branch_is_hard_boundary=True,
        count=32,
    )


def test_company_wide_authority_explicitly_spans_branches_only() -> None:
    assert_company_and_branch_isolation(
        DeterministicBoundary(branch_is_hard_boundary=False),
        branch_is_hard_boundary=False,
        count=32,
    )


def test_coverage_ledger_is_complete_and_fingerprinted() -> None:
    coverage = _coverage()
    payload: dict[str, object] = dict(coverage)
    fingerprint = payload.pop("fingerprint")
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert fingerprint == expected
    domains = {item["domain"] for item in coverage["domains"]}
    assert domains == {
        "Customers", "Contacts", "Service Locations", "Jobs",
        "Scheduling/Appointments", "Dispatch", "Workforce/Employees",
        "Inventory", "Purchasing", "Price Book", "Estimates", "Invoices/AR",
        "Payments", "Accounts Payable", "Accounting", "Business Events",
        "Beacon", "Business Economics Policy", "Platform Authorization Objects",
        "Workday Time", "Payroll Policy Authority", "Operational Projections",
    }


def test_every_coverage_claim_references_a_real_test() -> None:
    coverage = _coverage()
    for domain in coverage["domains"]:
        assert domain["layers"], domain["domain"]
        assert domain["evidence"], domain["domain"]
        for evidence in domain["evidence"]:
            path = ROOT / evidence["path"]
            assert path.is_file(), path
            functions = {
                node.name
                for node in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            assert evidence["test"] in functions, f"{domain['domain']}: {evidence}"


def test_high_risk_domains_have_relationship_and_runtime_layer_evidence() -> None:
    coverage = _coverage()
    by_domain = {item["domain"]: item for item in coverage["domains"]}
    for domain in ("Jobs", "Scheduling/Appointments", "Inventory", "Purchasing", "Estimates", "Invoices/AR", "Accounting", "Workday Time"):
        assert "relationship" in by_domain[domain]["layers"]
    for domain in ("Customers", "Jobs", "Scheduling/Appointments", "Inventory", "Beacon"):
        assert set(by_domain[domain]["layers"]) & {"repository", "service", "api"}
