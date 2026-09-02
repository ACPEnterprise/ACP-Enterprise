<!-- markdownlint-disable MD013 -->

# Field Operations Source Contracts Program 1

## Authority boundary

The server resolves every field request through authenticated User, active Company Membership, active Employee, authorized Branch, current Dispatch assignment, and explicit technician permission. Client-provided Employee identity is never authority. Unassigned, foreign-Branch, and foreign-Company Jobs use the existing concealed not-found behavior.

Jobs, Customers, Assets, Price Book, Estimates, Invoicing, Payments, Communications, and Workforce retain their business truth. This program adds bounded projections and Job artifact custody; it does not create competing domain engines.

## Mobile source contracts

| Contract | Authority and recovery |
| --- | --- |
| `GET /api/v1/technician/jobs/{job_id}/sources` | Current assignment version plus minimum Customer contact, Invoice, Payment, Communications, and completion state. Refetch after stale/conflict or response loss. |
| `GET /api/v1/technician/jobs/{job_id}/price-book` | Assignment-scoped active customer-facing items and current price versions. Internal cost is absent. Results are bounded to 100. |
| `GET /api/v1/technician/history` | Authoritative Mobile successor contract: own primary/crew assignments only, active Company and authorized Branches, completed Jobs, bounded by period/count. |
| `GET /api/v1/technician/readiness` | Authoritative Mobile successor contract for own Fleet/workforce readiness and truthful policy/source/provider gates. |
| `GET /api/v1/technician/jobs/{job_id}/equipment` | Authoritative Mobile successor contract for assignment-scoped equipment and bounded service evidence. |
| `GET /api/v1/technician/jobs/{job_id}/estimate` | Authoritative Mobile successor contract for exact issued Estimate presentation. |
| `POST /api/v1/technician/jobs/{job_id}/artifacts/intents` | Validates assignment version, class, MIME, size, digest, and idempotency key. Returns an opaque reference; real protected byte storage remains provider-gated. |
| `POST /api/v1/technician/jobs/{job_id}/artifacts/intents/{intent_id}/finalize` | Exact digest/size/MIME binding. Exact replay returns the immutable evidence; contradictory replay conflicts. |

Opaque IDs and future deep links are locators, not authorization. Each resolution repeats current Membership, Employee, Branch, permission, and assignment checks.

## Projection limits

- Contact data is the preferred active Job Customer contact only. There is no Customer search, unrelated history, payment instrument, or internal note surface.
- Equipment remains governed by the integrated Mobile successor contract. History is bounded safe Asset evidence; warranty is readiness evidence, never an eligibility decision.
- Fleet/tool custody is limited to the active Employee and authorized Branch. It grants no Fleet Administration or Inventory mutation.
- Estimates are exact revisions already converted to the assigned Job. Technician Estimate creation/revision remains source-gated until accepted commercial command authority exists.
- Invoice and Payment are read-only, provider-neutral projections. They expose no instrument, merchant, or Accounting internals and grant no collection authority.
- Communications status is bounded to intents whose source entity is the assigned Job. Provider delivery remains separately gated.

## Artifact security and durability

`field_artifact_intents` records the governed upload request. `field_artifact_evidence` records finalized Job evidence. Finalized evidence is append-only: PostgreSQL rejects direct UPDATE and DELETE. Storage references are opaque and no filesystem/public URL is domain authority. Allowed media are JPEG, PNG, HEIC, and PDF up to 25 MB. Evidence emits only identifiers, class, and content digest.

The migration `m9n7q05f2s8t` is additive and parents the then-authoritative head `l8m6p94e1r7s`.

## Remaining truthful gates

- `PROVIDER_REQUIRED`: protected artifact byte storage; real Communications delivery; APNs/FCM push delivery.
- `POLICY_REQUIRED`: legal customer signature/authorization semantics; inspection definitions/cadence; technician collection tender/provider/reversal/offline policy.
- `SOURCE_REQUIRED`: technician Estimate creation/revision command authority; authoritative Employee in-app inbox/read state.

Provider-neutral lock-screen notification types and a fail-closed unconfigured push adapter are defined, but they do not fabricate in-app notification authority or enroll a device.

## Domain separation

Field approval does not create Inventory movement, AP liability, Accounting posting, payment settlement, or Payroll activity. Artifact evidence does not expose bytes through public URLs. Communications delivery failure does not rewrite Dispatch, Job, Estimate, Invoice, or Payment truth.

## Acceptance and recovery

High-impact commands use deterministic idempotency and current assignment state. Exact replay converges; changed payload conflicts. A lost response is reconciled by refetching authoritative source/readiness state before retrying the same idempotency key. The server never converts an uncertain provider outcome into success.

Qualification uses synthetic non-Production evidence and includes direct SQL artifact immutability attacks, assignment/tenant contract checks, broad affected regressions, migration lifecycle, static checks, and leakage scanning. Preview and Production deployment are outside this packet.
