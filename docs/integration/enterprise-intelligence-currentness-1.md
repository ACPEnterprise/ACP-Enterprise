# ENTERPRISE.INTELLIGENCE.CURRENTNESS.1

## Evidence ledger

- Protected base: `origin/customer-management-v1`
- Observed protected SHA: `a65a104c21282fd8f94a2e9bac37ba576a91a75c`
- Integration branch: `integration/laptop1-intelligence`
- Worker consumed: `origin/work/beacon-luminary-realdata-acceptance-1`
- Worker SHA: `92be0b1d74a3023d9abbffd4fc3abaf5e4792036`
- Worker ancestry: direct descendant of the protected SHA
- Integrated code commit: `559f4e1412552f48b2e5eec81586aaa2a6b8ea55`

## Integrated capability

Beacon morning briefs now consume persisted evaluation-history deltas when a
completed run exists in the requested Company/Branch window. They expose NEW,
RESOLVED, CHANGED, and EXPIRED counts while retaining explicit limitations and
the existing read-only/source-domain boundary. Without completed history, the
brief remains truthful and reports comparison as unavailable.

## Qualification

- Ephemeral PostgreSQL migration `upgrade head`: passed.
- Focused Beacon tests: `5 passed`.
- Python compilation of changed modules/tests: passed.
- `git diff --check`: passed.
- No migration changed; no canonical Alembic head claimed.
- Frontend unchanged; frontend suite was not run because local `vitest` is not
  installed.

## Acceptance and release gates

- Preview health is reachable, but reports deployed SHA
  `a109743968fc764fc1885ecf8fbd4abeb87846d7`, not the current protected SHA.
- Authenticated Preview owner acceptance remains required.
- No real All County Beacon/Luminary result was accessed in this lane.
- OM1 ENTERPRISE.RELEASE owns final protected integration, migration reline,
  Preview/Production deployment, and owner acceptance authorization.

## Factory 2.0 currentness sweep — 2026-09-17

- Current protected authority: `origin/customer-management-v1` at
  `1be3de4456afc7b67ed6bb9f54644468318dd6e4`.
- Current cumulative Intelligence head: `b3a7ff9ee937efa633e478183b8d764c7d9286ed`.
- Merge-base: `1be3de4456afc7b67ed6bb9f54644468318dd6e4`; relationship `0 behind /
  1156 ahead`; remote/local divergence `0/0` before this ledger update.
- Worktree was isolated and clean. Original checkout was not inspected for
  mutation and was not modified.

### Worker inventory and disposition

- `origin/work/lia-voice-genesis-proprietary-engine-1` at
  `3bacb78436fa87d5217eaafe862a5db195c08937`: `ALREADY_INTEGRATED /
  PATCH_EQUIVALENT`. The current head contains the same Twelve Hats speech
  engine foundation through `17dd21a0`; no provider runtime, credentials,
  model artifact, or audio output was replayed.
- `origin/work/lia-voice-genesis-corpus-rights-1` at
  `ca9df20d50a6c2cadfe837b25dc195b635de0730`: `ALREADY_INTEGRATED /
  PATCH_EQUIVALENT`. The owned Genesis corpus/rights metadata is present
  through `6f0c2f7d`; no recording, upload, training, or voice cloning work was
  replayed.
- `origin/work/laptop1-phone-twelve-hats-speech-readiness-1` at
  `59da53a94c91a9d0fb0431a3a1b80012ae58a612`: `STALE_BASE /
  RECONCILIATION_REQUIRED`, not integrated. Its patch removes the current
  shared semantic speech renderer and reverts Mobile to speaking the raw
  server answer, which conflicts with the qualified web/Mobile semantic
  contract. The current head retains the safer owned-renderer boundary and
  local fallback. Phone must rebase and republish an additive readiness
  checkpoint if it has new work.
- Prior LIA spoken-presence and delivery-profile refs remain
  `ALREADY_INTEGRATED` or documentation/history-only; no newer Beacon,
  Luminary, Analytics, or reporting implementation checkpoint was found in the
  current remote inventory.

### Integration-owned audit and refill queue

- LIA routes remain split correctly: owner `/api/v1/lia/ask`; employee-safe
  `/api/v1/lia/employee/ask`. The employee route remains permission-gated by
  `COMPANY_EMPLOYEE_OPERATIONS_OWN_LIA_READ`; Mobile references only the
  employee route. No route or permission widening was made.
