# Beta Payroll and Dispatch cutover readiness 1

This packet qualifies deployment infrastructure only. It does not approve Payroll,
Dispatch, Scheduling, My Day, business-data mutation, or Production deployment.

Run the public and fail-closed smoke without credentials:

```sh
sh scripts/verify-beta-payroll-dispatch-cutover.sh
```

Exit 2 is expected until Release provides three distinct sanctioned, mode-0600 token
references through `PAYROLL_TOKEN_FILE`, `DISPATCH_TOKEN_FILE`, and
`EMPLOYEE_TOKEN_FILE`. The script never places token contents in command arguments or
output. The Payroll identity must have reporting-read authority, the Dispatch identity
must have Scheduling/Dispatch read authority, and the Employee identity must have own
day read authority. Do not substitute owner credentials for automated acceptance.

Optionally set `SMOKE_START_AT` and `SMOKE_END_AT` to a bounded ISO-8601 interval.
Every request is GET-only and response bodies are discarded. A 401/403 is classified
as authorization-blocked, another 4xx as a truthful domain blocker, and any 5xx as a
runtime failure. Passing this smoke proves route/API/runtime connectivity only, never
real workflow acceptance.

Issue #473 remains a separate P1 release-safety gate. Until its data-service topology
contract is reconciled, application releases must preserve the authoritative standalone
Preview PostgreSQL and Redis containers and must not run ordinary full-stack Compose.
