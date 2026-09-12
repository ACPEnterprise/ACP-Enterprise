# Enterprise Payroll readiness merge assist

## Authority and integration state

- Starting/current protected authority: `36fe3eeaa85905ef282b07ea8b7cc5482c335794`.
- Integration wave #251 contains the #238 implementation, reconciliation, and tests.
  Because #251 is a composed/squashed integration, `82d7fc1` is not a Git ancestor;
  file and contract equivalence, not ancestry alone, proves integration.
- Protected prerequisites are present: Employee setup, protected input envelopes,
  `payroll.real-input-readiness.v1`, the 2026 provider, independent reconciliation,
  current approved-time projections/correction handling, PayPeriod authority, and
  governed compensation/proration policy.
- #238 itself remains open with GitHub mergeability recalculating after #251. Enterprise
  must close it as integrated-by-#251 rather than merge it a second time. After #251
  reached protected authority GitHub classified #238 `CONFLICTING`, as expected for the
  already-composed candidate.
- During this assist Preview advanced coherently to `36fe3ee`; backend health was
  healthy with PostgreSQL and Redis connected. The existing Employee Setup route
  returned bounded unauthenticated 401, while the readiness route proposed below
  returned 404, mechanically confirming the deployed runtime-wiring gap.

## Bounded runtime reconciliation

The integration wave retained #238's qualified assembly, but no production caller
invoked `assemble_real_employee_readiness`. Library tests alone could not support
deployed acceptance. This candidate adds one read-only route:

`GET /api/v1/payroll/setup/employees/{employee_id}/readiness?pay_period_id={id}`

It requires existing Payroll Setup read authorization plus the Payroll Reporting and
Timekeeping Admin read authorities already enforced by `PayrollOperationsService`.
It resolves only Company-scoped persisted authorities: Employee, existing PayPeriod,
current approved Workday snapshot, effective approved compensation, and effective
approved encrypted setup versions. It invokes the assembly with preview disabled.

The response contains only contract versions, Employee/period identities, readiness
status, category states, exact blocker keys, provider/reconciliation versions, and an
evidence digest. It cannot return protected values, envelopes, ciphertext, nonces, key
material, calculated amounts, or a Payroll execution artifact. No table or migration is
added.

Missing key configuration with protected evidence returns bounded HTTP 503. Retained
key/authentication or evidence integrity failure returns bounded HTTP 409. Missing or
foreign Company subjects return the same bounded 404. Insufficient cross-domain read
authority returns bounded 403.

## Enterprise integration qualification

On a clean candidate descendant with a fresh PostgreSQL database:

```bash
cd backend
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic upgrade head
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic heads
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" pytest \
  tests/payroll/test_employee_setup_api.py \
  tests/payroll/test_real_employee_readiness_wiring.py \
  tests/payroll/test_real_input_readiness.py \
  tests/payroll/test_tax_reconciliation_2026.py \
  tests/payroll/test_period_input_assembly_acceptance.py \
  tests/timekeeping/test_payroll_time_source_acceptance.py
ruff check app/payroll/setup_router.py tests/payroll/test_employee_setup_api.py
mypy app/payroll/setup_router.py app/payroll/real_employee_readiness_wiring.py
python -m compileall -q app
cd ..
git diff --check
```

Require one Alembic head and no new upgrade operation from this candidate. Also run the
repository credential/private-key scan.

## Preview configuration and deployment validation

Use PR #246's mounted Preview keyring contract. Before deploying, require the mounted
JSON object to contain the `PAYROLL_INPUT_ACTIVE_KID`, every value to decode to exactly
32 bytes, and every historical envelope key ID to remain present. Never print the file,
environment, IDs, values, or decoded material. Run `_input_service()` inside the backend
container and emit only `PAYROLL_INPUT_KEYRING_READY`.

Deploy one coherent protected candidate. Require:

1. `/backend-health` is healthy and its `version` equals the integration SHA;
2. Alembic reports exactly one current head;
3. unauthenticated readiness access returns bounded 401;
4. foreign-Company Employee/period combinations return bounded 404;
5. a sanctioned synthetic Employee proves active-key write/read, retained-key read,
   Company-AAD rejection, digest-tamper rejection, and rotation history;
6. response/log/Event/browser-cache canary inspection finds no protected value,
   ciphertext, nonce, key, or calculated amount; and
7. missing fields remain exact blockers and never numeric zero.

## Metadata-only Lianne acceptance

With an authorized Payroll administrator, resolve Lianne and an existing PayPeriod
through normal Company-scoped product behavior. Call the read-only readiness route and
record only status, returned category/blocker keys, contract/provider/reference
versions, IDs/digests, and leakage PASS/FAIL. Do not record or infer any W-4, deduction,
YTD, compensation, or tax value.

Do not assume prior blocker lists. If the deployed route reports compensation, W-4,
jurisdiction, deductions, YTD, accepted time, Payroll period, provider, or reconciliation
missing, report only those actual keys. `AUTHORITATIVE_ZERO` must have provenance;
absence remains `MISSING`. Florida state withholding can be `NOT_APPLICABLE` only after
the assembly resolves explicit `US-FL` work and residence evidence.

PR #247 should be reconciled to replace its runtime-projection blocker with this route's
result only after the candidate is protected-integrated and coherently deployed. Until
then its result remains `PAYROLL_PERIOD_ASSEMBLY_IMPLEMENTATION_NOT_ALLOWED`.

No Payroll-period persistence, Payroll execution, tax filing/payment, Accounting
posting, money movement, Preview deployment, or Production action is authorized here.
