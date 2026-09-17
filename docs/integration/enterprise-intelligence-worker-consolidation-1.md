# ENTERPRISE.INTELLIGENCE.WORKER.CONSOLIDATION.1

## Current authority

- Protected remote: `origin/customer-management-v1`
- Current protected SHA: `541fe77e690993996acf7f0f66139edd7cbf8578`
- Previous remote Intelligence head: `7929bf03a622967c12e9a83feb1a5612492c74ac`

## Worker dispositions

| Worker | Candidate SHA | Base | Disposition |
| --- | --- | --- | --- |
| Laptop-A LIA/Beacon | `82ab4dbd581165404b58db6d2766b2885c80c6c1` | `a65a104c21282fd8f94a2e9bac37ba576a91a75c` | Qualified and integrated. Its first Beacon commit was patch-identical to the previous Intelligence checkpoint and was not duplicated; its LIA/Beacon history extension was applied after rebasing current authority. |
| Laptop-B Luminary/Economics | `14c9ca49ea8545298769df38cb3459682198e70c` | `541fe77e690993996acf7f0f66139edd7cbf8578` | Qualified and integrated. Adds prior-period/trend presentation, freshness/authority facts, and evidence-priority presentation without new authority or mutation. |
| Phone/C Mobile LIA | `41300801dbf94fb588c6dcb18cc458bbae74b32c` | `a65a104c21282fd8f94a2e9bac37ba576a91a75c` | Documentation-only, blocked/reconciliation required. It defines an employee-safe server contract; no Mobile source or API implementation was present or absorbed. |

## Integration and overlap

1. Rebased the prior isolated Intelligence branch onto current protected batch 10.
2. Preserved the patch-equivalent Beacon history implementation already on the branch.
3. Applied Laptop-A's LIA-to-bounded-Beacon-history extension.
4. Applied Laptop-B's Luminary presentation extension.
5. Added Phone/C's contract handoff as documentation only.

No OM2 operational implementation, duplicate API, competing intelligence
authority, or source-domain mutation was introduced. No cross-machine conflict
required escalation.

## Qualification

- Fresh ephemeral PostgreSQL migration to head: passed.
- Backend LIA, Beacon, Luminary, owner Economics, authorization, provenance,
  and incomplete-state suites: `353 passed`.
- Affected frontend tests: `16 passed`.
- Frontend ESLint: passed.
- Frontend TypeScript compilation and Vite production build: passed.
- Changed Python module compilation and `git diff --check`: passed.
- Mobile tests: not run; no Mobile source changed, only a contract handoff was
  added.
- No migration files changed; canonical Alembic/release ownership remains OM1.

## Real-data and release gates

- Preview health is reachable, but its reported release must be checked against
  this consolidated head before acceptance.
- Authenticated All County owner acceptance remains pending for LIA, Beacon,
  Luminary, Economics, and any Mobile contract consumer.
- Acceptance must use actual Company/Branch scope, real Customer/Job evidence,
  Beacon history, admitted Economics results, and source/as-of limitations.
- OM1 owns final protected integration, schema reline, Preview/Production
  deployment, and release authorization.

## Batch 2 addendum

- Current protected SHA observed before Batch 2 reconciliation:
  `d5148f60ba842f9b4e7c9e83f16d1d3301372491`.
- Laptop-A Batch 2 candidate:
  `origin/work/lia-beacon-owner-intelligence-2` at
  `82ab4dbd581165404b58db6d2766b2885c80c6c1`. Its prior Beacon-history
  commit was already present in protected ancestry; only the new LIA-to-bounded
  Beacon-history composition was retained.
- Laptop-B Batch 2 candidate:
  `origin/work/luminary-economics-presentation-2` at
  `14c9ca49ea8545298769df38cb3459682198e70c`, based directly on the then-current
  protected SHA. Integrated with no migration.
