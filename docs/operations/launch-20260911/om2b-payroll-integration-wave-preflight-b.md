# Payroll integration wave preflight B

## Pinned authority and candidate family

- Preflight observed protected authority: `d4eee6f6b0bc178d58654f26f3ef2b9429332ab3`.
- Candidate to integrate: PR #238, branch
  `work/payroll-real-employee-readiness-wiring-1`, commit
  `82d7fc1ac7d352b945444cccfa09dc345b83e2a1`.
- This packet adds no runtime feature or schema migration. Enterprise owns protected
  integration, secret installation, migration, and Preview deployment.

| Capability | Protected/candidate evidence | Classification | Enterprise action |
| --- | --- | --- | --- |
| `payroll.real-input-readiness.v1` | protected `150bcd2` (#220) | `INTEGRATED` | Preserve this canonical blocker/status contract. |
| Employee Payroll Setup | protected `27b89ec` (#235), superseding closed #223 | `INTEGRATED` | Do not integrate #223 separately. |
| Protected Payroll-input encryption | encrypted write-only envelopes and active-key sealing are protected in #235; retained-key authenticated decryption is in #238 | `READY_TO_INTEGRATE` | Install the keyring first, then integrate #238; retain every key ID referenced by stored envelopes. |
| 2026 federal/FICA provider | protected `8cf3bdb` (#236), superseding the provider portion of #228 | `INTEGRATED` | Do not integrate #228 separately. |
| Independent 2026 reconciliation | `payroll.federal-tax-2026-reconciliation.v1` is carried by #238 from #233 | `READY_TO_INTEGRATE` | Integrate through #238; do not separately stack conflicting #233. |
| Real Employee readiness assembly | `payroll.real-employee-readiness-assembly.v1` at #238 | `READY_TO_INTEGRATE` | Integrate #238 after the protected prerequisites above. |
| OM2-A accepted-time input | projection `payroll.time-input-projection.v1` at protected `ee88242` (#229), corrected-state admission at `40f4425` (#231), Mobile/labor reconciliation at `d52d117` (#216) | `INTEGRATED` | Bind immutable current approved Workday revision IDs and digests; never infer accepted time from a completed Job clock. |
| Persisted Payroll-period assembly | no protected composition of the complete assembly contract | `BLOCKED` | Begin only after #238 is integrated and deployed acceptance below passes. |

GitHub reported #238 open and mergeable at this checkpoint. A fresh protected-head
mergeability check remains mandatory immediately before integration because protected
authority can advance.

## Dependency order

1. Confirm protected contains #220, #235, #236, #229, #231, and #216 as shown above.
2. Install the Preview-only Payroll keyring and active key ID using the procedure below.
3. Integrate #238 once, without separately integrating #223, #228, or #233.
4. Run schema-head and qualification commands, then deploy one coherent Preview release.
5. Perform synthetic setup/rotation checks before authorized Lianne readiness inspection.
6. Run the read-only Lianne blocker acceptance. Do not calculate or execute Payroll.

## Preview protected-input configuration

The repository's Preview Compose contract sets
`PAYROLL_INPUT_ENCRYPTION_KEY_FILE=/run/secrets/acp/payroll-input-encryption-keyring.json`
and mounts the host directory named by `IDENTITY_ONBOARDING_DELIVERY_SECRET_DIR_HOST`
read-only at `/run/secrets/acp`. `PAYROLL_INPUT_ACTIVE_KID` comes from the
Enterprise-owned `.env.preview`. Although application settings also accept
`PAYROLL_INPUT_ENCRYPTION_KEYS` as a JSON environment value, Preview's authoritative
deployment mechanism is the mounted file; do not duplicate the keyring in both places.

The mounted file must be a JSON object whose keys are stable, non-secret key IDs and
whose values are URL-safe Base64 encodings of exactly 32 decoded bytes:

```json
{"preview-payroll-YYYY-NN":"<urlsafe-base64-of-32-random-bytes>"}
```

Set `PAYROLL_INPUT_ACTIVE_KID=preview-payroll-YYYY-NN` to one key ID present in that
object. Enterprise generates and installs the actual value outside Git, frontend
configuration, shell history, application logs, and this packet. The mounted file must
be readable by the backend container and not writable by it.

Validate without displaying key material after Compose configuration is rendered and
the backend is running:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml exec -T backend \
  python -c 'from app.payroll.setup_router import _input_service; _input_service(); print("PAYROLL_INPUT_KEYRING_READY")'
```

Then use a sanctioned synthetic Employee to draft and approve a protected successor,
and confirm all GET responses expose presence/provenance only. An absent active ID,
malformed JSON/Base64, missing active key, or active key not decoding to 32 bytes must
fail protected writes closed with HTTP 503 and the bounded message `Protected Payroll
input configuration is unavailable.` It must not fall back to plaintext or zero.

For rotation, add the new key ID while retaining all old key IDs, change only the active
ID, restart coherently, run the validation, and prove both a new envelope and an old
envelope can be authenticated. New writes use the active ID; existing envelopes use
their stored ID. No rewrap/key-retirement facility is authoritative, so an old key may
not be removed while any retained envelope can reference it.

Rollback restores the prior active ID and a superset keyring containing every key used
before or during the attempted rotation, followed by a coherent backend restart and the
same validation. Never roll back by deleting a newly used key. If validation fails,
disable protected setup changes, preserve the database and keyring, and restore the last
known-good deployment/configuration; no Payroll execution is authorized.

## Deterministic Lianne post-deploy acceptance

Resolve Lianne only through the authorized Company-scoped Employee UI/API. The
acceptance reads status, provenance, and exact blocker keys; it must not read decrypted
W-4, deduction, or YTD values. Do not enter, infer, screenshot, log, or export a missing
value for this acceptance.

For one explicit pay-period candidate, verify the chain in this order:

1. active Employee and effective approved compensation;
2. Employee-specific approved W-4 filing status and Steps 2, 3, 4(a), 4(b), and 4(c);
3. explicit work and residence jurisdiction (Florida non-applicability only when both
   authoritative values are `US-FL`);
4. effective deductions or explicit approved non-applicability;
5. same-Employee, same-payroll-year Social Security/Medicare and prior-Payroll/YTD
   evidence, including applicability prerequisites;
6. current approved Workday revisions for Lianne within the period, with correction
   lineage and no overlap;
7. explicit period start, end, and frequency;
8. the provider selected by the period effective date; and
9. independent reference version `payroll.federal-tax-2026-reconciliation.v1`.

At every step capture only the contract version, evidence IDs/digests, readiness state,
and exact blocker names. Missing evidence must remain `MISSING` and the Employee must
remain `BLOCKED_FOR_PAYROLL`; an authoritative zero is distinct and must carry complete
provenance. Foreign-Employee, wrong-year, overlapping-effective, stale-revision, or
conflicting evidence must block. The acceptance passes only when the final response is
`PAYROLL_READY`/operator `READY_FOR_PAYROLL`, exact blockers are empty, the provider and
reference versions are present, and no sensitive value was returned. This proves
readiness only; calculation preview and Payroll execution are separate authorities.

## Payroll-period next-gap contract

After #238 deployment acceptance, implement persistence/API composition against the
existing Payroll and Timekeeping authorities with these bindings:

- **Period identity:** immutable Company-scoped UUID plus period start/end, pay date,
  frequency, version, lifecycle, and canonical evidence digest; reject overlapping or
  ambiguous operating periods according to existing Payroll policy.
- **Employee scope:** an explicit bounded set of Company-scoped Employee IDs and the
  inclusion revision; additions/removals create a successor, not history mutation.
- **Accepted time:** bind the current approved `payroll.time-input-projection.v1`
  revision IDs, evidence digests, projection digest, and seal identity per Employee.
- **Compensation:** bind the one approved effective compensation authority ID, version,
  digest, and effective interval per Employee.
- **Proration policy:** bind an existing approved policy ID/version/digest or block with
  `proration_policy_missing`; do not invent or silently default policy.
- **Tax rules:** bind provider jurisdiction, provider version, source digests, and the
  effective date selected for the period, plus reconciliation evidence version.
- **Readiness snapshot:** persist the assembly/readiness contract versions, evidence
  digest, exact blockers, and snapshot time. Never persist decrypted setup values in the
  snapshot.
- **Replay/idempotency:** require a Company-scoped idempotency key over canonical period,
  Employee-scope, and evidence digests; exact replay returns the original identity,
  while same-key/different-content fails closed.
- **Corrections:** compensation, setup, period, or Timecard corrections create a new
  evidence revision and mark the prior readiness snapshot stale; preserve the original
  snapshot and lineage. Never silently mutate a reviewed or approved period.
- **Blocked state:** any missing, stale, partial, foreign, conflicting, unapproved, or
  unavailable dependency preserves exact blocker keys and prohibits calculation/final
  execution. Missing amounts are never rendered or serialized as zero.

The exact implementation gate is: #238 integrated, coherent Preview configuration and
deployment proven, synthetic retained-key acceptance passed, and Lianne's read-only
blocker chain observed truthfully. Until then, persisted period assembly remains
`BLOCKED` rather than being developed against a speculative contract.

## Enterprise qualification and deployment acceptance

Use a clean checkout of the integration candidate and a fresh PostgreSQL database:

```bash
cd backend
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic upgrade head
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" alembic heads
ENVIRONMENT=test DATABASE_URL="$QUALIFICATION_DATABASE_URL" pytest tests/payroll tests/timekeeping
ruff check app tests/payroll tests/timekeeping
mypy app/payroll app/timekeeping
python -m compileall -q app
cd ../frontend
npm run test:run
npm run lint
npm run build
cd ..
git diff --check
```

Require one Alembic head. #238 itself adds no migration; the existing protected Payroll
input tables come from `w4n6j8l0o275_create_payroll_input_authority.py`. After coherent
Preview deployment, verify the deployed release identity, keyring validation, authorized
Employee Setup navigation, protected write-only behavior, synthetic key rotation, exact
Lianne blockers, accepted-time staleness after a sanctioned correction fixture, and no
Payroll execution/posting endpoints invoked.

No protected merge, Preview deployment, Payroll execution, tax filing/payment,
Accounting posting, or money movement was performed by this preflight lane.
