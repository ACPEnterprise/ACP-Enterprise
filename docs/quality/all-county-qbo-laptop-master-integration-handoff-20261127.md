# Laptop Master handoff: All County QBO historical migration

Status: **integration handoff only**. This document authorizes neither deployment nor
QuickBooks access. Laptop Master remains the sole integration authority.

## Immutable inputs

- Application candidate: `3b227b2ca72dce37918d6cd700be6dc460f0622c`
- Remote ref: `origin/work/om1a-qbo-fresh-readonly-supplement-13`
- Preserved archive population: 20,702 records and 97,093 relationships
- Historical source cutoff: `2026-11-19`
- Original bounded-envelope digest recorded by surviving controls:
  `e4d672c1cdfca858e4a8e923a51a86627753c7ea1fedc695daa98066a5dc6041`
- Custody manifest SHA-256:
  `f6640c0d531eaa8a822e82f697b3aaead65c8ae7b52a3c527e9616642c4d4f4a`
- Custody set SHA-256:
  `dc682d25fa20327ee0c7663835a99f61feefdc93e1161466a5f0528c37d998ed`
- Exception workbook SHA-256:
  `e8e152272b131864fb264a9223e9c7a3020f6bd0072cfb08a1e1d889ed9f7d85`
- Exception workbook receipt SHA-256:
  `e071626515c5387bc6e708c3ac550a82642ff5a97b288e491c2a9941657f13ca`

Transfer the archive and workbook through approved evidence custody. Keep directories
mode 0700 and files mode 0600; mount source evidence read-only. Do not place financial
evidence, OAuth credentials, or tokens in Git.

All seven disclosed conflicts remain held: the five-row `$0.00` General Ledger
presentation difference; the `$100,801.91` A/R bridge; 73 unlinked payments totaling
`$85,414.91` versus `$87,544.91` provider unapplied; 102 unposted AmEx rows including
four repeated rows with a `-$872.76` duplicate-removal effect; payroll gross and net
coverage differences of `$41,734.39` and `$35,846.00`; unavailable detailed payroll
API records under the accounting scope; and the absence of authorized native posting.
No conflict has an approved automatic disposition.

## Candidate-specific acceptance

Focused QBO, attachment custody, callback, release-deployer, and Beta contract tests
passed `71/71`. The wider non-database QBO/release suite passed 207 tests with 11
skips. Ruff, Ruff format, and MyPy passed.

Candidate-specific assembled acceptance for
`3b227b2ca72dce37918d6cd700be6dc460f0622c` passed on 2026-11-28. The run started
from an empty disposable PostgreSQL 16 database, migrated through the single head,
bootstrapped the isolated accounting company, built the backend and frontend images,
and exercised authenticated browser readback. Authentication, authorization, tenant
isolation, restricted `acp_app` runtime identity, forced RLS, protected-principal
lifecycle, restart/readback, and backup plus isolated restore across 429 public tables
all passed. The mode-0600 browser receipt is outside Git at:

`/Users/michaelbfouse/ReleaseEvidence/qbo-historical-migration-20261127/authenticated-browser-acceptance-3b227b2c.json`

SHA-256:
`af014f998425de3dd375e8a2fc20b1e96e28a1b55b39f816e3b900bc76f0535f`

The receipt binds the exact candidate, authenticated isolated QBO historical fixture,
`/financial-reports` route, 20,702 records, 97,093 relationships, 46,405 report rows,
visible unresolved financial exceptions, and a browser-artifact digest. The acceptance
created only disposable local state and made no provider call.

The seven previously reported failures in
`backend/tests/qbo_source/test_native_application.py` passed `7/7` in 2.03 seconds
under Python 3.12.13 against the same disposable PostgreSQL 16 topology through its
loopback port. Their final disposition is **environment-only**: the prior host run used
the Compose-only hostname `postgres`; a diagnostic retry also confirmed macOS system
Python 3.9 is too old for the application's Python syntax. No source correction or gate
exception was needed. Exact node IDs and environment evidence are recorded in
`docs/quality/all-county-qbo-saturday-qualification-20261128.json`.

The original reproducible command remains:

```bash
test "$(git rev-parse HEAD)" = "3b227b2ca72dce37918d6cd700be6dc460f0622c"
ACCEPTANCE_COMPOSE_OVERRIDE="$PWD/docker-compose.qbo-historical-acceptance.yml" \
QBO_HISTORICAL_ARCHIVE_HOST="/Users/michaelbfouse/ReleaseEvidence/qbo-accounting-acquisition-20261119-readonly-copy" \
ACCEPTANCE_OWNER_EMAIL="mifo66@gmail.com" \
ACCEPTANCE_COMPANY_NAME="All County Plumbing & Leak — Accounting Migration" \
ACCEPTANCE_COMPANY_CODE="ALLCOUNTY-QBO-HISTORY" \
ACCEPTANCE_FRONTEND_PORT=18192 \
ACCEPTANCE_BROWSER_OUTPUT="/Users/michaelbfouse/ReleaseEvidence/qbo-historical-migration-20261127/authenticated-browser-acceptance-3b227b2c.json" \
scripts/qualify-application-integration.sh
```

