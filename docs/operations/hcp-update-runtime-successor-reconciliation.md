# SOURCE.4 UPDATE runtime successor reconciliation

The write executor remains fail-closed. `hcp-current-overlay-native-execution/v2`
does not authorize converting an UPDATE with no native successor into a hold.
This successor adds a read-only, complete inventory so Enterprise can establish
that distinction before another write attempt.

Enterprise supplies a mode-0600 cohort artifact with contract
`hcp-update-runtime-cohorts/v1`. It must classify every UPDATE exactly once as
`CURRENT_OPERATIONAL`, `SAFE_HISTORICAL`, `SAFE_UPDATE`, or `OTHER_HELD`.
The command rejects missing, additional, duplicate, or unknown cohort entries.

```bash
ENVIRONMENT=preview TARGET_ENVIRONMENT=preview \
PREVIEW_ACCESS_ENABLED=true PRODUCTION_ACCESS_ENABLED=false \
python -m app.operational_migration.hcp_update_runtime_successor_command \
  --authority-file "$AUTHORITY_FILE" \
  --cohort-file "$COHORT_FILE" \
  --output "$PRIVATE_INVENTORY"
```

The output is mode 0600, has `mutation_authority: none`, preserves every
original UPDATE assertion, and reports all runtime dispositions by domain and
cohort. A current record outside `BINDING_ALREADY_PRESENT` or
`PROVABLE_NATIVE_SUCCESSOR_BINDING` makes
`current_operational_graph_admittable` false.

Historical bounded holds require a subsequent versioned write-authority
contract. That successor must bind the cohort artifact digest, preserve the
original UPDATE assertion plus runtime hold reason in the execution receipt,
and prove no required parent or financial/current graph depends on it. Until
then, the existing executor continues rejecting every non-provable UPDATE.