- Phone/C Batch 2 candidate:
  `origin/work/laptop1-phone-lia-mobile-interaction-1` at
  `41300801dbf94fb588c6dcb18cc458bbae74b32c`. Documentation-only server
  contract; Mobile implementation remains blocked until the employee-safe route
  exists.
- Protected authority had already absorbed the previous Intelligence checkpoint;
  rebase preserved that work and a non-force merge reconciled the remote branch
  history.
- Final consolidated branch head is recorded in the release handoff; it is a
  protected ancestor and has zero remote integration divergence.

## Currentness reconciliation addendum

- A fresh `git fetch origin --prune` observed protected authority at
  `origin/customer-management-v1` SHA
  `5f7a45118885a38e5faa4fcfcf98dd395d3ea7ea`.
- The protected history now contains the qualified Laptop-A and Laptop-B
  Batch 2 source patches (`82ab4dbd...` and `14c9ca49...`) through their
  reconciled implementations. Rebase therefore classified those source
  candidates as already contained/current; no duplicate implementation was
  retained.
- The Phone/C candidate `41300801dbf94fb588c6dcb18cc458bbae74b32c` remains a
  documentation-only employee-safe contract handoff. It is retained on this
  integration branch for OM1/Phone coordination, but is not end-to-end
  qualified because the server route and Mobile client are not present.
- Reconciliation restored protected ancestry. The isolated branch is currently
  9 commits ahead of protected and 0 commits behind; its remote counterpart
  still requires a non-fast-forward history reconciliation before publication.
- The protected Batch 12 platform-boundary changes introduced no Intelligence
  migration requirement. OM1 retains canonical schema, final protected
  integration, Preview, and Production authority.

## Cosmic Batch 2 cycle

- Fresh inventory observed protected SHA
  `5f7a45118885a38e5faa4fcfcf98dd395d3ea7ea` and cumulative Intelligence SHA
  `05f10528804ebe665a82b93b2351dd63a51cc854` before this cycle.
- Laptop-A candidate `origin/work/lia-employee-safe-server-1` at
  `e17af6f09d1197a485b8e0515ce4f8e58d840b1e`, based directly on protected,
  was integrated first. It adds the explicit employee-safe LIA authority,
  Company/Branch/Employee scope enforcement, launch gating, and authorization
  tests. No migration changed.
- Laptop-B candidate `origin/work/luminary-economics-delta-explanation-1` at
  `81a52e5ad9124bc22501f30725b221517e9c7d0e`, based on protected through its
  reconciled parent, was integrated second. It adds deterministic comparable-
  period decomposition, fact/derived/finding separation, provenance,
  freshness, and incomplete-state presentation. No migration changed.
- Phone/C candidate `origin/work/laptop1-phone-lia-mobile-interaction-1` at
  `41300801dbf94fb588c6dcb18cc458bbae74b32c` remains already integrated as a
  documentation-only contract handoff. No Mobile client implementation was
  published in the current inventory.
- No worker overlap required a semantic conflict resolution. The employee-safe
  server contract precedes any future Mobile client qualification.
- Combined qualification: empty PostgreSQL migration to head passed; backend
  Intelligence suites `373 passed, 3 warnings`; affected frontend tests `16
  passed`; ESLint, TypeScript/Vite build, Python compilation, and diff checks
  passed. Mobile tests are not applicable to this source set.
- Real All County acceptance remains pending in Preview. No Preview or
  Production deployment occurred.

## Final Cosmic currentness reconciliation

- Protected authority advanced during qualification to
  `752f87a73dc1414dac7156f702de5c5230149cf3` via the Price Book admission
  hotfix. The isolated branch was rebased onto that authority; no protected
  branch was modified.
- The final cumulative worker content remains preserved after reconciliation:
  LIA connected intelligence and employee-safe authority, Analytics evidence
  integrity, Luminary delta/evidence presentation, Beacon history semantics,
  reporting qualification, and Mobile authoritative date/beta contract work.
