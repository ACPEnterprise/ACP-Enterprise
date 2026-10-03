# HCP Estimate and financial-history cutover

This workflow is non-mutating until Release separately authorizes execution on
an isolated Beta clone. HCP evidence never creates accounting postings and the
commands never write to HCP.

## Estimate promotion

Build `hcp-estimate-promotion-plan/v1` with
`backend/scripts/build_hcp_estimate_promotion_packet.py`. Inputs are sealed HCP
Estimate evidence, exact native Customer/Location/Job and commercial-snapshot
bindings, and a read-only export of existing native source state.

Each provider Estimate receives exactly one disposition: `CREATE`, `REUSE`,
`UPDATE`, `HISTORY_ONLY`, `CONFLICT`, `OWNER_DECISION_REQUIRED`, `UNSUPPORTED`,
or `REPLAY`. Changed evidence becomes `UPDATE` only when it is a newer provider
version and the ACP target has not changed since its prior provider application.
ACP-native-newer work is always `CONFLICT`.

Canonical `estimate_proposals` require immutable ACP Price Book commercial
snapshots. An open HCP Estimate without exact line-to-snapshot bindings is
`OWNER_DECISION_REQUIRED`; a closed Estimate without those bindings remains
`HISTORY_ONLY`. The cutover must never manufacture Price Book snapshots merely
to admit history.

## Parent and lifecycle rules

- Customer, Location when supplied, and Job relationships are exact provider-ID
  bindings. Missing or ambiguous parents quarantine only the affected Estimate.
- Multiple source Jobs require an owner decision because canonical Estimate
  lineage permits one sold conversion path.
- Lines and options retain unique provider identities, amounts, status, notes,
  employee attribution, source version/timestamps, digest, and as-of evidence.
- Exact packet replay is stable; a same-version/different-digest assertion fails
  closed.

## Credits, refunds, reversals, and unapplied credit

`hcp-financial-history-classification/v2` retains Invoice payments and refunds
and now inventories Invoice credits, payment reversals, and unapplied credits.
Exact provider identities are source history; missing identities are
`REVIEW_REQUIRED_MISSING_PROVIDER_IDENTITY`. Every record remains
`HCP_SOURCE_BACKED_NOT_ACCOUNTING_POSTING` and `aggregation_safe=false` until
canonical Accounting reconciliation proves otherwise.

## Release rehearsal evidence

Release must provide the sanctioned Beta clone digest, current GET-only HCP
acquisition manifest, cutoff/as-of, source and native packet digests, plan
digest, disposition counts, and replay receipt. Current open-Estimate counts and
actual CREATE/UPDATE cohorts cannot be claimed without that evidence.