Any integration successor must reproduce or independently accept this candidate-bound
receipt, retain the source-manifest seals, isolated company, report totals, tenant
denial, and all seven exceptions, and make no provider call before governed owner OAuth.

## Governed Beta prerequisites

Before any Beta release, Laptop Master must have all of the following:

1. Clean integration of the exact candidate with a single Alembic head and no
   unexpected migration. This candidate adds no migration.
2. Current Beta database backup, verified isolated restore receipt, candidate-bound
   rollback target, Enterprise qualification receipt, and recorded Release GO.
3. Authorized release actor, trusted Beta SSH identity/host key, and short-lived
   authenticated acceptance principal through the existing custody workflows.
4. The direct-Beta URI registered in the existing Intuit Production application while
   preserving the existing Preview URI:
   `https://beta.twelve-hats.com/api/v1/integrations/qbo/production/oauth/callback`.
5. Protected, persistent QBO runtime and evidence volumes, with parent directories
   mode 0700 and secret/config files mode 0600. Confirm backup and recovery of sealed
   evidence without copying tokens into release artifacts.

The mode-0600 Beta runtime environment must contain these exact non-secret bindings:

```text
QBO_PRODUCTION_ENABLED=true
QBO_PRODUCTION_ACP_COMPANY_ID=3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd
QBO_PRODUCTION_CALLBACK_URI=https://beta.twelve-hats.com/api/v1/integrations/qbo/production/oauth/callback
QBO_PRODUCTION_RUNTIME_ROOT=/var/lib/acp-qbo-production
QBO_PRODUCTION_EVIDENCE_ROOT=/var/lib/acp-qbo-production-evidence
```

Provision the protected client document only at
`/var/lib/acp-qbo-production/secrets/production-client.json`. Provision the exact,
case-sensitive CompanyInfo binding `All County Plumbing and Leak`, independently
corroborated by the sealed November 19 reconciliation register, only at
`/var/lib/acp-qbo-production/configuration/expected-company-name`. The token document
must not exist before owner authorization. Verify ownership, mounts, permissions, and
credential readback without printing values.

The sanctioned deployer must be invoked by the authorized release actor with the
explicit `--allow-qbo-production-read-only` flag. Its fail-closed guard verifies the
exact callback, tenant UUID, runtime root, and evidence root. Do not weaken that guard.

## Owner OAuth and read-only enforcement

Only after Beta serves the approved SHA and protected configuration passes:

1. The owner signs into `https://beta.twelve-hats.com` as the existing All County
   Company administrator in a fresh browser.
2. In **Administration**, the owner selects
   **Connect REAL QuickBooks — Read Only**.
3. The owner verifies an HTTPS redirect to `appcenter.intuit.com` for the existing ACP
   Command Center application and selects only the intended All County company.
4. The owner reviews the provider's QuickBooks Accounting scope and completes Intuit
   authorization. No OAuth URL, code, token, or credential is relayed through chat.
5. The callback must return to the exact Beta URI. TwelveHats must reject any realm or
   exact `CompanyInfo.CompanyName` mismatch before committing the protected token.

Intuit's accounting scope is not granularly read-only. TwelveHats enforces read-only
operation with a GET-only entity/report adapter, transport rejection of accounting API
POSTs, exact tenant/realm/company binding, protected evidence custody, and no exposed
financial mutation command. OAuth token exchange, refresh, and revocation are the only
bounded non-GET provider operations; they do not post accounting data. Authorization
does not permit payments, payroll, banking changes, posting, or money movement.

After authorization, the governed operator first runs a CompanyInfo read probe, then a
uniquely timestamped bounded acquisition. Seal its separate snapshot identity, catalog
v3 manifest, per-family counts, attachment dispositions and body digests, relationship
counts, and reconciliation delta. It supplements but never overwrites or masquerades as
the November 19 archive. Every attachment must be `BODY_SEALED`,
`BODY_URL_UNAVAILABLE`, or `NOTE_ONLY` before completeness can be accepted.

## Rollback

Record the exact prior immutable release directory from `.release-metadata.json` before
deployment. If application verification fails, use the deployer's automatic rollback.
For an operator rollback, run `scripts/deploy-preview-release.py rollback` against the
verified prior `enterprise-beta-*` directory and include
`--allow-qbo-production-read-only` only when that target's protected environment has
QBO enabled. The deployer atomically restores `current`, recreates the selected
application services, and reruns health, schema, Beta connectivity, PostgreSQL, and
Redis identity checks.

This application candidate has no database migration and authorizes no financial
mutation. Do not delete or revoke the protected token, remove evidence, restore a
database, or alter Intuit registration during application rollback without separate
governed authorization. Preserve sealed snapshots and audit records. If a later
database mutation is separately authorized, use only its candidate-bound verified
backup/restore rollback procedure.

## Acceptance boundary

Local candidate qualification is complete. Final release acceptance still requires
protected integration, serving-SHA readback, successful fresh GET-only provider
acquisition after owner OAuth, complete supplemental reconciliation, and explicit
owner/Finance review. No independent deployment, QuickBooks mutation, native posting,
or conflict resolution is authorized by this handoff.