- Current employee-safe route truth is `POST /api/v1/lia/employee/ask`, guarded
  by `COMPANY_EMPLOYEE_OPERATIONS_OWN_LIA_READ`; it is tenant- and
  assignment-scoped, default-deny, and cannot fall back to owner LIA APIs.
- Current Mobile beta migration status is `PREPARED_NOT_SWITCHED`; Preview is
  the selectable environment, `beta.twelve-hats.com` is not selectable until
  its gates pass, and Production remains inactive.
- Final qualification after this cycle: backend `382 passed` with 3 existing
  warnings and fresh PostgreSQL migration-to-head; frontend affected tests
  `28 passed` with lint and production build; Mobile `139 passed`, typecheck,
  lint, config validation, and iOS/Android Expo exports passed. The unsigned
  Xcode Simulator Release build was attempted but requires missing generated
  CocoaPods `Pods-ACPEmployee.release.xcconfig`.

- Final fetch after reconciliation observed protected authority at
  `2777f1bbb1fe3aa5145d4b4bd9a8bc7759073706`; the intervening Price Book
  presentation-only OM2 change was incorporated as protected ancestry and did
  not alter Intelligence source contracts.

## Continuous Maximum 2 cycle

- Fresh protected authority was `388226f21d43c055934a87f26a92f3cad0b0e901`.
  The cumulative branch was reconciled from `02ab21c4...` onto this current
  authority before worker consumption. Subsequent protected changes during
  reconciliation were OM2/OM1 platform changes outside Intelligence ownership.
- Laptop-A `work/lia-connected-intelligence-maximum-1` remains at
  `cccfc26991f5c94f2f8f4edcd35d081168118c78` and is already represented in the
  cumulative Intelligence content; no duplicate replay occurred.
- Laptop-B advanced to `work/cosmic-intelligence-realdata-maximum-1` at
  `825eb42f89071aad47366a04d5bae6945668a9dc`. Patch identity classified its
  earlier Analytics/Beacon/reporting commits as equivalent to existing lane
  work. New presentation-state hardening, unavailable-evidence handling, and
  unsupported Economics-scope rejection were integrated. Its overlapping
  older Luminary UI patch was not replayed because it regressed the qualified
  delta explanation; compatible currency/period safeguards remain present.
- Phone/C advanced to `work/cosmic-mobile-employee-beta-maximum-1` at
  `298ba14f87674ed463772de960c70a57ddefe5b0`. The two new malformed-time
  commits were integrated after the prior endpoint/date contract. The beta
  endpoint remains prepared-but-not-switched and Production remains
  fail-closed.
- No migration files changed. Broad qualification after integration: backend
  `382 passed` with 3 existing warnings; frontend affected Intelligence and
  reporting routes `30 passed`, lint, TypeScript, and Vite build passed;
  Mobile `139 passed`, typecheck, lint, config validation, and iOS/Android
  Expo exports passed. Unsigned Xcode simulator Release remains blocked by
  missing generated CocoaPods `Pods-ACPEmployee.release.xcconfig`.

## Maximum 2 currentness refresh

- Protected authority advanced through OM2/OM1 operational integrations to
  `9dbdea7933a69ea8b147a63ed6cc6437d5401825`. The Intelligence branch was
  rebased onto it and its prior qualified content preserved. No protected
  branch or operational source-domain implementation was modified.
- Current worker heads: Laptop-A `cccfc26991f5c94f2f8f4edcd35d081168118c78`;
  Laptop-B `825eb42f89071aad47366a04d5bae6945668a9dc`; Phone/C
  `298ba14f87674ed463772de960c70a57ddefe5b0`. A remains contained; B’s
  duplicate cumulative patches were skipped by patch identity while new
  presentation protections were retained; Phone/C’s malformed-time patches
  were retained.
- The final subsequent protected refresh was
  `e4947b66f5ef3bb6f6e095fd42d29ce14fa650d2` before the latest OM2 scheduling
  and dispatch authority, with no Intelligence file overlap. Final fetch
  currentness is recorded in the release handoff.

## ABC consolidation maximum 1 (current remote sweep)