- Current Intelligence retains Twelve Hats speech sovereignty: browser/device
  speech and Expo local speech are transitional local fallbacks; the owned
  engine remains fail-closed until an owned accepted artifact and inference
  implementation exist. Commercial TTS remains disallowed.
- Existing actionable cross-domain queues were preserved rather than hidden:
  Customer identity/completeness reconciliation, Payroll readiness, Revenue
  Cycle application/settlement/cash/as-of projections, Timekeeping period-hour
  projection, Analytics currency authority, and exact Luminary/Economics
  finding identifiers. These are source-domain handoffs, not Intelligence
  implementations.
- Refill Laptop-A with a bounded LIA acceptance/contract audit: stale route,
  evidence/provenance, correction, period, and navigation checks against the
  latest protected Operations contracts; no new architecture unless a defect
  is reproduced.
- Refill Laptop-B with a Beacon/Luminary real-data contract audit focused on
  evidence freshness, incomplete states, drill-down identity, and currency;
  do not infer or fabricate missing source authority.
- Refill Phone with an additive native-speech readiness revision based on the
  current shared semantic renderer; require employee-route-only behavior,
  lifecycle cancellation, local fallback, and no deletion of qualified speech
  semantics.

### Qualification status

- Previously qualified cumulative backend, frontend, and Mobile results remain
  valid for the unchanged implementation. Current environment checks: Python
  compilation, JSON/profile validation, diff check, and changed-boundary
  secret scan pass. Host backend pytest is unavailable (`pytest` module absent)
  and Docker migration qualification is unavailable because the configured
  Docker credential helper is missing; neither is claimed as passed.
- No schema or Alembic change. No Preview/Production deployment. Authenticated
  All County acceptance remains pending; the deployed Preview SHA and employee
  environment availability must be rechecked by OM1 after release.

## Factory 2.0 worker reconciliation — 2026-09-17

- Protected authority refreshed to `785511810d9399c33c8d8727cf6fe01420fc1226`.
  The protected merge was reconciled into this lane before worker integration;
  protected authority remains an ancestor and was not modified.
- Prior Intelligence head `2602bebacf8424ba1e24c93cbf9717c70b8c1f08` was
  preserved. A’s candidate was based directly on it. The resulting bounded LIA
  checkpoint is `0a9074e1`; the resulting Mobile lifecycle checkpoint is
  `d3d4cd14`.

### Laptop-A

`origin/work/lia-current-contract-acceptance-1` at
`ba92adcabc7c6d2c19df906d43954470562f0c3f` was `PARTIALLY_CONTAINED`:
protected reconciliation already supplied its backend contract changes, while
the genuinely new frontend multi-domain continuation and bounded topic-context
behavior were integrated as `0a9074e1`. Focused LIA/voice and route tests pass
14/14. Authorization, evidence digests, safe navigation, and multi-domain
context remain bounded and server-authoritative.

### Laptop-B

- `e7b96734d657312cd3c7c1a685f4d779614cb9e6` — `POST_PRODUCTION_FOUNDATION`;
  Genesis-to-training admission governance is not required for current Beta
  spoken experience and was not replayed.
- `e5f707879d9fc577929c620fc22119f5761f57c6` — `POST_PRODUCTION_FOUNDATION`;
  pronunciation authority is useful for a future owned engine but does not
  change current local fallback behavior and was not replayed.
- `68d5c91e885acac5ab08d15defecbce401f8c7e4` — `DEPENDENCY_BLOCKED /
  POST_PRODUCTION_FOUNDATION`; model promotion ledger depends on the
  pronunciation admission path and is not current Beta functionality.
- `d6cdf7aaf03d255d9085e0bde98f4411969444bd` — `DEPENDENCY_BLOCKED /
  POST_PRODUCTION_FOUNDATION`; training-run ledger depends on model promotion.

These four commits are not patch-equivalent to the current head, but remain
qualified governance backlog rather than implementation to absorb merely for
throughput. No Beacon/Luminary/Analytics implementation candidate was newly
published in this sweep.

### Phone

