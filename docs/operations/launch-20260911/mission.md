ACP ENTERPRISE — CONTINUOUS OPERATING-RELEASE MISSION
Owner instruction, September 10–11, 2026

PURPOSE

Continue the approved 72-hour Launch & Operations plan. Do not replace it with
another roadmap or repeat completed milestones. Use the ten existing Codex
sessions: Enterprise plus three execution lanes on each physical computer.

The first checkpoint is 08:00 America/New_York, Friday September 11. It is a
reporting checkpoint, not a reason to stop useful work. This instruction permits
up to 72 hours of bounded continuation from activation, or until the approved
actionable work is complete, the owner revokes it, or a safety stop applies.
Record activation and expiry. This does not extend any technical credential or
previous delegation beyond its own expiry, and does not authorize more spending
or changes to account limits.

Success means deployed, tested operator workflows—not just commits or reports.

PART 0 — PUBLISH THIS MISSION ONCE

Enterprise: publish this complete instruction, including all ten lane sections,
without broadening it, at:
  docs/operations/launch-20260911/mission.md
on a dedicated coordination branch:
  work/launch-20260911-mission

Use an isolated worktree and preserve unrelated dirty state. If that branch or
path already exists, inspect and preserve history instead of overwriting it.
Push through the existing authorized Git path. This branch distributes the
owner's instructions; it is NOT the base for product implementation. All product
work starts from CURRENT origin/customer-management-v1 or reconciles a preserved
candidate onto that authority.

Return MISSION_PUBLISHED with the exact remote ref, commit and file digest.
Do not claim any other session started merely because this file was published.
Each of the other sessions receives one owner-issued native goal command.

PART 1 — REAL CONTINUATION, NOT A SINGLE-TASK PROMPT

Use the installed Codex native persistent-goal facility where available.
Verify the installed version/capability rather than assuming that the latest
online documentation matches every host. Preserve current permissions and
sandbox controls; do not enable unrestricted access to prevent prompts.

No new ACP scheduler, database queue, worker enrollment, delegation framework,
terminal injection, or cross-machine control-plane project is authorized by this
instruction. Preserve deferred headless-factory work unchanged.

A goal must cover the entire assigned operating outcome and its approved
successors—not merely “produce one commit.” After a component completes:
  check remaining acceptance → select next actionable item → implement/repair
  → qualify → push/handoff → verify deployed result → continue.

Do not stop for approval to test, commit, push, reconcile, or execute an already
approved successor. Do not mark the goal complete because a PR is open.

Keep a small durable lane checkpoint: task, exact base/head, remaining checks,
next action, known blockers, dependencies and last real progress. Preserve it
across context compaction. Do not store secrets or raw Customer/Payroll data.

Native goals are not proof of process survival or successful execution. Report
actual session/execution evidence and demonstrate progression from one finished
subtask to the next without another owner message. If a host lacks the native
facility, report that once and continue available product work in the session;
do not claim unattended continuation or start another factory rewrite.

Keep existing sessions and required runtimes alive. Check power/network/sleep,
current disk/memory health and available authentication once; do not perform a
new prolonged hardware capacity study. Avoid extra implementation processes
competing with these ten lanes. Never allow two writers in the same worktree.

PART 2 — COMMON EXECUTION / COLLABORATION RULES

At start recover actual work, current refs, dirty/index/interrupted Git state,
useful unmerged candidates and deployed versions. Most lanes reportedly finished
their previous tasks: integrate/reuse their results before assigning repeats.

Fetch before each new milestone. Record the base. Do not repeatedly restart
ongoing work because protected authority moves; requalify against the relevant
new authority before integration. Compare patch/content equivalence when squash
or cherry-pick history obscures ancestry.

Preserve OM2's historical dirty ACP worktree with interrupted cherry-pick and
conflicts. Preserve every other unrelated dirty workspace, Mobile runtime,
credential store and recovery artifact. No reset/clean/abort/stash of unrelated
work. New implementation uses an isolated worktree.

Use the existing Git/PR channel for handoffs, not the owner as a message relay.
Each lane owns its own status file/PR, not a shared frequently edited file.
Publish the owning lane, exact candidate, base, dependencies, tests, runtime
requirements and next action. Publish compact progress at material checkpoints;
while active, do not go more than 30 minutes without a safe status checkpoint.
Do not manufacture empty commits merely to show activity.

Enterprise checks available handoffs regularly, aiming for at most 10 minutes
between checks while candidates are flowing. Use supported waits rather than
tight model/API polling. If remote access is unavailable, report it truthfully.