- Current protected authority at sweep: `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`.
  Prior Intelligence `fd4cb2d061281811fba8c531507d1d661a453c59` was rebased
  onto it; protected history was not modified.
- Laptop-A `work/lia-connected-assistant-night-shift-1` at
  `092c2d34fe57b899b1104139d74b2f3d414b1432`: first cumulative patch already
  contained; four later connected-LIA/voice/acceptance patches consumed. No
  migrations.
- Laptop-B `work/cosmic-intelligence-realdata-maximum-1` at
  `917d87eafac141cc15b1c165f29e64f221bffa54`: cumulative Analytics,
  Beacon/reporting, and unsupported-scope patches already contained; the
  overlapping Luminary UI patch was skipped to preserve the current period-
  delta model; later presentation-state content consumed. No migrations.
  Analytics still lacks an authoritative currency source contract and does not
  assume USD.
- Phone/C `work/laptop1-phone-lia-client-maximum-1` at
  `90aa2c9b750051c8ab08f3f6eb41d4145843ce7b`: three date/beta patches already
  contained; actual permission-gated employee LIA client consumed. No
  migrations. It uses only the employee-safe route and remains fail-safe until
  released/deployed authority exists.
- Integration order: A, compatible B presentation-state content, then C.
  Existing canonical Luminary finding IDs and evidence result IDs already
  provide scope/period/provenance identity; no new contextual-link migration
  was warranted. Existing authorization/not-found behavior fails closed for
  absent, stale, or unauthorized identities.
- Employee-safe truth remains `POST /api/v1/lia/employee/ask`, guarded by
  `COMPANY_EMPLOYEE_OPERATIONS_OWN_LIA_READ`, with tenant, membership,
  eligibility, assignment, default-deny, and protected-field enforcement; no
  owner-route fallback. Mobile now consumes that contract.
- Qualification: backend `386 passed, 3 warnings`, disposable PostgreSQL
  migration-to-head passed with one Alembic head `o1q9s27h4u0v`; frontend 43
  affected tests, ESLint, TypeScript, and Vite build passed; Mobile 16 suites /
  143 tests, typecheck, lint, config validation, and iOS/Android exports
  passed. Xcode Release remains blocked by missing generated
  `Pods-ACPEmployee.release.xcconfig`. Python compilation and diff-check passed;
  host Ruff, MyPy, and Alembic were unavailable.
- Real All County acceptance remains pending: no deployment occurred,
  authenticated owner/employee execution was not observable, and no business
  data was mutated. Source-domain handoffs remain Scheduling/Dispatch,
  Price Book, Revenue Cycle, Timekeeping, Customer/Job historical identity,
  and Analytics currency contracts.

## LIA spoken presence consolidation

- Current protected authority: `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`.
  Prior Intelligence head: `1a72c9a7b181cdd63557f44a9abc5a18294fed94`.
- Laptop-A `work/lia-spoken-presence-maximum-1` at
  `13d2094b7618a125d44b36dc31e1f33b5d48c79b` was genuinely new and integrated
  as implementation authority. It adds additive `response_mode`, deterministic
  evidence-safe spoken rendering, response-depth budgets, safe next-action
  handling, local platform voice preference, `0.94` rate, and neutral pitch.
  Visual answers/evidence and factual/provenance/authorization boundaries stay
  unchanged. No migrations.
- Laptop-B `work/lia-delivery-style-profile-1` at
  `8bd90a9d0a954247497c372e2ca52c48dfb1494a` was genuinely new documentation
  and integrated as design/evaluation authority. Its 150–170 WPM and warm,
  calm, professional profile are targets only. `REFERENCE_MEASUREMENT_PENDING`
  remains explicit; no unavailable reference audio was represented as measured.
- Corrected B’s stale implementation-rate wording from `1` to the tested A
  default `0.94`. The advisory `0.96` option does not override it. No provider,
  credentials, voice clone, or external TTS integration was added.
