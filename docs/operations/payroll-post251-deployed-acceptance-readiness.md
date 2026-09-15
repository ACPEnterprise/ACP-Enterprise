# PAYROLL.POST251.DEPLOYED.ACCEPTANCE.READINESS.1

Prepared 2026-09-12 for protected Payroll authority `36fe3eeaa85905ef282b07ea8b7cc5482c335794` (PR #251). Historical PRs #225/#226/#232/#234/#239/#240 are superseded integration inputs and must not be replayed. PR #252 is documentation-only.

## Current state evidence

- `PAYROLL_TIME_CHAIN_INTEGRATED = YES`: protected `customer-management-v1` contains #251.
- `PAYROLL_TIME_CHAIN_DEPLOYED = YES`: `https://preview.allcountyhomeservices.com/backend-health` reported application version `36fe3eeaa85905ef282b07ea8b7cc5482c335794`, environment `preview`, database `connected`, and Redis `connected` on 2026-09-12.
- `PAYROLL_TIME_CHAIN_ACCEPTED = NO`: public health does not prove the deployed schema revision or Payroll encryption-keyring usability, and no authorized synthetic Preview acceptance identity/fixture scope was available to execute the evidence chain.

### Watch checkpoint: protected successor `96d67cb`

Protected and Preview advanced to `96d67cb73dbe4838e882e1551de5906eda598f4e`, a Migration-only successor that contains #251. Preview briefly returned two 502 responses during the transition, then `/backend-health` recovered and reported the exact successor SHA, Preview environment, PostgreSQL connected, and Redis connected. This preserves `INTEGRATED = YES` and `DEPLOYED = YES`; it does not satisfy schema/keyring/fixture acceptance gates.

PR #254 remains open and clean. It proposes the read-only endpoint:

`GET /api/v1/payroll/setup/employees/{employee_id}/readiness?pay_period_id={id}`

Do not call or depend on that route until a protected successor containing #254 is deployed. Once deployed, acceptance must verify bounded unauthenticated `401`, foreign-Company `404`, missing cross-domain authority `403`, unavailable evidence `409`, missing key configuration `503`, metadata-only output, exact blocker keys, and absence of protected values/ciphertext/nonces/keys/calculated amounts. The endpoint supplements but does not replace the sanctioned synthetic time-to-Payroll chain or keyring round-trip proof.

### Executor checkpoint: protected/deployed successor `52dc336`

Protected and Preview advanced to `52dc336766a67fc0c4698244b9894bab0fe65913`, which contains #251 and integrated #254. Public health reported Preview, PostgreSQL connected, and Redis connected. The deployed readiness route returned the required bounded unauthenticated `401` without leaking metadata.

Fresh-source qualification proved the legitimate migration lineage `e5g7i9k1m3o5 -> f6h8j0l2n4p6`, one head/current=head, and zero drift. The nine focused Job-clock, Workday, correction, Payroll-input, compensation, proration, encrypted-input, and readiness suites passed **43 tests**, including synthetic keyring load, encrypted round trip, rotation, wrong-Company AAD rejection, and tamper rejection.

These results accept the protected source contracts but do not attest the deployed database revision or mounted Preview keyring. No authorized OM2-C synthetic acceptance identities were issued at this checkpoint, so deployed fixture execution remains pending.

The sanctioned fixture grant must identify a non-payable Preview Company, Branch, two synthetic Employees (drafter and independent approver identities), synthetic Job and Appointment, isolated PayPeriod, permission grants, cleanup/retention owner, and explicit authorization for append-only synthetic clock/time/correction/compensation/proration evidence. It must prohibit Payroll run execution and collision with real Employee identities. Retain only IDs, states, reason codes, versions, and digests in acceptance evidence—never protected input values or key material.

## Host-level deployment evidence

Enterprise should run these read-only checks on the Preview host and retain their output without printing secret contents:

```bash
cd /opt/acp-enterprise/current
test "$(git rev-parse HEAD)" = "36fe3eeaa85905ef282b07ea8b7cc5482c335794" || \
  git merge-base --is-ancestor 36fe3eeaa85905ef282b07ea8b7cc5482c335794 HEAD
docker compose --env-file .env.preview -f docker-compose.preview.yml ps
docker compose --env-file .env.preview -f docker-compose.preview.yml run --rm migrate alembic heads
docker compose --env-file .env.preview -f docker-compose.preview.yml run --rm migrate alembic current
docker compose --env-file .env.preview -f docker-compose.preview.yml run --rm migrate alembic check
docker compose --env-file .env.preview -f docker-compose.preview.yml exec -T backend \
  python -c 'from app.core.config import settings; from pathlib import Path; p=settings.payroll_input_encryption_key_file; assert p and Path(p).is_file() and Path(p).stat().st_size > 0'
curl --fail --silent --show-error https://preview.allcountyhomeservices.com/healthz
curl --fail --silent --show-error https://preview.allcountyhomeservices.com/backend-health
```

Expected schema for exact #251 is one head/current head `e5g7i9k1m3o5`. A successor is acceptable only when it contains #251 and its own migration lineage is legitimate. The keyring check proves configured/readable/nonempty without disclosing key material; an authorized synthetic encrypted-input round trip is still required to prove actual key usability.

## Deterministic acceptance suite

Against an isolated PostgreSQL database built from the exact deployed source:

```bash
cd backend
ENVIRONMENT=test DATABASE_URL=<isolated-postgresql-url> PYTHONPATH=<isolated-deps>:. \
  python -m pytest \
  tests/timekeeping/test_job_clock_operations.py \
  tests/timekeeping/test_workday_authority.py \
  tests/timekeeping/test_payroll_time_source_acceptance.py \
  tests/payroll/test_time_input_operations_integrity.py \
  tests/payroll/test_policy_authority.py \
  tests/payroll/test_period_input_assembly_acceptance.py \
  tests/payroll/test_compensation_proration_policy.py -q
```

This suite is the acceptance authority for: authoritative clock stop; open/awaiting/rejected exclusion; current accepted revision only; predecessor exclusion after correction; overlap fail-closed behavior; no scheduled or Job-elapsed substitution; shared Job-labor/Payroll evidence identity; effective compensation by work date; unauthorized compensation overlap rejection; explicit `UNSELECTED`, `BLOCK_PAYROLL`, and `BY_WORK_DATE`; replay; and unsupported salary proration fail-closed behavior.

## OM2-B handoff evidence

When #238 or its protected successor is deployed, OM2-B needs these identities/digests—not a duplicate time model:

- Company, Branch, Employee, and pay-period scope;
- accepted Workday `revision_id`, predecessor/successor lineage, `work_date`, approved minutes, and evidence digest;
- payable inclusion or truthful exclusion reason;
- compensation `authority_id`, version, effective interval, authority digest, and successor lineage;
- approved proration policy identity/version/method/digest and approver evidence;
- final Payroll-input allocation/result digest.

Use sanctioned synthetic Employee/Job/Appointment/time fixtures only. Do not create payable evidence for a real Employee, execute Payroll, calculate/file tax, post Accounting, move money, or touch Production.