Exactly one owner per shared implementation. Before changing shared API/schema
contracts, publish the narrow boundary. Receivers develop against verified
contracts or clearly labeled fixtures, never invented endpoint behavior.

Cross-lane fixes go to the owning lane with a reproducer. Enterprise may record
an explicit non-overlapping reassignment within the approved scope. Do not have
two lanes “helpfully” rewrite the same code.

A blocked dependency does not block unrelated tasks. Work on contract tests,
UI integration, recovery cases or the next approved successor. After repeated
identical failures, change the diagnosis, not just the retry count. After three
unchanged attempts, record the blocker and choose another actionable item.
Respect provider backoff and account limits; no endless resend/relogin loops.

When no actionable item remains, write the exact blocked/complete state and
pause safely. Do not burn tokens on repeated status reports or invent busywork.
Resume when a supported continuation mechanism sees the dependency change;
otherwise label the required resumption honestly. Do not claim a paused goal
will wake itself unless that behavior is actually supported and proven.

PART 3 — DECISIONS ALREADY AUTHORIZED

Choose small reversible implementation details independently using existing
product conventions: labels, layout, pagination, bounded recovery behavior,
validation messages, compatibility repairs and routine tests.

Use existing authenticated APIs/services/administrative tooling for already
approved Preview operations. Preserve permissions and audit attribution. A
broken UI does not justify fabricating an authorization context or editing role
rows directly. A missing credential remains missing; do not create fake identity.

Owner has reported POSTMARK APPROVED. Do not ask again for sending approval or
reinstall the working token merely because the last report showed ErrorCode 412.
Verify the actual runtime outcome and handle any remaining provider restriction
as a specific configuration finding.

The existing Lianne invitation may be retried through its audited outbox path
once validity and absence of prior acceptance are verified:
  invitation: 46c444ea-0200-4f56-91b8-337d061c88aa
  outbox: ef1be2f4-925e-477e-a453-b6470285b620
Preserve her actual recorded email, owner-selected role and MAIN Branch.
If expired, use the canonical same-employee reissue/revocation flow so only one
valid invitation remains. Do not recreate Lianne. Do not blindly resend an
uncertain or already accepted message. Employee/security mail only.

Do not choose roles, compensation, W-4 values, tax treatment, opening balances,
identity matches or consequential employment/pricing decisions as “small items.”

External prerequisites are checked early and reported once: actual QBO company
credentials/OAuth, expiring administrative access, physical device availability,
and distribution authority. Use valid existing sanctioned refresh mechanisms.
Do not fabricate credentials, relabel sandbox as real, or invent acceptance.
Complete every independent part while the blocked operation remains isolated.

PART 4 — FIXED LANE OWNERSHIP AND COMPLETION QUEUES

OM1-ENTERPRISE — INTEGRATION / PREVIEW / RELEASE

Own protected PR integration, shared contract arbitration, all live schema
migrations/deployments, and authorized Preview data writes. Other lanes provide
code, tests and execution packets; they do not independently mutate live Preview.
Coordinate with any already-running live operator before taking over. Never
interrupt a mutation blindly or duplicate its execution.

Queue:
1. Recover and integrate qualified completed candidates; identify what's
   already deployed, not merely merged.
2. Coordinate HCP admission, QBO read-only acquisition persistence and employee
   delivery without overlapping live mutations.
3. Deploy coherent increments while the other lanes continue.
4. Resolve integration defects and immediately return acceptance failures to
   their owners.
5. Keep a per-outcome readiness matrix with independent evidence from OM2-C.
6. Produce the morning operating handoff and Production decision packet.
7. Continue the approved residual 72-hour queue after the checkpoint.

Do not integrate your own changes without an available independent review
consistent with protected controls. Do not direct-push or force-update protected
history. If requirements truly mandate a human reviewer, retain that gate.

OM1-MIGRATION — ALL CUSTOMERS / HCP / CURRENT SCHEDULE DATA

Queue:
1. Recover latest classifier, operator runner and successor executor; finish
   missing wiring/regression only, not a new reconciliation model.
2. Run/prepare the canonical dry-run against actual Preview evidence with
   Enterprise owning live execution.
3. Prove exact successor reuse, safe creates and bounded holds, preserving
   parent graphs and Invoice/Payment native truth.
4. Provide the replayable admission packet; Enterprise executes only if the
   existing guards pass under the already-approved Preview admission scope.
5. Reconcile every source record to admitted/reused/held/rejected/source-exception
   outcomes. Resolve mechanically supported exceptions.
6. Publish usable Customer/Location/Job/Appointment projections for UI lanes.
7. Establish source currentness through September 11 using existing authorized
   read-only incremental acquisition. Do not freeze or mutate HCP.