- Mobile response validation now accepts additive `response_mode` with a
  `NORMAL` default; no separate Mobile intelligence or native speech engine
  was introduced. Existing employee-safe endpoint, permission, conversation,
  provenance, and fail-safe behavior remain intact. Native speech remains a
  future Phone-owned follow-up.
- Qualification: frontend spoken/LIA tests `32 passed`, ESLint, TypeScript,
  and Vite build passed; Mobile LIA tests `4 passed`, typecheck, lint, and
  config validation passed; Python compilation and diff-check passed. Host
  Ruff/MyPy were unavailable. No schema changes.
- Preview acceptance remains pending; no Preview/Production deployment,
  external provider selection, credentials, reference recording, or business
  data mutation occurred.

## Continuous Intelligence shift sweep

- Fresh remote sweep confirmed protected authority
  `b527d75eecb2d271a29bcb0bacb9e1b16b33784b` and synchronized Intelligence
  authority `f73002dbdceb673cefb9a573d6e98f6c3b9391a5` before this evidence
  update. No new A/B/Phone implementation checkpoint was published.
- Existing LIA, Beacon, Luminary, Economics, Analytics, and Mobile candidate
  branches remain already integrated or patch-equivalent. Payroll candidates
  remain Operations-owned and were not inspected as implementation inputs.
- Protected Operations review covered current Price Book maintenance,
  immutable Estimate conversion lineage, Dispatch/Scheduling, Workforce, and
  Timekeeping route/permission contracts. Intelligence consumers retain
  explicit source evidence, period/as-of, incomplete, and authorization
  boundaries; no stale route, schema mismatch, broken drill-down, or
  integration-owned acceptance defect was demonstrated.
- `origin/work/economics-pricebook-feedback-readiness-1` at
  `e0fab90408b320027b67b57150575f64aef68f97` remains outside this checkpoint:
  it adds post-production Price Book feedback readiness and depends on deeper
  source-domain review. It was not integrated merely to create work.
- No code change was warranted. This shift records evidence only; Preview and
  Production were not deployed, and real business records were not changed.

## Final A/B reconciliation (current)

- Protected authority remained `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`.
  Previous Intelligence head was `815a1d1c16c54fd15f6243a45b4a9e751c65a4c8`.
- Laptop-A `work/lia-connected-quality-shift-2` current head
  `a86ecf262f6ae1b1ef7dd565fb2c811cabb18053` was `PARTIALLY_CONTAINED`:
  earlier cumulative patches were patch-equivalent, while ten later commits
  were genuinely new and integrated. These add exact commercial retrieval,
  scoped Employee/Dispatch evidence, numeric/financial safety, Beacon
  explanation/evidence/navigation, and Luminary/Economics context navigation.
  No migrations.
- Laptop-B `work/cosmic-intelligence-realdata-maximum-1` current head
  `fba5cb00cf8dde559ca8eb6a417572d036dbd57a` was `PARTIALLY_CONTAINED`:
  duplicate Analytics/Beacon history and the overlapping Luminary evidence
  patch were skipped; eight genuinely new reporting, empty-state, trend,
  currency, and Command Center truth patches were integrated. No migrations.
- Phone/C `work/laptop1-phone-lia-client-maximum-1` remains
  `90aa2c9b750051c8ab08f3f6eb41d4145843ce7b`; all four patches are already
  patch-equivalent and were not replayed.
- Final qualification: backend Intelligence/source suites `652 passed, 3
  warnings`; PostgreSQL zero-to-head passed with one Alembic head
  `o1q9s27h4u0v`; frontend `138 files / 564 tests passed`, with ESLint,
  TypeScript, Vite, Python compilation, and diff-check passing. Mobile `16
  suites / 143 tests`, typecheck, lint, config validation, and iOS/Android
  exports passed. Ruff and MyPy were unavailable on host; Xcode Release remains
  blocked by missing generated CocoaPods configuration.
