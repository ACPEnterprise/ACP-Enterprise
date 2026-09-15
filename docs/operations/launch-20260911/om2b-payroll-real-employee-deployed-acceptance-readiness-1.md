# Payroll real Employee deployed acceptance readiness

## Current gate

- Protected authority observed 2026-09-12: `d4eee6f6b0bc178d58654f26f3ef2b9429332ab3`.
- Preview `/backend-health` reported the same release SHA, healthy PostgreSQL and
  Redis, and environment `preview`.
- PR #238 (`82d7fc1ac7d352b945444cccfa09dc345b83e2a1`) is open and
  mergeable, not protected-integrated or deployed.
- The unauthenticated Employee Setup route returned bounded `401 Authentication
  required`, proving the protected route without disclosing Employee data.
- PR #246 remains an open preflight packet. Neither candidate was modified here.

Result: `DEPLOYED_ACCEPTANCE_BLOCKED_PR238_NOT_INTEGRATED`.

There is a second acceptance gate that Enterprise must reconcile during #238
integration. #238 supplies `payroll.real-employee-readiness-assembly.v1`, retained-key
decryption, and deterministic tests, but no runtime route or service currently calls
`assemble_real_employee_readiness`. The protected Employee Setup endpoint derives its
status from the latest persisted `PayrollRunMemberRecord`; absent one, it returns only
`PAYROLL_RUN_ADMISSION_REQUIRED`. Therefore merging #238 alone does not mechanically
prove that the product can display the assembly's exact blocker categories. Do not
represent that generic blocker as deployed real-Employee assembly acceptance.

## Enterprise preconditions

1. Integrate #238 on the then-current protected authority without separately stacking
   superseded #223, #228, or #233.
2. Reconcile an authorized read-only runtime projection from the Employee Setup path to
   the #238 assembly, or identify the already-authoritative route that does so. It must
   return presence/provenance and exact blockers only, never decrypted values.
3. Configure the Preview keyring by the mounted-file procedure in PR #246.
4. Deploy one coherent Preview release and require `/backend-health.version` to equal
   the protected integration commit.
5. Use an authorized Payroll-administrator session and Company-scoped Employee
   resolution. Never place access tokens, Employee IDs, or response bodies in logs or
   repository artifacts.

## Secret acceptance

Run these checks inside the deployed backend container. Commands must emit fixed
PASS/FAIL labels only. Do not enable shell tracing and do not print settings, the
keyring, environment, ciphertext, nonce, decrypted payload, or exception repr.

1. Construct the repository `_input_service()` and require
   `PAYROLL_INPUT_KEYRING_READY`. This proves the active key ID exists and decodes to an
   accepted 32-byte AES key. A file value is authoritative in Preview; do not configure
   a divergent environment keyring.
2. With a sanctioned in-memory canary payload and synthetic Company UUID, use the
   deployed `ProtectedPayrollInputCipher` to encrypt and decrypt under the active key.
   Compare only its canonical digest and emit `ACTIVE_KEY_ROUND_TRIP_PASS`.
3. For every retained key ID, instantiate the same cipher with that key active and run
   the same in-memory authenticated round trip. Emit only a count and
   `RETAINED_KEYS_ROUND_TRIP_PASS`; never emit key IDs or values.
4. Attempt to decrypt the canary using a different synthetic Company UUID and require
   `PayrollConflictError`. This is `COMPANY_AAD_ISOLATION_PASS`.
5. Attempt a digest mismatch and require `PayrollConflictError`. This is
   `CONTENT_DIGEST_AUTHENTICATION_PASS`.
6. Construct an isolated test configuration with an absent active ID, missing active
   key, malformed Base64, and wrong decoded length. Each must fail closed. Do not alter
   the running container environment or mounted keyring to conduct negative tests.
7. Against a sanctioned synthetic historical setup record, prove its stored key ID can
   still decrypt after rotation and that a new synthetic revision uses the new active
   ID. Retain both keys. Do not use Lianne's values for this test.

The existing setup write path must map live malformed/missing configuration to HTTP
503 `Protected Payroll input configuration is unavailable.` No fallback plaintext,
default value, or zero is permitted. If any check fails, disable protected setup
changes, preserve the database and complete keyring, and restore the last-known-good
active ID/configuration. Never remove a key referenced by a retained envelope; no
authoritative rewrap/key-retirement facility exists.

