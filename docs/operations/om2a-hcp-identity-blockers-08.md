# HCP identity blocker recovery package

Laptop Master must generate the protected runtime inventory with
`hcp_update_runtime_successor_command.py` inside the authorized read-only
Preview boundary. The inventory must contain all 417 UPDATE bindings and remain
mode 0600. OM2-A does not possess that database-derived output and therefore
does not claim that any of the 417 bindings is resolved yet.

Inside the same protected custody boundary, build the candidate-bound package:

```bash
umask 077
cd backend
PYTHONPATH=. python scripts/build_hcp_identity_recovery_packet.py \
  --runtime-inventory /protected/hcp/runtime-successor-inventory.json \
  --source-packet /protected/hcp/current-schema-execution-packet.json \
  --output /protected/hcp/identity-recovery-package.json
```

The command requires exactly 417 unique database-derived rows, restrictive
input permissions, complete evidence digests, and a dependency graph whose
parents all exist in the inventory. It classifies every binding into the five
owner-authorized outcomes. A missing legacy identity remains held; it is not
treated as proof that the native record is absent. Conflicts, cross-scope rows,
and graph mismatches are never mapped by names or other fuzzy attributes.

Only exact successors whose complete parent graph is also exact appear in the
independent recovery cohort. The package carries no mutation authority. It is a
candidate for independent review and a later SHA/schema/Company/Branch-bound
execution authority, not an admission command.

The customer population reconciliation remains a separate protected set
operation. Laptop Master must export the 635 restored provider/native identity
rows and compare them with the 5,464 owner export IDs, 5,253 sealed SOURCE.4
IDs, and 5,381 current acquisition IDs. Counts or name-only matches cannot
substitute for the four record-level identity sets.

Attachment recovery remains blocked until Laptop Master restores the sealed
621-reference manifest and 3,088,372,246-byte media bundle, or supplies an
approved provider GET-only retrieval manifest. No attachment URL may be
constructed from a filename or identifier.
