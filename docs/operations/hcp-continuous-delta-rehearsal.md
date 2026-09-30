# HCP continuous delta rehearsal

This runbook advances operational HCP evidence after the preserved SOURCE.4
cutoff. It does not authorize a live cutover and it never writes to HCP.

## Required authority

- A database clone made from the currently deployed Beta database, isolated
  from Beta runtime traffic.
- The canonical SOURCE.4 digest and the last successfully applied overlay
  receipt.
- GET-only HCP credentials held by Release/Enterprise in a mode-0600 secret
  file. Do not copy those credentials or real evidence to a worker checkout.
- Protected evidence directories must be mode 0700 and sealed files mode 0600.

## Evidence and classification

1. Acquire Customers and Jobs through the GET-only extractor. Acquire
   Appointments for changed/new Jobs. Customer contact values and addresses are
   part of their authoritative Customer graph. Appointment status and dispatched
   employee source IDs carry schedule/assignment evidence.
2. Seal provider observations with provider identity, record digest,
   `updated_at`, acquisition time, parent identities, and payload.
3. Export read-only native observations from the clone: bound provider identity,
   last applied source digest/time, and native row `updated_at`.
4. Run `backend/scripts/build_hcp_continuous_delta_packet.py`. Exact digest
   replays are excluded. New identities become CREATE. A changed source becomes
   UPDATE only when it is a provable provider successor and native state has not
   changed since the prior provider assertion. Every other changed record is a
   HOLD with an explicit reason.
5. Execute the resulting nested overlay with the established
   `execute_hcp_current_overlay.py` command and a fresh clone backup digest.
   The existing executor applies Customers, Locations, Jobs, and Appointments
   through canonical services and journals a replay-safe receipt.

Service-location updates and Estimates remain held/evidence-only because the
canonical overlay does not currently support safe mutation for those domains.
No provider removal deletes native records.

## Acceptance

On the isolated clone, query both source identities and native projections and
record exact counts for created/updated/replayed/held records. Verify:

- rerunning the identical packet returns the identical receipt;
- new Jobs and Appointments exist exactly once;
- changed provider successors update only unchanged native targets;
- a native edit after the last applied provider assertion becomes HOLD;
- recent Appointments appear in Calendar and Dispatch queries with their source
  status and assignment evidence;
- held records and their descendants do not block independent safe records.

Release must publish the clone backup digest, source acquisition timestamp,
cutoff, packet digest, receipt digest, projection counts, and conflict counts.
Only owner authorization may advance this rehearsed packet to a real cutover.
