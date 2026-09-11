# OM1-ECO QBO contract successor checkpoint

- Mission: `origin/work/launch-20260911-mission` at
  `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`; file SHA-256
  `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`.
- Current protected base: `0b74c7654fde500529da824bdce604e01575cec1`.
- Protected integration already present: OM1-ECO PR #201 as `d8999fc8` and
  OM2-B PR #206 as `9b7dd10b`.
- Successor branch: `work/qbo-contract-successor-1`.
- Contract reconciliation is protected as PR #209 at `3bcac1eb`.
- Read-probe successor implementation: this branch's head commit.

PR #201 merged before its final OM2-B response-shape reconciliation commit was
published. The earlier authorization/completeness hardening was already content-
equivalent in protected authority, so its cherry-pick was correctly empty. This
successor contains only the missing consumer-contract convergence.

The endpoint now returns OM2-B's required `mode`, provider environment, hashed
company identity, CompanyInfo verification time, source-manifest digest,
completeness, bills and conflicts, while retaining explicit provider authorization,
historical/current evidence mode, entity/page counts and catalog dispositions.
`mode=live` requires an exact current production marker/realm/CompanyInfo/API-version
match. A preserved snapshot without that authority is `historical`; absent evidence
is `blocked`. No QBO or Accounting mutation exists.

Combined qualification on current protected composition:

- QBO, source projection, Economics and operational measurement: 440 passed.
- OM2-B QBO API/component/route tests: 3 files, 5 tests passed.
- Backend focused Ruff/MyPy/compilation and frontend TypeScript/ESLint passed.
- No migration or schema change.

State: the response contract is protected-integrated; the read probe is IMPLEMENTED
and QUALIFIED but not protected-integrated, Preview-deployed, or deployed-accepted.
Enterprise must review/integrate this scoped successor, deploy the coherent
OM1-ECO/OM2-B release, and perform authenticated Preview acceptance.
Real acquisition remains `LIVE_QBO_AUTHORIZATION_BLOCKED` until protected production
credentials, exact Company binding and provider readability are actually available.

## Production CompanyInfo read probe

The successor also provides a sanctioned GET-only probe that can prove the current
protected production realm is authorized and readable without starting a full
financial acquisition:

```shell
python -m app.qbo_source.production \
  --run-id company-info-probe-YYYYMMDD-unique \
  --cutoff YYYY-MM-DD \
  --company-info-only
```

The operator must run this only in the protected backend runtime after the exact
production Company binding, verified production connection marker, and protected
OAuth token are present. The probe uses the production Intuit API host and existing
read-only adapter. It requests only `CompanyInfo`, seals its provider envelope and
manifest, and closes the HTTP client. Probe run IDs occupy the dedicated
`company-info-probe-` namespace and cannot be resumed as full acquisition IDs.

The resulting manifest is deliberately non-bounded. A successful probe proves only
that the configured production realm and exact Company were readable at that source
timestamp; it does not establish financial-population completeness, report basis,
or a live OM2-B projection. Unqueried entity families are not recorded as
`EMPTY_CONFIRMED`. A full catalog acquisition remains required for live financial
evidence. Any provider/OAuth failure remains explicit failed evidence and must not be
relabeled live.

The OM2-B financial projection admits only a complete full-catalog manifest with a
matching, digest-verified `BOUNDED_COMPLETE` snapshot. It ignores non-bounded probe
manifests when selecting the latest financial snapshot and loads only the bounded
snapshot's included entities. Registered source reports are composed only when both
their accounting basis and report end date match the requested bounded snapshot;
date-incompatible controls are excluded with an explicit limitation. This prevents a
newer readability probe, post-cutoff transaction, or older report from silently
changing the source-to-projection result.

No QBO mutation, Accounting posting, ledger creation, money movement, Production
deployment, repricing, or policy value is introduced by this probe.
