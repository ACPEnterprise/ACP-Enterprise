# LIA current-state authority map

Audit authority: `origin/customer-management-v1` at the start of
`LIA.MODULE.COMPLETION.1`.

| Capability | Classification | Product treatment |
|---|---|---|
| Development Factory LIA supervisor/worker/review CLI | AUTHORITATIVE, NOT PRODUCT LIA | Preserved and excluded from product runtime |
| Application shell `AIWorkspace` placeholder | PARTIAL | Superseded by the routed governed workspace; shell seam remains available |
| Command Center assistant rows | PARTIAL | Historical coming-soon indicators; no domain mutation delegated |
| AuthorizationContext and permission dependencies | AUTHORITATIVE | Reused before adapter selection and retrieval |
| Customers, Jobs, Scheduling, Estimates query models/services | AUTHORITATIVE | Governed read adapters consume tenant-scoped domain evidence |
| Invoicing and Payments | AUTHORITATIVE | Distinct adapters and language preserve invoice/payment/settlement boundaries |
| Purchasing and Inventory | AUTHORITATIVE | Read-only state adapters; approval/movement stays in domain services |
| Business Economics | AUTHORITATIVE | LIA explains only admitted results; does not recompute economics |
| Beacon | AUTHORITATIVE | Stable composition seam; signal lifecycle remains owned by Beacon |
| Migration readiness | AUTHORITATIVE | Stable composition seam; no cutover action is exposed |
| Luminary product findings | AUTHORITATIVE | Accepted persisted briefing adapter is Company/Branch and permission scoped |
| Beacon intelligence packet | AUTHORITATIVE_ON_QUALIFIED_INTEGRATION_BRANCH | `BEACON.INTELLIGENCE.v1` is adapted without changing Beacon quality or action authority |
| Business Economics LIA evidence | PARTIAL | Stable interface exists; accepted Economics adapter remains an explicit source gate |
| Product LIA request/response/provenance contract | AUTHORITATIVE | `lia-governed-assistant/v1` remains the runtime foundation |
| LIA safety/evidence/tool contracts | QUALIFIED_INTEGRATION_BRANCH | `LIA.FOUNDATION.v1` and `LIA.READ_ONLY.v1` add provider-neutral safety contracts |
| Product model provider | BLOCKED_EXTERNAL | Provider-neutral protocol and explicit `AI_PROVIDER_NOT_CONFIGURED` gate |
| Product conversation transcript retention | BLOCKED_POLICY | No transcript persistence; configurable policy remains required |
| Autonomous LIA business mutation | NOT_APPLICABLE | Explicitly prohibited; proposals are non-executing |

No historical Migration worktree or Development Factory LIA contract is used as
the product assistant's authority.
