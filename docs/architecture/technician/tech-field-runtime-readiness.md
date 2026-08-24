<!-- markdownlint-disable MD013 -->

# TECH.FIELD.1 Runtime Readiness

## Evidence snapshot

`TECH.FIELD.READY.1` reconciles the field-runtime packet against authoritative Enterprise commit `5f6649527d793a3f40d1a60d41af5e5c5c943ea7`. It authorizes no runtime, migration, deployment, scheduler assignment, or Production change.

| Dependency | Classification | Authoritative evidence | Effect on TECH.FIELD.1 |
| --- | --- | --- | --- |
| `TECH.1` | `AWAITING_OWNER_ACCEPTANCE` | The durable MMQ manifest records TECH.1 as `ready` with boundary version 2/fingerprint `04980ac90a5d1ed0e379600ab7e02cdc4f74fc767572c10cd35a79e3280442c9`; origin contains no technician application-shell frontend | Sole unresolved hard dependency |
| `OPS.1` | `COMPLETE_AND_AUTHORITATIVE` | `c89396546a6ba6012e48694ba7737bd30e316637` is an ancestor of authoritative Enterprise and the manifest records it complete | Satisfied |
| `DISP.2` | `COMPLETE_AND_AUTHORITATIVE` | `98ae82579d23d8b3737cce590186b93b865ef022` is an ancestor of authoritative Enterprise and the manifest records it complete | Satisfied |
| `EST.4` | `COMPLETE_AND_AUTHORITATIVE` | `62c0d84cd33cd5851a9a70db3dfbde67a09ce343` is an ancestor of authoritative Enterprise and the manifest records it complete | Satisfied |
| `INVOICE.1-3.ACCEL` | `COMPLETE_AND_AUTHORITATIVE` | Runtime commit `43018e22786341116f77a606ccf70a8fa1e3ae14` and identity correction `5f6649527d793a3f40d1a60d41af5e5c5c943ea7` are authoritative; the Accounting ledger records the milestone complete | Satisfied |
| `PAY.1-3.ACCEL` | `NOT_REQUIRED_FOR_INITIAL_RUNTIME` | `PAY.CONTRACT.1` is authoritative at `0915317370a75f7b529b2f4c9b39f8dd228c78e3`; no Payments runtime exists and the ledger records `DEPENDENCY_READY_OWNER_START_REQUIRED` | Initial field runtime must fail closed at the payment seam; accepted Payments runtime is required for final physical payment-handoff acceptance |

## Exact TECH.1 gate

TECH.1 counts as accepted and integrated only when all of the following are true:

1. its implementation was produced from a recorded authoritative Enterprise SHA under boundary version 2 and the recorded fingerprint;
2. the accepted diff is confined to the boundary's frontend/documentation paths and contains no backend or migration change;
3. focused frontend tests, ESLint, TypeScript production build, responsive/accessibility checks, authorization/route-guard checks, and device evidence pass;
4. one normal commit is present in `origin/customer-management-v1` and the technician application shell is visible in that tree;
5. the owner accepts TECH.1 completion and its active PHONE/TECH workspace no longer creates an unresolved path collision.

Provider/readiness commits `e3b4dfd57a674d09173674122257334719b41236` and `6c69530a22fc45bef91f6c24dfb50e4f6ca7cdb5` made TECH.1 safely dispatchable; they did not implement the technician frontend and do not satisfy this gate. The current phone revision-action commit `06ba3007940ff8d716bb5682d7760473a86ef0e6` is also control-plane work, not TECH.1 implementation evidence.

## Migration slot

Authoritative Enterprise has exactly one Alembic head: `w8m0i2k4n619`, the Invoice/AR revision descending from Accounting Core `w8m0i2e4f619`. Invoice therefore advanced the head; no Payment or AP runtime migration is authoritative at this snapshot.

TECH.FIELD.1 creates no migration now. At implementation Start it must fetch origin and set its isolated one-revision migration parent to the then-current sole Enterprise head. Immediately before integration it must fetch again. If Payment, AP, or another lane has integrated first, the field migration must be mechanically re-parented to that new sole head only when ancestry and table/domain ownership are disjoint; fresh upgrade, downgrade/re-upgrade, drift, affected regressions, and exactly-one-head checks must be rerun. Multiple heads, overlapping tables/contracts, destructive transforms, or ambiguous ancestry require serialized owner/integration review.

## Start trigger

TECH.FIELD.1 becomes startable when TECH.1 satisfies the five-part gate above, origin remains a single authoritative lineage, the accepted TECH.1 paths do not conflict with the field packet, and the owner separately authorizes TECH.FIELD.1. Payment runtime is not part of this Start trigger.

PHONE control is not a product dependency. A manual owner Start may be used as soon as TECH.1 is accepted and the capacity/worktree is explicitly safe; operational phone control is required only if the owner elects to Start from Mission Control on the phone. This readiness pass does not reassign capacity.

## Day-1 acceptance checklist

The following cases can be implemented and validated before Payments is authoritative:

- dispatcher assigns an eligible technician; unauthorized, inactive, cross-Company, and cross-Branch assignments fail closed;
- the assigned technician sees the correct local-day itinerary and minimum Customer, Service Location, appointment, Job, and exception context;
- acknowledgement, `en_route`, and `arrived` use authoritative Dispatch state and are idempotent;
- start requires the active assignment, arrival, permission, and current Job version;
- pause requires a controlled reason; resume and all lifecycle commands reject stale/reordered/duplicate mutations safely;
- required work notes and immutable requirement-snapshot evidence are append-only and auditable;
- completion is blocked without required evidence and customer approval or a controlled unavailable/refused disposition;
- both technician and generic Job completion paths invoke the same global field guard;
- completion produces correlated Job, audit, and Business Event evidence exactly once;
- the accepted Estimate and completed Job produce an idempotent Invoice handoff; retry/failure becomes visible reconciliation-required state;
- mobile refresh/reconnect preserves authoritative state, labels stale cached reads, and never reports unacknowledged local mutations as complete;
- physical iPhone Safari validates itinerary through Invoice handoff in separately authorized Preview.

The following final acceptance cases require accepted and integrated `PAY.1-3.ACCEL`:

- initiate the approved external-processor payment flow without ACP storing raw instruments;
- display authoritative receipt/application/failure/refund/deposit/clearing status;
- prove duplicate provider callback and client retry safety;
- reconcile invoice balance, unapplied receipt, deposit/clearing, and settlement evidence;
- complete the physical iPhone Invoice-to-Payment handoff and the full HCP-replacement closed loop.