8. Run August 28 historical comparison AND current open-work reconciliation.

Retain the canonical hybrid digest:
228f2e1b1f9050066cd8de5cddfceff6a62461864c0d6a90361040801132cbad
and its correct companion Customer control digest:
c5c81977116c9d4e296a8b4fa763a5029a94752ae00803d9a6c363d7e1ca711e
These are different evidence boundaries; do not compare a hybrid digest to an
arbitrary single archive hash or rewrite accepted authority to pass a guard.

Different namespaces do not prove different real-world entities. Match only
through supported source-ID transformations, provenance and corroborated graph
evidence. Absence from an incomplete source set does not prove unrelatedness.
No fuzzy auto-merges, blanket conflict waiver, or destructive Preview reset.

Success: real native records are accessible, totals reconcile, duplicates are
controlled and source as-of time is visible. A partial population remains partial.

OM1-ECO — REAL QBO ACQUISITION / BACKEND EVIDENCE

Preserve Economics work; this lane owns QBO backend acquisition tonight.

Queue:
1. Verify existing Intuit app/environment, authorized All County realm, credential
   presence and actual read access. Do not confuse sandbox with the real company.
2. Recover existing approved exports/control evidence and QBO adapters.
3. Complete source normalization, paginated acquisition, retry/checkpoint and
   refresh behavior within existing provider-neutral contracts.
4. Supply available accounts, Customer/Invoice/Payment/vendor/bill and report
   evidence to the existing ACP read models; coordinate API contracts with OM2-B.
5. Reconcile only compatible source dates and cash/accrual bases; preserve
   conflicts and prior versions, including known opening-control decisions.
6. Prove source provenance, completeness and actual refresh when credentials exist.
7. Continue accepted productive-hour/break-even input readiness from the original
   queue after QBO actionable work is complete.

No source payloads in Git. Missing values are not zero. QBO-source balances are
not posted ACP ledger balances. No automatic HCP/QBO identity merges or
application/settlement invention. No QBO writes or Accounting posting.
Without real credentials, complete the adapter/read-model work with preserved
labeled evidence and record LIVE_QBO_AUTHORIZATION_BLOCKED, not “live.”

OM1-PHONE — SIMPLE TEAM ONBOARDING / IDENTITY MAIL / LOGIN

Queue:
1. Finish the existing Lianne invitation delivery now that approval is reported.
   Coordinate the single actual retry with Enterprise; no competing consumers.
2. Prove outbox claim, Postmark response/message ID and truthful accepted-versus-
   delivered state. Repair actual failures, not hypothetical provider problems.
3. Verify the deployed activation/password page, one-time/expiry/replay behavior,
   and real activation status. Never set or solicit her reusable password.
4. Verify Team/Employees navigation and Add Employee simplicity: name, email,
   standard role, MAIN default and Send Invite; correct actionable status/errors.
5. Preserve Owner/Manager/Admin/CSR/Technician bundles and required owner
   verification. Do not auto-verify a real employee where owner policy requires it.
6. Qualify revocation, safe reissue, existing-user collisions, and authorization
   refresh using isolated sanctioned fixtures.
7. Hand Laptop1 Phone a safe identity/client contract; no activation secrets in
   task reports. Continue existing identity/security recovery UX.

Real messages only to already owner-selected recipients for approved identity
purposes. Provider delivery evidence is not proof a human opened the message.
If Lianne is absent, continue fixture acceptance and label real activation pending.

OM2-A — JOB CLOCKS / JOBSITE HOURS / TIMECARD BACKEND

Queue:
1. Reconcile completed Jobsite Hours/timecard/exception work into current authority.
2. Prove assigned Employee/Job/Appointment clock-on, visible active clock, clock-off
   and committed interval through existing audited services.
3. Repair duplicate tap, lost response, retry, overlap, multi-technician and
   authorization/revocation cases. Reconcile before retrying ambiguous writes.
4. Prove office/mobile agree after refresh/reconnect and that corrections preserve
   original time plus the reviewer/reason.
5. Prove Job labor, Timecard and payroll-period calculations consume the same
   accepted intervals and invalidate stale approval/calculation state correctly.
6. Continue approved Job labor actuals and time-evidence quality work.

No scheduled-time substitution. Do not lose valid worked-time evidence because
it is unpaid/unclassified; preserve its actual classification. No fabricated
payable punches on real employees. Live write tests use Enterprise-sanctioned
clearly segregated fixtures. Coordinate with Laptop1 Phone, not another client.

OM2-B — QBO / ACCOUNTING / PAYROLL OPERATING UI

