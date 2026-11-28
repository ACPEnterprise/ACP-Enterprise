# OM2-B Keith sales-training restoration handoff

## Scope and result boundary

This candidate restores only the fixed synthetic tenant `TwelveHats Demo Services`
(`c36895cf-8a6f-5c31-a2ed-474dee8d0fc4`). It does not deploy, modify the hosted
database, invite a user, reset a password, accept the NDA for a user, call
QuickBooks, send customer communications, or execute a financial transaction.

The repository proves that the original sales-training UI, enrichment, and
estimating paths target that fixed company. The current repository contains no
protected hosted catalog receipt proving whether the company or Keith identity is
present after the recent database promotion. That omission must therefore be
classified as `UNVERIFIED`, not assumed. The read-only inspection below gives
Laptop Master a secret-free determination before any restoration is authorized.

## Candidate behavior

- Reads Keith's existing login email only from a mode-0600 protected file.
- Requires an existing active user and existing credential; it never reads,
  prints, hashes, replaces, or rotates the password.
- Refuses restoration if the identity has an invited, active, or suspended
  membership in any non-Demo company.
- Recreates the fixed synthetic company and connected training records only when
  both the fixed company and per-user Demo environment are absent.
- Reuses only a complete ready fixed tenant; partial or ambiguous state fails
  closed without repair.
- Replays deterministic enrichment and verifies credential hash and version are
  unchanged before commit.
- Retains the mandatory `SALES_DEMO` agreement gate. Agreement acceptance remains
  a first-login user action and cannot be manufactured by this command.
- Inherits the Sales Demo guard requiring a non-production runtime with
  QuickBooks production, communications delivery, identity outbox delivery, and
  Google Ads live access disabled.

## Laptop Master hosted inspection and activation

Create the protected identity file without showing its content in shell history or
logs, then set mode 0600. Run from the backend application environment with the
hosted configuration already supplied through approved secret custody:

```bash
python backend/scripts/restore_sales_demo_access.py \
  --identity-file /run/secrets/keith_sales_demo_login
```

Interpretation:

- `READY`, company present: the promotion retained the tenant; investigate login
  or agreement state without restoring data.
- `READY`, company absent: the promotion omitted the tenant, and restoration is
  eligible after Laptop Master reviews the protected backup/catalog evidence.
- user not found: Keith's original identity was omitted; stop. Do not create a new
  identity or change credentials under this handoff.
- `BLOCKED`: Keith has non-Demo company access. Stop and reconcile access; never
  run `--apply`.

Only Laptop Master or the authorized hosted operator may perform the mutation:

```bash
python backend/scripts/restore_sales_demo_access.py \
  --identity-file /run/secrets/keith_sales_demo_login \
  --apply
```

The result must report `PASS`, the fixed Demo company ID,
`credential_preserved: true`, zero non-Demo access memberships, and enrichment
version `twelvehats.sales-demo.v2`. Separately verify that the approved agreement
is published using the existing immutable agreement release procedure. Never put
the identity file, command output from protected infrastructure, or credentials in
Git.

## Independent authenticated acceptance

Use an approved Chromium launch coordinated by Laptop Master. Do not weaken the
host sandbox. At desktop (1440 x 1000), tablet (820 x 1180), and mobile
(390 x 844), perform all of the following:

1. Sign in with Keith's existing credential through the UI.
2. Verify the agreement gate appears before application access when no acceptance
   receipt exists; accept only as Keith during authorized owner/reviewer acceptance.
3. Verify the company selector/API accessible-company response contains exactly
   `TwelveHats Demo Services` and its fixed ID.
4. Request `/api/v1/authorization/context` with the Demo company header and verify
   the fixed Demo company ID is returned.
5. Repeat the context request with the protected All County company ID and require
   HTTP 403 `Tenant access denied.` Do not record that protected ID in Git.
6. Open `/sales-demo`; verify eight guided scenarios and working customer,
   dispatch, estimate, invoice, Beacon, Luminary, and LIA navigation.
7. Create/edit a synthetic estimate, invoice, and payment record. Verify every
   record remains in the Demo tenant and is labeled synthetic.
8. Verify communications delivery, QuickBooks production access, identity outbox
   delivery, Google Ads live access, payroll/tax execution, banking, and external
   payment execution remain disabled.
9. Sign out and repeat direct All County denial after a fresh sign-in.

The existing component qualification covers the three viewport widths, but it is
not a substitute for the authenticated browser procedure above. Passing synthetic
qualification does not establish actual All County operational acceptance.

## Qualification recorded on OM2-B

- Python syntax compilation: PASS.
- Patch whitespace validation: PASS.
- Sales Demo responsive component suite: PASS, 1 file / 4 tests, including
  390 px, 820 px, and 1440 px cases.
- Database-backed restoration tests: prepared, not run while system load exceeded
  the coordinated heavy-work threshold and the owner-inspection stack remained
  reserved.
- Hosted catalog inspection, authenticated API denial, and physical browser
  acceptance: pending Laptop Master authorized access and execution.

Until those final three gates pass, hosted restoration status is **FAIL / NOT YET
ACCEPTED**. This is a qualified candidate handoff, not a claim that Keith's hosted
access has already been restored.