- The full frontend run reproduced an asynchronous Estimates source-domain
  defect at `frontend/src/routes/EstimatesRoute.tsx:354`: missing
  `current_revision` is dereferenced for `proposal_title`. Retrieval itself is
  not an Intelligence defect; Estimates owns the fix and should guard the
  optional current revision or repair its contract/fixture.
- A’s context navigation partially resolves the prior Luminary/Economics gap:
  surface context reaches LIA, but exact finding/result drill-back still needs
  owning-domain opaque identifiers. Intelligence did not invent them.
- Price Book exact retrieval is integrated; Branch-safe current-price authority
  remains source-owned. Estimate retrieval is integrated; proposal-title
  exception remains an Estimates handoff. Revenue Cycle monetary aggregates,
  settlement/cash/as-of, Timekeeping period hours, richer Dispatch ordered
  references, and Analytics authoritative currency remain source contracts.

## Spoken presence current-authority reconciliation

- Protected authority advanced during handoff from `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`
  to `be7d1e9bf928301d1a14274b7fae295935fb0b89`. The isolated Intelligence
  branch was rebased onto the new authority and the prior remote Intelligence
  history was merged without force-push; protected ancestry is restored.
- A `13d2094b7618a125d44b36dc31e1f33b5d48c79b` and B
  `8bd90a9d0a954247497c372e2ca52c48dfb1494a` remain integrated. The tested
  implementation is platform-local speech at rate `0.94`, neutral pitch, and
  deterministic evidence-safe rendering. Delivery-style targets and reference
  measurement remain non-authoritative design/evaluation material.
- Mobile accepts additive `response_mode` with a backward-safe `NORMAL`
  default. Native speech is not duplicated in this lane; Phone follow-up may
  consume the shared field when separately implemented.

## Native Mobile speech consolidation

- Phone/C `work/laptop1-phone-lia-client-maximum-1` at
  `2f21a562fda94c38d85c85dba2ba86311f93ff75` was genuinely new after the
  existing four Mobile commits and was integrated. It adds `expo-speech`
  `57.0.3`, Speak/Stop/replay, unmount and new-question cancellation, and
  native local-device playback of the server-composed answer only. No owner
  endpoint fallback, cache, provider, or credential was added.
- Browser and Mobile share the same nominal delivery values: en-US, rate
  `0.94`, pitch `1`, volume `1`, and response mode. Numeric rates are adapter
  parameters, not an acoustic identity or absolute WPM guarantee. Browser
  semantic shaping remains deterministic; Mobile does not create a second
  planner, fact, authority, or evidence path.
- Browser qualification: 55 focused spoken/evaluation tests, ESLint,
  TypeScript, and Vite build passed. Mobile qualification: 16 suites / 145
  tests, typecheck, lint, config validation, iOS/Android Expo exports passed.
  The local unsigned Xcode Release build remains unavailable because generated
  `Pods-ACPEmployee.release.xcconfig` is absent, despite the worker’s reported
  CocoaPods/simulator qualification. No migrations; Python compilation,
  diff-check, and secret scan passed.
- Pronunciation governance: A’s built-in ACP/LIA/QBO/HVAC normalization remains
  deterministic and tested; B’s ACP/LIA/QBO/HVAC/SKU entries remain
  `PROPOSED`; arbitrary names are never guessed. Provider remains `NONE` and
  `REFERENCE_MEASUREMENT_PENDING` remains true.

## Native speech final currentness

- Protected authority advanced to `be79bd2586873d91c50c2d94ceeaf21643e4fd3e`
  during consolidation. The Intelligence branch was rebased onto it, with
  prior spoken-presence, A/B, and Mobile history preserved; the stale remote
  Intelligence history was merged normally and no force-push was used.
- A `6c3f89daba3c209fe2ef323c62648c8383428f22`, B
  `029d7fcb25477a8a1a145df07410dbdf865ed08f`, and C
  `2f21a562fda94c38d85c85dba2ba86311f93ff75` are integrated. The Mobile
  `response_mode` overlap was reconciled to one backward-safe schema field.