Queue:
1. Pair with OM1 ECO on verified QBO read-model/API contracts.
2. Make available source records navigable from existing ACP financial screens:
   accounts, balances, invoices/AR, bills/AP, payments and reports as supported.
3. Show real company, source basis/date, last refresh, completeness and conflicts.
4. Prevent HCP/QBO double counting and distinguish source evidence from native
   posted accounting. No cosmetic fabricated totals.
5. Prove filters, drill-down, error/recovery and empty/partial states in deployed UI.
6. Finish existing Payroll-period/Timecard office operation and register review.
7. Verify payroll calculations against independent cases and authoritative current
   IRS/jurisdiction rules, effective-dated compensation/elections and prior/YTD
   inputs. Do not infer overtime exemptions from a supervisor title.
8. Preserve the weekly Excel workaround; it is not independent proof that ACP's
   tax calculations or employee inputs are correct.

Missing QBO credentials or payroll elections block those real-data claims only.
Continue fixtures, screens and tests. No payments, postings, tax filings or wages
transmitted. No “live QBO” label without an actual real-company acquisition.

OM2-C — INDEPENDENT END-TO-END ACCEPTANCE

Queue:
1. Reuse existing authenticated harnesses; no second test framework.
2. Prepare and run CSR → Customer → Location → Job → Appointment → Month/Dispatch
   tests, plus role/tenant/Branch denial cases.
3. Verify every appointment in crowded days is reachable and correct after refresh.
4. Verify population accounting and evidence-backed QBO views with source dates.
5. Verify employee onboarding/activation with fixtures and actual evidence where
   available; then Job clock → office Timecard → payroll-period composition.
6. Reproduce failures and assign repairs to implementation owners. Do not compete
   with them for the same code; repair only your acceptance harness by default.
7. Re-run on each relevant coherent deployed checkpoint and audit the final release.
8. Publish reproducible operator steps, screenshots/recordings where available,
   exact release, results and remaining gates for Enterprise.

A 200 response is not visual acceptance. Simulator/browser tests are not physical
phone tests. Do not certify production readiness, data currentness or actual pay
correctness without the specific required evidence.

LAPTOP1-A — CSR / MONTH CALENDAR / SCHEDULE / DISPATCH UI

Queue:
1. Recover completed calendar work and reproduce any actual remaining defects.
2. Make crowded-day +N more open all appointments in a usable drill-down.
3. Prove previous/next month, Today, week boundaries, local dates, timezone/DST,
   filters, canceled/historical status and multi-technician display.
4. Prove Customer/Location search → Job/Appointment booking → technician/window
   selection → human-confirmed save → refresh and persisted state.
5. Prove Day, Week, Work Week, Month, Unassigned and horizontal Dispatch represent
   ONE authoritative schedule. Empty space does not certify availability.
6. Preserve non-mutating recommendations, Why?, risks and ghost proposals.
7. Test desktop office usability, keyboard use, phone layout, overflow and safe
   errors; repair defects in the actual rendered routes.
8. Continue existing CSR/dispatch operating quality work, not speculative visuals.

Own Scheduling UI, not Customer roster or timekeeping backend. Publish any
backend blocker to its owner. No autonomous changes to actual Customer jobs;
mutating acceptance uses authorized fixtures coordinated with Enterprise.

LAPTOP1-B — ALL CUSTOMERS / LOCATIONS / OFFICE NAVIGATION

Queue:
1. Recover existing Customer UI and pending work without repeating implementation.
2. Prove source-backed roster completeness, pagination and search by supported
   name/phone/address fields; prevent silent truncation.
3. Prove Customer detail, multiple Locations/contacts, history and related Jobs,
   appointments, estimates/invoices where authoritative evidence exists.
4. Show source-only/held/ambiguous data distinctly; do not expose it as native
   accepted truth or create duplicate Customers to fill the screen.
5. Pair with Laptop1-A for clean CSR booking navigation and context preservation.
6. Verify permissions and safe errors in actual deployed pages.
7. Continue approved Customer/history/operating UX regressions; take other
   original-queue UI work only after an explicit Enterprise ownership handoff.

No migration identity decisions or backend financial calculations in this lane.
No real Customer messages. No edits to another lane's exception/Payroll files.

LAPTOP1-PHONE — ACP EMPLOYEE CLIENT / DEPLOY READINESS

Queue:
1. Recover existing Mobile project/build/Metro/device state and actual API target.
2. Prove login, session persistence, Employee identity, My Day, assigned Job detail,
   clock-on/off, current-clock visibility and persisted time.