`origin/work/laptop1-phone-twelve-hats-speech-readiness-1` at
`c5539e489f3934d7fbef8bc684172c0eb2f10aec` was `STALE_BASE /
CONFLICTING`. Its whole patch would remove the shared semantic renderer and
restore raw-answer speech; its broad lockfile/Podfile changes were therefore
not cherry-picked. The non-regressive lifecycle subset was manually reconciled
as `d3d4cd14`: AppState background cancellation, speaking-state cleanup, and
native completion/stop callback handling, with regression coverage. No
dependency drift or Podfile repair was claimed.

### Meaningful cumulative delta and worker refill

- LIA: bounded multi-domain conversation retention and context-safe follow-up
  navigation; no source-domain joins or authorization widening.
- Mobile: speech cannot continue behind a backgrounded screen, and completion
  or stop returns UI state to idle; employee-safe endpoint and shared semantic
  speech remain unchanged.
- Beacon/Luminary/Analytics: no new implementation delta; existing evidence,
  incomplete-state, provenance, and currency boundaries remain protected.
- Next Laptop-A assignment: `LIA.SPOKEN.PRESENCE` continuation and real-data
  acceptance defects only.
- Next Laptop-B assignment: `LIA.DELIVERY.STYLE.PROFILE.1` audit of cadence,
  current TTS capabilities, and distinct synthetic voice options; no cloning,
  upload, purchase, or provider commitment.
- Next Phone assignment: rebase a TestFlight-ready Mobile checkpoint from
  current Intelligence, preserve the shared semantic renderer, and qualify
  native speech lifecycle/build behavior. Do not revive the stale raw-answer
  path.

## Factory 2.0 current-authority reconciliation — 2026-09-17

- Protected authority remained `785511810d9399c33c8d8727cf6fe01420fc1226`.
- Prior Intelligence head was `d484fcd605d220dc73d5f532881ff64669322042`.
- Protected reconciliation was already applied before this cycle; the new
  protected authority remains an ancestor.

### New worker dispositions

- Laptop-B `origin/work/lia-delivery-style-device-prototype-1` at
  `2f9d41efc303e4ebe22e1edc15dd7ae2c8d30a51`: `USEFUL_NOW`, integrated as a
  bounded current-Beta voice improvement. It preserves the semantic renderer
  and material values while adding deterministic local-English voice inventory,
  reviewed browser-local preference, safe fallback, and same-corpus A/B
  evaluation. No provider, cloning, or schema change.
- Phone `origin/work/laptop1-phone-twelve-hats-speech-readiness-1` at
  `cbebae37f68bc62e7180a4feacb681c0f30b4b34`: `PARTIALLY_CONTAINED /
  USEFUL_NOW`. The current branch was based on stale `2602beb...`; its
  reconciled shared-renderer restoration is compatible. The previously
  integrated lifecycle salvage was retained, and the current Phone checkpoint
  is not replayed wholesale because its remaining diff includes stale
  semantic/test changes. No owner-route fallback was admitted.
- Older Phone raw-answer branches remain rejected as regressive.

### Current product classification

- Variant A: improved semantic spoken renderer — `CURRENT`.
- Variant B: reviewed distinct local/device voice selection — `BETA-CAPABLE`.
- Variant C: governed cross-device Twelve Hats-owned TTS successor — justified
  future work, not a commercial-provider integration.
- Web browser speech and Mobile Expo/native speech remain transitional local
  fallbacks. They cannot guarantee stable expressive identity across devices.

### Resulting bounded work

- A’s LIA continuation checkpoint: `0a9074e1`.
- Phone lifecycle checkpoint: `d3d4cd14`.
- B device-voice checkpoint: integrated in the current cumulative head.
- Current cumulative head after this ledger/code update: to be recorded at
  push completion below.
- No migration or Alembic change. Employee-safe authorization and semantic
  Web/Mobile parity remain unchanged.

### Qualification

- Web LIA/voice focused tests: passed; full frontend qualification remains
  available from the prior cumulative checkpoint.
- Mobile LIA focused tests: 9/9 passed after lifecycle salvage; Mobile
  typecheck, ESLint, and config validation passed.
- Python compilation and `git diff --check` passed.
- Backend pytest and disposable PostgreSQL migration remain unavailable in
  this environment and are not claimed as passed.

### Worker refill

- Laptop-A: continue LIA spoken-presence and contract-acceptance defects.
- Laptop-B: evaluate the current device voice prototype against the 12-case
  corpus and return to delivery-style evidence; no external provider path.
