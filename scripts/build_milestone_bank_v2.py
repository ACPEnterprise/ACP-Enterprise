"""Build and validate the BANK.2 planning artifact without activating work."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "backend/app/engineering_control/scheduler/milestone-bank.v2.json"
STARTING_SHA = "1f012258cba67300c3481953aa18a62e12e5b634"
READINESS = {
    "READY",
    "BLOCKED_DEPENDENCY",
    "BLOCKED_OWNER_DECISION",
    "BLOCKED_FINANCE_DECISION",
    "BLOCKED_EXTERNAL",
    "DEFERRED",
}
PRIORITIES = {"P0", "P1", "P2", "P3"}


@dataclass(frozen=True)
class Family:
    code: str
    domain: str
    collision: str
    repository_areas: tuple[str, ...]
    excluded: tuple[str, ...]
    topics: tuple[str, ...]
    first_state: str
    first_priority: str
    first_gate: str
    first_owner: bool = False
    first_finance: bool = False
    first_external: str = "none"
    entry_dependencies: tuple[str, ...] = ()


FAMILIES = (
    Family(
        "CRM",
        "Customers / CRM",
        "customer_identity_timeline",
        ("backend/app/customers/**", "frontend/src/components/customers/**"),
        ("Migration adapters", "marketing automation", "financial posting"),
        (
            "Customer data-quality exception workbench",
            "Service-location merge and survivorship controls",
            "Household and commercial account relationship model",
            "Contact preference effective-history workflow",
            "Customer duplicate review and reversible resolution",
            "Customer timeline evidence completeness",
            "Customer account ownership transfer workflow",
            "Service-location access and hazard evidence",
            "Customer archival and restoration controls",
            "CRM operational search relevance hardening",
            "Customer data-retention disposition workflow",
            "CRM launch reconciliation acceptance",
        ),
        "BLOCKED_OWNER_DECISION",
        "P1",
        "Laptop operations selection must release CRM paths and approve survivorship policy.",
        first_owner=True,
    ),
    Family(
        "JOB",
        "Jobs / Operations",
        "job_lifecycle",
        ("backend/app/jobs/**", "frontend/src/components/jobs/**"),
        ("Technician-owned field evidence", "accounting journals", "migration"),
        (
            "Job exception and hold lifecycle",
            "Job dependency and prerequisite evidence",
            "Multi-visit job continuity",
            "Job cancellation financial-handoff guard",
            "Job reschedule reason and audit workflow",
            "Job completion requirement policy engine",
            "Job warranty and callback linkage",
            "Job related-work lineage",
            "Job document and attachment index",
            "Job operational reconciliation queue",
            "Job lifecycle performance hardening",
            "Operations launch acceptance journey",
        ),
        "BLOCKED_OWNER_DECISION",
        "P0",
        "Laptop operations lane currently owns operational selection.",
        first_owner=True,
    ),
    Family(
        "SCH",
        "Scheduling",
        "scheduling_appointments",
        ("backend/app/scheduling/**", "frontend/src/routes/SchedulingRoute.tsx"),
        ("Dispatch assignment", "payroll policy", "autonomous scheduling"),
        (
            "Appointment constraint and conflict model",
            "Recurring service appointment generation",
            "Appointment move and cancellation evidence",
            "Customer availability request workflow",
            "Technician availability consumption boundary",
            "Schedule exception and overbooking review",
            "Travel-window evidence integration",
            "Schedule timezone and daylight-saving hardening",
            "Schedule continuity and recovery workflow",
            "Scheduling launch acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P0",
        "Laptop operations selection must release Scheduling paths.",
        first_owner=True,
    ),
    Family(
        "DSP",
        "Dispatch",
        "dispatch_assignments",
        ("backend/app/dispatch/**", "frontend/src/routes/DispatchRoute.tsx"),
        ("Worker factory capacity", "autonomous dispatch", "technician evidence"),
        (
            "Dispatch exception resolution queue",
            "Assignment conflict and stale-write recovery",
            "Crew and helper assignment boundary",
            "Dispatch route sequence evidence",
            "Arrival-risk and lateness presentation",
            "Emergency reassignment workflow",
            "Unassigned-work aging controls",
            "Dispatch communication handoff",
            "Dispatch continuity and degraded-mode UX",
            "Dispatch launch acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P0",
        "Operations selection and Field ownership must release shared assignment seams.",
        first_owner=True,
    ),
    Family(
        "FIELD",
        "Technician / Field Service",
        "field_service",
        ("backend/app/field_service/**", "frontend/src/features/technician/**"),
        ("Worker enrollment", "Inventory-owned stock truth", "Accounting posting"),
        (
            "Field note and evidence capture hardening",
            "Customer work-approval workflow",
            "Required form and checklist execution",
            "Photo and attachment custody boundary",
            "Offline command queue contract",
            "Offline conflict and retry UX",
            "Technician job-status transition journey",
            "Technician material request handoff",
            "Technician time evidence capture",
            "Field safety and hazard acknowledgement",
            "Customer signature evidence",
            "Technician closeout reconciliation",
            "Field accessibility and device hardening",
            "Field launch physical-device acceptance",
        ),
        "BLOCKED_OWNER_DECISION",
        "P0",
        "Laptop1-A owns Field Service and must release or complete the current lane.",
        first_owner=True,
    ),
    Family(
        "COMMS",
        "Communications",
        "communications_outbox",
        ("backend/app/communications/**", "backend/app/platform/notifications/**"),
        ("Marketing campaigns", "provider credentials", "autonomous messaging"),
        (
            "Appointment notification journey",
            "Dispatch and arrival notification journey",
            "Estimate delivery and reminder journey",
            "Invoice and payment receipt notification journey",
            "Consent and quiet-hours enforcement",
            "Template version and approval workflow",
            "Delivery failure reconciliation queue",
            "Inbound reply classification boundary",
            "Communication history operator workspace",
            "Communications launch acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P1",
        "Owner-approved customer templates and release of operations/commercial seams are required.",
        first_owner=True,
    ),
    Family(
        "COMMERCIAL",
        "Price Book / Estimates",
        "commercial_pricing",
        ("backend/app/price_book/**", "backend/app/estimates/**", "frontend/src/routes/EstimatesRoute.tsx"),
        ("Financing offers", "accounting policy", "Business Economics recommendations"),
        (
            "Price Book effective-dating and supersession",
            "Price Book bulk operator workflow",
            "Price Book branch availability controls",
            "Price Book evidence and audit exports",
            "Estimate alternate-option comparison",
            "Estimate reusable assemblies and bundles",
            "Estimate allowance and provisional-item controls",
            "Estimate expiration and renewal workflow",
            "Estimate revision comparison UX",
            "Estimate approval exception workflow",
            "Estimate customer-presentation accessibility",
            "Estimate follow-up evidence handoff",
            "Estimate-to-job contradiction reconciliation",
            "Commercial calculation property testing",
            "Commercial mobile workflow hardening",
            "Commercial launch acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P1",
        "Laptop1-B commercial selection owns or may reserve these paths.",
        first_owner=True,
    ),
    Family(
        "REV",
        "Invoicing / Payments",
        "revenue_workflows",
        ("backend/app/invoicing/**", "backend/app/payments/**", "frontend/src/routes/InvoicesRoute.tsx"),
        ("Accounting posting rules", "processor credentials", "real financial import"),
        (
            "Invoice generation from accepted field completion",
            "Invoice delivery and receipt-state workflow",
            "Invoice customer presentation hardening",
            "Invoice correction operator workflow",
            "Credit memo approval and application UX",
            "Invoice dispute evidence workflow",
            "AR open-item reconciliation workspace",
            "Payment request customer journey",
            "Externally processed payment evidence intake",
            "Payment application operator workflow",
            "Unapplied receipt resolution queue",
            "Refund approval and provider handoff",
            "Refund failure and retry reconciliation",
            "Payment dispute and chargeback workflow",
            "Deposit and settlement operator workflow",
            "Revenue-domain concurrency hardening",
            "Revenue mobile and accessibility acceptance",
            "Invoice-to-payment launch acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P0",
        "Commercial lane ownership and Accounting receipt seams must be reconciled.",
        first_owner=True,
    ),
    Family(
        "INV",
        "Inventory",
        "inventory_stock_truth",
        ("backend/app/inventory/**", "frontend/src/routes/InventoryRoute.tsx"),
        ("Purchasing-owned purchase orders", "financial valuation", "fabricated opening balances"),
        (
            "Inventory opening-completeness evidence model",
            "Truck stock custody workflow",
            "Job material requirement reservation",
            "Job material issue and return workflow",
            "Material waste and correction evidence",
            "Stock transfer exception resolution",
            "Cycle-count variance approval workflow",
            "Inventory adjustment separation of duties",
            "Inventory attachment and evidence custody",
            "Inventory unit-of-measure conversion boundary",
            "Inventory reconciliation dashboard",
            "Inventory performance and lock-contention hardening",
            "Inventory mobile scanning accessibility boundary",
            "Inventory launch acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P1",
        "Opening-balance completeness granularity and active Inventory ownership must be resolved.",
        first_owner=True,
    ),
    Family(
        "PUR",
        "Purchasing",
        "purchasing_vendor_po",
        ("backend/app/purchasing/**", "frontend/src/components/purchasing/**"),
        ("Inventory table writes", "AP Bills", "accounting valuation"),
        (
            "PUR.1 purchasing foundation",
            "PUR.2 partial receiving and discrepancy workflow",
            "Purchase return and vendor authorization workflow",
            "Purchase-order change-order controls",
            "Purchase-order close and cancellation evidence",
            "Vendor performance evidence boundary",
            "Replenishment recommendation workbench",
            "Replenishment approval and PO linkage",
            "Branch purchasing policy configuration",
            "Purchasing attachment and document custody",
            "Purchasing operator mobile workflow",
            "Purchasing reconciliation dashboard",
            "Purchasing performance and concurrency hardening",
            "Purchasing launch acceptance suite",
        ),
        "READY",
        "P0",
        "INV.2A is authoritative at 45fda1c and PUR.1 packet is ready_for_owner_start.",
    ),
    Family(
        "ASSET",
        "Equipment / Fleet / Assets",
        "operational_assets",
        ("backend/app/assets/**", "backend/app/fleet/**"),
        ("Fixed-asset accounting", "telematics vendor selection", "payroll"),
        (
            "Operational equipment identity contract",
            "Customer equipment and install-base registry",
            "Equipment warranty evidence workflow",
            "Equipment service-history projection",
            "Fleet vehicle identity and assignment",
            "Fleet inspection evidence workflow",
            "Fleet maintenance scheduling handoff",
            "Tool custody and accountability workflow",
            "Asset document and attachment custody",
            "Equipment and fleet launch acceptance",
        ),
        "BLOCKED_OWNER_DECISION",
        "P1",
        "Owner must approve equipment, fleet, and tool identity boundaries.",
        first_owner=True,
    ),
    Family(
        "WF",
        "Workforce",
        "workforce_employee_labor",
        ("backend/app/workforce/**", "backend/app/platform/employees/**"),
        ("Payroll calculation", "worker factory identity", "autonomous performance decisions"),
        (
            "Employee operational profile lifecycle",
            "Technician capability effective history",
            "Certification and expiration evidence",
            "Crew membership and leadership boundaries",
            "Work availability exception workflow",
            "Time and labor evidence contract",
            "Time-entry correction and approval workflow",
            "Job labor allocation evidence",
            "Overtime evidence and policy input boundary",
            "Payroll summary handoff contract",
            "Workforce productivity evidence projection",
            "Workforce permission and SOD hardening",
            "Workforce data-retention controls",
            "Workforce launch acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P1",
        "Labor/time authority and payroll handoff ownership require owner approval.",
        first_owner=True,
    ),
    Family(
        "ACC",
        "Accounting / Finance",
        "accounting_ledger_reporting",
        ("backend/app/accounting/**", "backend/app/financial_reporting/**"),
        ("QBO acquisition", "real financial import", "unstated Finance mappings"),
        (
            "Accounting authority and lineage reconciliation",
            "Posting receipt cross-domain acceptance",
            "AR control-account reconciliation",
            "AP control-account reconciliation",
            "Cash and clearing evidence reconciliation",
            "Bank statement evidence contract",
            "Bank reconciliation operator workflow",
            "Accounting period close checklist",
            "Period close concurrency and lock hardening",
            "Controlled period reopen workflow",
            "Sales-tax support architecture",
            "Payroll posting interface contract",
            "Fixed-asset posting interface contract",
            "Trial-balance and statement acceptance",
            "AR/AP aging policy activation",
            "Accounting audit export and drillback",
            "Accounting disaster-recovery reconciliation",
            "Day-1 Accounting activation acceptance",
        ),
        "BLOCKED_FINANCE_DECISION",
        "P0",
        "OM2-A owns current Accounting reconciliation and must release the domain.",
        first_owner=True,
        first_finance=True,
    ),
    Family(
        "ECO",
        "Business Economics",
        "business_economics",
        ("backend/app/business_economics/**", "docs/architecture/accounting/eco-*.md"),
        ("Accounting mutation", "unsupported causal claims", "autonomous pricing"),
        (
            "Economics source authority reconciliation",
            "Contribution measurement acceptance",
            "Service-line economics model",
            "Job contribution economics",
            "Labor utilization economics",
            "Material utilization economics",
            "Overhead allocation evidence contract",
            "Callback and warranty economics",
            "Customer and segment economics",
            "Estimate conversion economics",
            "Confidence and evidence scoring",
            "Economics variance reconciliation",
            "Profitability intelligence presentation",
            "Economics launch acceptance",
        ),
        "BLOCKED_FINANCE_DECISION",
        "P2",
        "ECO actively owns Business Economics and Finance policy remains unresolved.",
        first_owner=True,
        first_finance=True,
    ),
    Family(
        "BEA",
        "Beacon",
        "beacon_signals",
        ("backend/app/beacon/**", "frontend/src/components/command-center/BeaconPanel.tsx"),
        ("Autonomous operational mutation", "unsupported economics", "worker scheduling"),
        (
            "Operational exception signal catalog",
            "Evidence-bound signal evaluation",
            "Signal confidence and freshness semantics",
            "Signal prioritization and tie-breaking",
            "Signal acknowledgement and ownership",
            "Signal escalation lifecycle",
            "Financial exception signal family",
            "Economic signal consumption boundary",
            "Beacon explanation and drillback UX",
            "Beacon launch acceptance suite",
        ),
        "READY",
        "P2",
        "Beacon foundation is authoritative and operational signals can remain independent of ECO outputs.",
    ),
    Family(
        "LIA",
        "Luminary / LIA",
        "lia_guidance",
        ("backend/app/engineering_execution/**", "docs/engineering/lia-*.md"),
        ("Autonomous mutation", "worker enrollment", "financial recommendations without evidence"),
        (
            "Enterprise explanation envelope",
            "Evidence citation and provenance contract",
            "Confidence and uncertainty presentation",
            "Owner decision framing boundary",
            "Alternative and tradeoff explanation model",
            "Controlled action proposal contract",
            "Unsafe recommendation refusal boundary",
            "Stale evidence and contradiction handling",
            "Owner mobile guidance presentation",
            "LIA trust and safety acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P2",
        "Physical-worker factory currently owns LIA/Engineering execution seams.",
        first_owner=True,
    ),
    Family(
        "MIG",
        "Migration / Cutover",
        "migration_cutover",
        ("backend/app/customer_migration/**", "backend/app/operational_migration/**"),
        ("Production import", "QBO OAuth acquisition", "unapproved source mutation"),
        (
            "HCP source inventory acceptance",
            "HCP transformation conformance",
            "Customer and service-location reconciliation",
            "Job and appointment reconciliation",
            "Estimate and invoice comparison",
            "Attachment inventory and custody",
            "Migration reject and exception workflow",
            "Representative dry-run readiness",
            "Representative non-production rehearsal",
            "Repeatable rehearsal and delta strategy",
            "QBO acquisition evidence intake",
            "Cross-system financial comparison",
            "Cutover and rollback runbook acceptance",
            "Post-cutover validation and hypercare",
        ),
        "BLOCKED_EXTERNAL",
        "P0",
        "Migration lane is active and immutable HCP/QBO evidence gates are external.",
        first_owner=True,
        first_external="HCP/QBO source evidence and separate rehearsal authority",
    ),
    Family(
        "PLAT",
        "Platform / Enterprise",
        "platform_shared",
        ("backend/app/platform/**", "backend/app/events/**", "backend/app/core/**"),
        ("Worker enrollment", "Production mutation", "domain-specific policy"),
        (
            "Phase-1 operational integration checkpoint",
            "Authorization matrix continuous verification",
            "Company and Branch isolation property suite",
            "Immutable audit completeness verification",
            "Business Event delivery and replay hardening",
            "Notification outbox resilience hardening",
            "Sensitive-data logging controls",
            "API idempotency consistency standard",
            "Cross-domain data-integrity verification",
            "Application performance baseline",
            "Enterprise observability contract",
            "Platform launch security acceptance",
        ),
        "BLOCKED_DEPENDENCY",
        "P0",
        "Phase-1 integration waits for PUR.1 authoritative completion.",
        entry_dependencies=("BANK.PUR.001",),
    ),
    Family(
        "DF",
        "Development Factory",
        "engineering_control_factory",
        ("backend/app/engineering_control/**", "backend/app/worker_runtime/**"),
        ("Product implementation", "Production deployment", "credential generation"),
        (
            "Milestone-bank ingestion contract",
            "Dependency readiness evaluator",
            "Path and collision-domain evaluator",
            "Automatic safe-work selection",
            "Capacity-aware assignment planner",
            "Owner phone approval projection",
            "Execution evidence completeness gate",
            "Authoritative reconciliation and recovery",
            "Stale ownership lease recovery",
            "Factory scheduling acceptance suite",
        ),
        "BLOCKED_OWNER_DECISION",
        "P1",
        "OM1 owns active physical-worker enrollment and factory qualification.",
        first_owner=True,
    ),
    Family(
        "READY",
        "UX / Mobile / Production Readiness",
        "release_readiness",
        ("frontend/src/**", "docs/deployment/**", "docs/runbooks/**"),
        ("Production deployment", "real-data import", "physical worker enrollment"),
        (
            "Office workflow responsive acceptance",
            "Owner mobile operational acceptance",
            "Technician degraded-network acceptance",
            "Cross-domain accessibility conformance",
            "Failure and recovery UX standard",
            "Backup and restore rehearsal",
            "Disaster-recovery runbook validation",
            "Production cutover readiness review",
        ),
        "BLOCKED_OWNER_DECISION",
        "P0",
        "Active Laptop and Field lanes plus separate Preview/Production authority gate these boundaries.",
        first_owner=True,
        first_external="separate Preview/Production authorization for environment validation",
    ),
)

CROSS_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "BANK.PUR.002": ("BANK.PLAT.001",),
    "BANK.INV.003": ("BANK.PUR.002", "BANK.FIELD.007"),
    "BANK.FIELD.008": ("BANK.PUR.002",),
    "BANK.REV.001": ("BANK.FIELD.007",),
    "BANK.COMMS.001": ("BANK.REV.002",),
    "BANK.ACC.003": ("BANK.REV.007",),
    "BANK.ACC.004": ("BANK.PUR.002",),
    "BANK.ECO.003": ("BANK.ACC.014",),
    "BANK.BEA.007": ("BANK.ACC.005",),
    "BANK.MIG.009": ("BANK.PLAT.001", "BANK.REV.018", "BANK.ACC.018"),
    "BANK.READY.006": ("BANK.MIG.010",),
}


def canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def priority_for(index: int, family: Family) -> str:
    if family.first_priority == "P0":
        return "P0" if index <= len(family.topics) // 2 else "P1"
    if family.first_priority == "P1":
        return "P1" if index <= (len(family.topics) * 2) // 3 else "P2"
    return "P2" if index <= (len(family.topics) * 2) // 3 else "P3"


def build() -> dict[str, Any]:
    milestones: list[dict[str, Any]] = []
    for family in FAMILIES:
        previous: str | None = None
        for index, name in enumerate(family.topics, 1):
            milestone_id = f"BANK.{family.code}.{index:03d}"
            if index == 1:
                dependencies = list(family.entry_dependencies)
            else:
                assert previous is not None
                dependencies = [previous]
            state = family.first_state if index == 1 else "BLOCKED_DEPENDENCY"
            owner = family.first_owner if index == 1 else False
            finance = family.first_finance if index == 1 else False
            external = family.first_external if index == 1 else "none"
            readiness = (
                family.first_gate
                if index == 1
                else f"{previous} is authoritative and its completion evidence is accepted."
            )
            record = {
                "milestone_id": milestone_id,
                "name": name,
                "domain": family.domain,
                "objective": (
                    f"Deliver the bounded {name.lower()} capability using authoritative "
                    "Company/Branch evidence, explicit provenance, and fail-closed behavior."
                ),
                "priority": priority_for(index, family),
                "readiness_state": state,
                "ownership_state": "ACTIVE_OWNED" if owner else "UNOWNED",
                "dependencies": dependencies,
                "repository_evidence": [
                    f"origin/customer-management-v1@{STARTING_SHA}",
                    *(["INV.2A@45fda1c"] if milestone_id == "BANK.PUR.001" else []),
                ],
                "dependency_type": "HARD_ALL",
                "readiness_conditions": [readiness, "Current origin is fetched and path ownership is rechecked."],
                "implementation_boundary": (
                    f"Own only {name.lower()} contracts, persistence or projections, APIs, "
                    f"operator UX, audit, and focused validation inside {family.collision}."
                ),
                "excluded_scope": list(family.excluded),
                "likely_repository_areas": list(family.repository_areas),
                "collision_domain": family.collision,
                "owner_decision_required": owner,
                "finance_decision_required": finance,
                "external_gate": external,
                "schema_migration_risk": "HIGH" if index in {1, 2, 5} and family.code in {"PUR", "ASSET", "WF", "MIG"} else "MEDIUM" if index % 4 == 0 else "LOW",
                "production_risk": "PROHIBITED_UNTIL_SEPARATE_AUTHORIZATION",
                "validation_contract": [
                    "Focused domain unit and integration tests",
                    "Company/Branch authorization and negative tests",
                    "Idempotency, concurrency, audit, and Business Event evidence where applicable",
                    "Affected static analysis and frontend production build where applicable",
                    "Migration upgrade/downgrade/drift/one-head validation when schema changes",
                    "git diff --check and focused secret/private-material scan",
                ],
                "completion_evidence": [
                    "One bounded commit set is authoritative on origin/customer-management-v1",
                    "Required validation is recorded with no fabricated or real imported data",
                    "Worktree is clean and local/origin synchronization is proven",
                    "Preview and Production remain separately gated",
                ],
                "successor_ids": [],
            }
            milestones.append(record)
            previous = milestone_id
    by_id = {item["milestone_id"]: item for item in milestones}
    for milestone_id, cross_dependencies in CROSS_DEPENDENCIES.items():
        item = by_id[milestone_id]
        item["dependencies"] = list(
            dict.fromkeys([*item["dependencies"], *cross_dependencies])
        )
        if item["readiness_state"] == "READY":
            item["readiness_state"] = "BLOCKED_DEPENDENCY"
    for item in milestones:
        for dependency in item["dependencies"]:
            by_id[dependency]["successor_ids"].append(item["milestone_id"])
    payload: dict[str, Any] = {
        "schema_version": "2.0",
        "bank_id": "BANK.2",
        "purpose": "Planning-only executable ACP Enterprise milestone inventory.",
        "authoritative_start_sha": STARTING_SHA,
        "generated_on": "2026-08-27",
        "activation_semantics": "NONE_PLANNING_ONLY",
        "canonical_runtime_manifest": "backend/app/engineering_control/scheduler/scheduler-manifest.v1.json",
        "integration_rule": "BANK.DF.001 must define reviewed ingestion before any runtime scheduler consumption.",
        "active_ownership": {
            "OM1": "physical worker enrollment, qualification, Engineering Control, worker runtime and capacity",
            "ECO": "Business Economics contracts and adapters",
            "MIG": "HCP/QBO acquisition, transformation, reconciliation and migration",
            "OM2-A": "Accounting reconciliation and successor ownership",
            "LAPTOP1-A": "operations and Field Service selection",
            "LAPTOP1-B": "commercial selection",
        },
        "milestones": milestones,
    }
    payload["fingerprint"] = canonical_digest(payload)
    return payload


def validate(bank: dict[str, Any]) -> None:
    milestones = bank["milestones"]
    if not 200 <= len(milestones) <= 300:
        raise ValueError("Milestone count must be between 200 and 300.")
    required = {
        "milestone_id", "name", "domain", "objective", "priority", "dependencies",
        "dependency_type", "readiness_conditions", "implementation_boundary",
        "excluded_scope", "likely_repository_areas", "collision_domain",
        "owner_decision_required", "finance_decision_required", "external_gate",
        "schema_migration_risk", "production_risk", "validation_contract",
        "completion_evidence", "successor_ids", "readiness_state",
    }
    ids = [item["milestone_id"] for item in milestones]
    if len(ids) != len(set(ids)):
        raise ValueError("Milestone IDs are not unique.")
    names = [item["name"].casefold() for item in milestones]
    if len(names) != len(set(names)):
        raise ValueError("Milestone names are not unique.")
    known = set(ids)
    for item in milestones:
        missing = required - set(item)
        if missing:
            raise ValueError(f"{item['milestone_id']} lacks {sorted(missing)}")
        if item["priority"] not in PRIORITIES:
            raise ValueError(f"Invalid priority for {item['milestone_id']}")
        if item["readiness_state"] not in READINESS:
            raise ValueError(f"Invalid readiness for {item['milestone_id']}")
        if not set(item["dependencies"]) <= known:
            raise ValueError(f"Missing dependency for {item['milestone_id']}")
        if item["readiness_state"] == "READY" and item["dependencies"]:
            raise ValueError(f"READY item has unresolved bank dependency: {item['milestone_id']}")
        if item["readiness_state"] == "READY" and (
            item["owner_decision_required"]
            or item["finance_decision_required"]
            or item["external_gate"] != "none"
        ):
            raise ValueError(f"READY item has an unresolved gate: {item['milestone_id']}")
        if (
            item["readiness_state"] == "BLOCKED_OWNER_DECISION"
            and not item["owner_decision_required"]
        ):
            raise ValueError(f"Owner-blocked item lacks its gate: {item['milestone_id']}")
        if (
            item["readiness_state"] == "BLOCKED_FINANCE_DECISION"
            and not item["finance_decision_required"]
        ):
            raise ValueError(f"Finance-blocked item lacks its gate: {item['milestone_id']}")
        if item["readiness_state"] == "BLOCKED_EXTERNAL" and item["external_gate"] == "none":
            raise ValueError(f"Externally blocked item lacks its gate: {item['milestone_id']}")
        for successor in item["successor_ids"]:
            if item["milestone_id"] not in by_id(milestones, successor)["dependencies"]:
                raise ValueError("Successor edge is not reciprocal.")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(milestone_id: str) -> None:
        if milestone_id in visiting:
            raise ValueError(f"Dependency cycle at {milestone_id}")
        if milestone_id in visited:
            return
        visiting.add(milestone_id)
        for dependency in by_id(milestones, milestone_id)["dependencies"]:
            visit(dependency)
        visiting.remove(milestone_id)
        visited.add(milestone_id)

    for milestone_id in ids:
        visit(milestone_id)
    fingerprints = {
        canonical_digest(
            {
                "implementation_boundary": item["implementation_boundary"],
                "collision_domain": item["collision_domain"],
                "likely_repository_areas": item["likely_repository_areas"],
            }
        )
        for item in milestones
    }
    if len(fingerprints) != len(milestones):
        raise ValueError("Duplicate executable boundaries detected.")


def by_id(milestones: list[dict[str, Any]], milestone_id: str) -> dict[str, Any]:
    return next(item for item in milestones if item["milestone_id"] == milestone_id)


def main() -> None:
    bank = build()
    validate(bank)
    OUTPUT.write_text(json.dumps(bank, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for item in bank["milestones"]:
        counts[item["readiness_state"]] = counts.get(item["readiness_state"], 0) + 1
    print(json.dumps({"count": len(bank["milestones"]), "readiness": counts, "fingerprint": bank["fingerprint"]}))


if __name__ == "__main__":
    main()