3. Prove duplicate taps, response loss, app background/foreground, network loss,
   retry and stale/revoked authorization do not duplicate or misattribute time.
4. Pair with OM2-A and OM2-C on phone → server → office → Timecard consistency.
5. Use the actual physical device when accessible. Otherwise run simulator/client
   tests and preserve a minimal real-device handoff; do not invent acceptance.
6. Produce a reproducible build/deploy readiness packet using the existing project.
   Separate simulator, development device, signed distributable and fleet access.
7. Check whether an existing authenticated employee-browser route can serve as an
   explicitly labeled interim option. Do not build a new client or silently
   substitute it for the requested native app.
8. Continue bounded existing dependency/reconnect/usability work after core flow.

Keep signing identities and project intact. Do not install Xcode on OM1. No new
Apple signing, TestFlight upload or App Store action under this instruction.

PART 5 — DEPLOYMENT AND TEST SAFETY

Enterprise alone owns live Preview changes under existing authorized scope.
All other lanes prepare verified operations packets and support execution.

For every coherent checkpoint:
- exact protected release and compatible component versions;
- verified backup and rollback consistent with new schema;
- isolated restored-database upgrade plus appropriate fresh-database tests;
- one migration writer, one Alembic head, current=head, no unexpected drift;
- service-scoped application deployment, no database/cache recreation;
- health, authentication, authorization and rendered-route acceptance;
- exact source population/as-of and surviving historical references.

Never run automated destructive tests against Preview. Never start two
PostgreSQL servers against one data directory. Preserve corrupted evidence,
restored volumes, old release/secret boundaries and incident backups.
Never rollback to public infrastructure ports or anonymous Redis.

Keep public 5432/6379/8000 closed; no public Docker infrastructure publication;
Redis authenticated, default user off, protected-mode on. Preserve SSH's
108.190.80.97/32 restriction and intended TCP 80/443 exposure. Do not reopen
ports or copy database credentials to engineering hosts to solve a test problem.

Qualification is proportionate, not absent: focused/domain tests plus changed
security/data-integrity/schema boundaries. Record reproduced pre-existing
failures; do not call a failed suite passed or weaken real assertions.

PART 6 — HARD STOPS AND PERMISSION TO KEEP OTHER WORK MOVING

No Production deployment/cutover, HCP/QBO record mutation, source freeze,
Accounting posting, money movement, payroll/tax submission, general Customer
communications, automatic pricing activation, autonomous Dispatch, consequential
employment action, or Apple signing/TestFlight without separate explicit consent.

No destructive replacement/restore, invented credentials, permission bypass,
fabricated employee/financial facts or weakened source guards.

Pause affected live mutation for a P0/security/data-integrity event; preserve
state and report. Unaffected isolated work may continue where safe.

Postmark approval does not authorize blanket resend or all Customer mail.
QBO developer Production credentials do not authorize ACP Production deployment.
A ready build does not imply employee distribution or real-device acceptance.

PART 7 — COMPLETION EVIDENCE AND MORNING HANDOFF

Track separately:
IMPLEMENTED / QUALIFIED / PROTECTED-INTEGRATED / PREVIEW-DEPLOYED /
DEPLOYED-ACCEPTANCE-PASSED / HUMAN-ACCEPTANCE-PENDING / EXTERNAL-GATE.

Do not close an operating outcome at commit time. Push a ready handoff, continue
independent work, and return after deployment for verification.

Enterprise's morning handoff must contain:
- exact working URLs/navigation, not guessed labels;
- selected/deployed release and schema;
- CSR booking plus Month overflow/drill-down evidence;
- Customer population/source-date reconciliation;
- QBO real-company connection and visible-evidence result, or exact auth gate;
- employee invitation provider status, activation/login evidence separately;
- phone build/client/physical/distribution results separately;
- Job clocks, office Timecards and Payroll readiness with missing inputs explicit;
- backups, rollback, limitations and exact proposed Production scope;
- GO/NO-GO for the requested scope without lowering it to manufacture GO.

Publish the 08:00 checkpoint even if incomplete, then continue actionable work
within the authorization window. Do not wait for an owner reply to resume
routine approved development.

Stop when all actionable assigned/handed-off goals have qualified and deployed
acceptance, no owned repair remains, and remaining human/external gates are
precisely documented; or at revocation/expiry/safety/usage limit. Do not keep ten
sessions spinning on a completed or wholly externally blocked queue.

Before the owner leaves, show each lane's actual goal/session, worktree, task,
last meaningful action and continuation status. Distinguish WORKING, WAITING,
BLOCKED, COMPLETED and UNVERIFIED. A prompt or heartbeat alone is not activity.

END MISSION