- Phone: rebase from the resulting cumulative head for TestFlight readiness,
  preserving semantic speech, background cancellation, and employee-safe
  routing.

## Factory 2.0 current-authority reconciliation — device voice and Mobile — 2026-09-17

- Refreshed protected authority: `785511810d9399c33c8d8727cf6fe01420fc1226`.
- Prior Intelligence head: `d484fcd605d220dc73d5f532881ff64669322042`.
- Laptop-B `origin/work/lia-delivery-style-device-prototype-1` at
  `2f9d41efc303e4ebe22e1edc15dd7ae2c8d30a51`: `USEFUL_NOW`, integrated as
  `1372998d`. The prototype is additive and preserves one semantic speech
  path, missing-evidence meaning, and material values. Browser-local reviewed
  voice preference and deterministic fallback are Beta-capable; no provider or
  identity inference was added.
- Phone `origin/work/laptop1-phone-twelve-hats-speech-readiness-1` at
  `cbebae37f68bc62e7180a4feacb681c0f30b4b34`: `PARTIALLY_CONTAINED /
  PATCH_EQUIVALENT_FOR_SAFE_BEHAVIOR`. Current Intelligence already contains
  the restored shared semantic renderer, background cancellation, speaking
  cleanup, and native callback boundary. The remaining branch diff is stale
  base/lockfile churn and a weaker raw-answer test path; it was intentionally
  not replayed. No Phone-owned successor commit was needed in this cycle.

### Final classification

- Variant A — improved semantic spoken renderer: `CURRENT`.
- Variant B — reviewed distinct local/device voice selection: `BETA-CAPABLE`.
- Variant C — governed cross-device Twelve Hats-owned TTS: justified future
  work. Commercial TTS remains disallowed and no Lianne cloning or external
  audio processing occurred.
- Current limitations: browser and native device voices vary by platform;
  stable expressive identity, SSML/prosody control, and portable voice style
  are not guaranteed.

### Qualification and release state

- Web voice/LIA focused qualification: 35/35 passed.
- Full Mobile qualification: 17 suites / 154 tests passed; Mobile typecheck,
  ESLint, and config validation passed.
- Python compilation, `git diff --check`, and prior frontend build/static
  qualification remain green. Backend pytest and disposable PostgreSQL
  migration remain unavailable in this environment and are not claimed.
- No schema/Alembic changes. Preview and Production were not deployed.
- Authenticated owner/employee Preview acceptance and physical Mobile voice
  acceptance remain pending until compatible server authority is deployed.

## Factory 2.0 current reconciliation — combined Web/Mobile voice — 2026-09-17

- Refreshed protected authority: `785511810d9399c33c8d8727cf6fe01420fc1226`.
- Starting Intelligence SHA: `3bb0e1037f6dc1be08ebf69a3119ae8bc2eda3d2`.
- Laptop-B `2f9d41efc303e4ebe22e1edc15dd7ae2c8d30a51`: `ALREADY_INTEGRATED /
  PATCH_EQUIVALENT`; current tree contains its device-voice prototype,
  reviewed local preference, safe fallback, and evaluation behavior.
- Phone `cbebae37f68bc62e7180a4feacb681c0f30b4b34`: `ALREADY_INTEGRATED /
  SAFE_SUBSET_CONTAINED`; current tree retains the shared semantic renderer,
  local fallback, background cancellation, and callback cleanup. The stale
  branch diff was not replayed because it would weaken current lifecycle/test
  semantics and includes unrelated lockfile churn.
- No new implementation files were required. This checkpoint records the
  current authority reconciliation and combined qualification.

### Combined qualification

- Web LIA voice, device inventory, semantic preservation, and fallback tests:
  35/35 passed.
- Full Mobile suite: 17 suites / 154 tests passed.
- Mobile typecheck, ESLint, and configuration validation passed.
- Python compilation and `git diff --check` passed.
- Backend pytest and disposable PostgreSQL migration remain unavailable and
  are not claimed as passed.

### Beta voice status

- Variant A semantic spoken renderer remains current and authoritative.
- Variant B reviewed local/device voice selection is Beta-capable.
- Variant C Twelve Hats-owned cross-device speech remains future work.
- Current limitations are device/browser-dependent voice identity and lack of
  portable expressive, SSML, prosody, and stable cross-device controls.
- No commercial TTS provider was selected; no voice cloning or external audio
  upload occurred.