- Focused browser spoken/evaluation qualification: 55 tests passed, ESLint,
  TypeScript, and Vite passed. Mobile: 16 suites / 145 tests passed,
  typecheck, lint, config validation, and iOS/Android exports passed. Backend
  Intelligence suites: 653 passed with 3 warnings and one Alembic head
  `o1q9s27h4u0v`. Local Xcode Release remains blocked by missing generated
  CocoaPods `Pods-ACPEmployee.release.xcconfig`; worker-reported simulator
  qualification remains recorded separately.

## Maximum shift currentness (2026-09-17)

- A and B published no new heads beyond `6c3f89daba3c209fe2ef323c62648c8383428f22`
  and `029d7fcb25477a8a1a145df07410dbdf865ed08f`; both remain integrated and
  qualified. The Phone branch advanced to `72ed521e09dd32e315c081c71024a6f6c4353f0b`.
- The Phone advance was a bounded two-file safety patch, integrated as
  `76df7083197787fc39d5a162ef8572946fae9fbe`: native speech failures now leave
  the authorized answer visible and report playback unavailability. No owner
  route fallback or authorization change was introduced.
- Current protected authority is
  `be79bd2586873d91c50c2d94ceeaf21643e4fd3e`; the cumulative branch is
  protected-derived, `0` behind and `1146` ahead before the final local commits.
- Audit found an Intelligence-owned Analytics presentation defect: the revenue
  trend chart labeled amounts as USD although the Analytics source contract has
  no authoritative currency. The chart now presents numeric amounts and labels
  currency as unavailable; no source contract or calculation was invented.
- Post-fix frontend qualification: 57 focused tests, ESLint, TypeScript, and
  Vite passed. Mobile qualification: 16 suites / 146 tests, typecheck, lint,
  config validation, and iOS/Android exports passed. Preview/Production were
  not deployed and real-data acceptance remains pending.

## LIA Voice Sovereignty consolidation (2026-09-17)

- Current protected authority advanced from `be79bd2586873d91c50c2d94ceeaf21643e4fd3e`
  to `44587182a328d3b56cd73568b5bbd9b8b1231cdd`. A normal protected merge
  restored ancestry; no protected ref was modified and no force-push occurred.
- Laptop-A `work/lia-spoken-presence-maximum-1-successor` at
  `9c0754d2f0941071f9078fe7ce48db7e93247913` was genuinely new from the
  prior Intelligence head. It adds one shared deterministic semantic speech
  path for Web and Mobile, including material-value preservation, budgets,
  evidence-mode provenance, safe actions, and native failure handling.
- Laptop-B `work/lia-delivery-style-profile-1-current` at
  `27f1ee263e11066eab6d734d4b7d8bb799d94728` was documentation/profile work
  from an older Intelligence tip and was integrated after reconciliation. Its
  future renderer language now explicitly targets a Twelve Hats-owned engine;
  commercial hosted TTS, vendor identities, credentials, and per-render calls
  are disallowed in production.
- Phone remains contained at `72ed521e09dd32e315c081c71024a6f6c4353f0b`;
  no patches were replayed. Its Expo Speech adapter remains a local,
  transitional fallback, while Mobile now consumes the same semantic shaping
  contract as Web.
- Added `docs/architecture/lia/voice-sovereignty.v1.md`, formalizing Twelve
  Hats ownership of identity, rights-cleared training data, pronunciation,
  delivery, model artifacts, inference, privacy, and portability. The
  `LiaSpeechRenderer` boundary is reserved for `TWELVE_HATS_SPEECH`.
- No database migrations. Backend qualification remains `653 passed` with 3
  warnings and Alembic head `o1q9s27h4u0v`. Current focused frontend
  qualification: 57 tests, ESLint, TypeScript, Vite passed. Current Mobile
  qualification: 16 suites / 152 tests, typecheck, lint, config validation,
  and iOS/Android exports passed. Local Xcode Release remains unavailable when
  generated CocoaPods configuration is absent.
