# Commercial Core-Workflow Acceptance Ledger

Scope: Customer → Price Book → Estimate → Job → Dispatch → Invoice → office-observed payment evidence.

This ledger records customer-facing friction found during the November 18, 2026
acceptance sweep. The release SHA is the deployed commit reported with this
ledger; no provider, HCP, QBO, payroll, or money-movement action is part of this
acceptance.

| Page | Workflow | Class | Severity | Friction | Fix | Deployed SHA | Retest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Customers | Create customer | UNCLEAR LABEL | Medium | “Customer source” exposed a migration/data field in a normal office form. | Removed it from the customer-facing form while preserving the authoritative value. | Release commit | Automated UI pass |
| Customers | Create → next step | MISSING ACTION | Medium | A new customer could be saved without being told where to add the work address. | Reworded the empty location state and made “Add service location” the clear next action. | Release commit | Automated UI pass |
| Customers | Create customer | UNCLEAR LABEL | Low | “Internal customer context” sounded like a system field. | Renamed it “Notes for your team.” | Release commit | Automated UI pass |
| Estimates | Price Book selection | UNCLEAR LABEL | Medium | “Create immutable Estimate” and “active service” exposed implementation language. | Changed to “Save estimate,” “approved service,” and plain-language Price Book guidance. | Release commit | Automated UI pass |
| Price Book | Owner review | CONFUSING | Medium | “Candidate” terminology made retained services feel provisional or fabricated. | Reframed the bounded review surface as “All County owner review” and “Proposed selling price,” while retaining Draft/Held controls. | Release commit | Automated UI pass |
| Payments | Payment entry | TRUE DEFECT | High | Standalone Payments exposed provider-style IDs and a provider submission action in a normal office workflow. | Removed the collection form; route office users to invoice-level office-observed payment evidence with an explicit no-money-movement statement. | Release commit | Automated UI pass |
| Invoice | Accounting readback | MISSING ACTION | Medium | The invoice showed AR evidence but did not summarize where the transaction did and did not flow. | Added “Where this transaction appears” with receivable, payment evidence, cash/clearing, job revenue, and job-cost states. | Release commit | Build and UI pass |
| Estimates | Price Book selection | TRUE EXTERNAL DEPENDENCY | High | Clean Beta has 0 Active All County services, so no estimate can honestly sell a service yet. | No price was activated; the UI directs the owner to review Price Book Draft/Held services. | Release commit | Live Beta readback |
| Invoices | Completed job → invoice | TRUE EXTERNAL DEPENDENCY | Medium | Clean Beta returned no completed accepted-work invoice candidates for a safe live creation test. | No fabricated invoice or payment was created; existing invoice readback and manual-evidence path remain available. | Release commit | Live Beta readback |

## Acceptance interpretation

The normal office paths are clearer and safer, but the full commercial lifecycle
cannot be called green until an authorized owner activates at least one approved
Price Book service and Beta provides a sanctioned completed accepted-work fixture.
Those are controlled business/test-fixture decisions, not reasons to invent data
or bypass Price Book authority.
