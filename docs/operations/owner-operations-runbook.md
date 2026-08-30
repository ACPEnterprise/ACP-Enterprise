# Owner Operations inspection runbook

Owner Operations is a read-only composition of accepted authority. It does not
grant roles, execute Payroll, post Accounting entries, run Migration, connect a
provider, adjust Inventory, approve Purchasing, or deploy a release.

## Inspection sequence

1. Open **Owner Operations** with `COMPANY_ADMINISTER`.
2. Review required and degradable system-health components. A responding HTTP
   process is not sufficient evidence of readiness.
3. Confirm the active Company and explicit Branch grants.
4. Review QuickBooks Development and HCP Migration readiness. Perform provider
   authorization or migration execution only in their owning workspaces and
   only with separate authority.
5. Review mobile prerequisites. A mobile-capable Employee requires an active
   Membership→Employee binding, Branch grant, and explicit own-data/field
   permission; possession of a session is not authority.
6. Use permission explanation for the current signed-in identity. `ALLOWED_BY_ROLE`
   means the current authorization context includes the permission and requested
   Branch. Denials never become grants.
7. Use canonical launch roles as acceptance fixtures, then verify direct API
   denial as well as navigation visibility.
8. Follow links to the domain that owns any blocker. Owner Operations never
   resolves domain reconciliation itself.

## Recovery states

Use the Operator Guide for `RETRY_SAFE`, `RETRY_AFTER_REFRESH`,
`USER_CORRECTION_REQUIRED`, `OWNER_ADMIN_ACTION_REQUIRED`,
`RECONCILIATION_REQUIRED`, `TEMPORARILY_UNAVAILABLE`, and `TERMINAL_FAILURE`.
Never retry an uncertain financial/provider operation unless its owning domain
classifies the retry as safe.

## Physical-device preparation

Use synthetic identities only. Verify invitation claim, active Membership,
Membership→Employee linkage, Branch scope, own-data permissions, session refresh,
and revocation. Mobile signing and Preview deployment remain owned elsewhere.