After the synthetic checks, inspect bounded API responses, application logs, generic
Business Events, audit projections, and the browser mutation cache using a unique
non-sensitive canary marker. The marker, protected payload keys, ciphertext, nonce,
key material, and decrypted content must be absent. Presence flags, authority IDs,
versions, effective dates, key IDs stored as envelope metadata, and evidence digests
may appear only where authorized and necessary.

## Lianne read-only acceptance

Use normal authenticated ACP navigation: Employee roster → Lianne → Pay. Resolve the
Employee through Company-scoped product navigation; do not enter a UUID manually.
This acceptance does not draft, approve, calculate, transmit, or alter anything.

Record only:

- deployed SHA and readiness/assembly contract versions;
- `READY_FOR_PAYROLL` or `BLOCKED_FOR_PAYROLL`;
- exact category and blocker keys returned by deployed authority;
- evidence IDs, versions, effective dates, and digests where the viewer is authorized;
- provider/source versions and reconciliation version; and
- a redaction/leakage PASS/FAIL result.

Do not record input values. Do not assert that compensation, W-4, jurisdiction,
deductions, YTD, accepted time, Payroll period, provider, or reconciliation is missing
unless the deployed response explicitly reports that category. A UI response containing
only `PAYROLL_RUN_ADMISSION_REQUIRED` proves neither those individual blockers nor the
#238 assembly and must be recorded as `RUNTIME_ASSEMBLY_PROJECTION_UNAVAILABLE`.

For every reported field, require one of `AVAILABLE`, `AUTHORITATIVE_ZERO`, `MISSING`,
`CONFLICTING`, or explicit `NOT_APPLICABLE`. Zero satisfies a requirement only when it
has complete authority provenance. Blank, absent, unreadable, unapproved, stale, or
conflicting evidence must not become zero or ready. The response and browser cache must
not contain protected values, ciphertext, nonce, or an encryption key.

## Provider acceptance

Using sanctioned synthetic assembly evidence first, then Lianne's metadata-only
projection, require:

- the provider selected by the Payroll period effective date;
- provider/source authority, publication/version, source digest/reference, effective
  interval, and calculation method version are explicit;
- federal withholding, employee/employer Social Security, employee/employer Medicare,
  and Additional Medicare prerequisites are separately represented;
- periods outside provider authority remain blocked;
- explicit `US-FL` work and residence evidence is required before Florida state income
  tax is `NOT_APPLICABLE`; missing, non-Florida, or conflicting jurisdiction must not
  produce that result; and
- no tax election or calculated tax amount is inferred, returned, or recorded for
  Lianne during readiness acceptance.

The independent evidence version must be
`payroll.federal-tax-2026-reconciliation.v1`. Provider selection alone is not
reconciliation and must not clear that blocker.

## Payroll-period implementation start gate

Return `PAYROLL_PERIOD_ASSEMBLY_IMPLEMENTATION_ALLOWED` only when all are true:

1. #238 is an ancestor of current protected authority and the coherent deployed SHA;
2. the deployed authorized Employee path invokes the real assembly contract and exposes
   exact protected-value-free blockers;
3. active/retained-key, Company-AAD, tamper, rotation, and leakage checks pass;
4. the Lianne read-only flow truthfully returns READY or exact BLOCKED reasons;
5. effective-date provider, source manifest, FICA authority, Florida applicability, and
   independent reconciliation checks pass; and
6. accepted time remains bound to the current approved
   `payroll.time-input-projection.v1` revisions and digests.

The allowed implementation must consume these protected authorities without copying
them: `payroll.real-input-readiness.v1`,
`payroll.real-employee-readiness-assembly.v1`,
`payroll.tax-deduction-authority.v1`, the protected 2026 federal provider and source
manifest, `payroll.federal-tax-2026-reconciliation.v1`,
`payroll.time-input-projection.v1`, approved effective compensation authority, and the
existing Payroll input envelope tables created by
`w4n6j8l0o275_create_payroll_input_authority.py`. #238 adds no schema migration.

Current result: `PAYROLL_PERIOD_ASSEMBLY_IMPLEMENTATION_NOT_ALLOWED`.

No Payroll execution, tax filing/payment, Accounting posting, money movement, Preview
mutation, Preview deployment, or Production action was performed.
