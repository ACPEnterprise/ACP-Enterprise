# SOURCE.4 UPDATE cohort authority

`MIGRATION.HCP.UPDATE.COHORT.AUTHORITY.1` seals accepted Migration intent for
all 280 UPDATE assertions. It supplies no Preview/native successor claim and no
mutation authority.

## Sealed result

- Contract: `hcp-update-runtime-cohorts/v1`
- Authority contract: `hcp-source4-update-cohort-authority/v1`
- Sanctioned path: `/Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-source4-update-cohort-authority-v1/update-cohort-authority.json`
- Internal artifact digest: `7c743c5e46af4b065d10b8e193ec7a5a0c568c385159bf33c5ed5f012eeb6b53`
- File SHA-256: `607db4495c79114ab625cdbd9480cfe36e345377ec0de4cb57bc57a5cfb4205d`
- Directory/file modes: `0700` / `0600`
- Domains: Customers 20, Locations 0, Jobs 254, Appointments 6
- Cohorts: CURRENT_OPERATIONAL 8, SAFE_HISTORICAL 0, SAFE_UPDATE 37,
  OTHER_HELD 235

The eight current-graph UPDATEs comprise five supporting Customers and three
current Jobs. This reconciles `CURRENT_SET_BINDINGS_REQUIRED = 8`. The other
current 11/11/15/18 graph members are CREATE assertions and therefore are not
members of this authority.

`appt_2075136994c64ca89be01cc631c246f2` is `OTHER_HELD` because accepted
Migration evidence classifies every historical Appointment UPDATE as requiring
a native lifecycle hold. Its parent is
`job_79334811641d4f3383f3350b8f566b67`. The artifact does not encode the
separate Preview observation `NATIVE_SUCCESSOR_MISSING`.

## Verification and Enterprise inventory

From `backend`, reproduce and compare every byte with:

```bash
python -m scripts.hcp_update_cohort_authority \
  --overlay /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/current-overlay-merge-packet.json \
  --hold-packet /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-admission-packet-20260912T170000Z/current-operational-hold-dispositions.json \
  --source-package-manifest /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-source-4-20260827T223858Z/acquisition-package-manifest.json \
  --predecessor-packet /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-migration-1-20260827T/candidates/migration-candidates.json \
  --refresh-root /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-refresh-20260912T120000Z \
  --schedule-root /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-current-open-schedule-20260912T170000Z \
  --output /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-source4-update-cohort-authority-v1/update-cohort-authority.json \
  --verify
```

After PR #265 is integrated, stage this file read-only and run:

```bash
ENVIRONMENT=preview TARGET_ENVIRONMENT=preview \
PREVIEW_ACCESS_ENABLED=true PRODUCTION_ACCESS_ENABLED=false \
python -m app.operational_migration.hcp_update_runtime_successor_command \
  --authority-file "$AUTHORITY_FILE" \
  --cohort-file /Users/michaelbfouse/.acp-enterprise/migration/housecall-pro/hcp-source4-update-cohort-authority-v1/update-cohort-authority.json \
  --output "$PRIVATE_INVENTORY"
```

That command is read-only and requires the deployed execution authority file.

## Subsequent write-authority boundary

No UPDATE-to-HOLD transition is authorized here. A subsequent versioned
authority must bind this artifact's file and internal digests, preserve the
original UPDATE assertion, bind PR #265's complete runtime inventory digest and
per-record disposition/reason/evidence, and prove both that each proposed hold
is outside the required current graph and that no required parent or current
financial truth depends on it. It must fail closed for missing inventory rows,
changed scope/artifacts/authority/schema, ambiguous or conflicting bindings,
parent mismatch, and any cohort/runtime disagreement.
