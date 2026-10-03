# HCP supplemental evidence cutover

This runbook covers attachments, service plans/memberships, and reviews when the
normal HCP GET API does not provide authoritative population completeness. It
does not authorize a provider write, Beta mutation, native entitlement, or
public review publication.

## Authority boundary

An empty or unsupported API response is `UNKNOWN_PROVIDER_INVENTORY`, never a
zero-count assertion. Release must obtain a provider export, HCP support export,
or downloadable manifest before declaring attachment completeness.

All input and output directories are Release-controlled, mode `0700`. Manifests,
packets, and content objects are mode `0600`. Raw exports and Customer evidence
must not be committed to Git, copied into reports, or printed to logs.

## Owner/provider export request

Request one complete All County tenant export, with an explicit acquisition
cutoff and provider account/tenant identifier, containing:

1. Attachment inventory for Customers, Jobs, Estimates, and all open-work Jobs.
2. Provider attachment ID, parent type, provider parent ID, filename, MIME type,
   byte size, created timestamp, uploader reference when available, and a
   downloadable object or provider download reference.
3. Service plan/membership provider ID, Customer provider ID, source status,
   start/end dates, recurring obligations, benefits/discounts, source version,
   and lifecycle history when available.
4. Review provider ID, rating, review text when exportable, review timestamp,
   and exact Customer/Job provider IDs when HCP supplies those relationships.
5. A provider-generated export manifest or checksum list. If unavailable,
   Release computes SHA-256 while acquiring each object and records that fact as
   acquisition provenance rather than provider provenance.

The owner must not infer attachment totals from normal application pages. HCP
Support must explicitly state whether the export is a complete tenant inventory
or a bounded/partial result.

## Attachment workflow

1. Seal the source export and manifest digests.
2. Resolve parents only by exact provider identity. Unknown parents remain held
   for orphan review.
3. Represent every record as `AVAILABLE`, `IMPORTED`, `FAILED`,
   `MISSING_SOURCE`, `RETRY_REQUIRED`, or `OWNER_EXPORT_REQUIRED`.
4. If inventory completeness is not asserted, add the synthetic accounting row
   `UNKNOWN_PROVIDER_INVENTORY`; it is not an attachment identity.
5. Verify content digest and byte size before copying into company-scoped
   immutable custody. A replay with the same digest is accepted; conflicting
   content fails closed.
6. Retry only `FAILED`/`RETRY_REQUIRED` records. A retry changes evidence through
   a new sealed packet; it never erases prior failure evidence.
7. Admit linkage only after both immutable content and exact parent identity are
   proven. The packet does not itself mutate Customer, Job, Estimate, or open
   work.

## Membership workflow

Provider service-plan records are historical source evidence by default. A
record becomes an active native service agreement only through the existing
Service Agreement authority and an exact native binding. A source record that
asserts current state but has no binding remains `HELD`; historical records are
`SOURCE`. Discounts and benefits are preserved as source evidence and do not
create current entitlement by themselves.

## Review workflow

Imported ratings and text are `OPERATIONAL_HISTORY_ONLY`. Exact Customer/Job
links are retained when provided. The packet never grants Marketing/publication
authority and never infers a missing relationship.

## Build and delta commands

Run from `backend` with the supported application environment:

```bash
python scripts/build_hcp_supplemental_packet.py attachments \
  --input /run/evidence/hcp/attachments-input.json \
  --output /run/evidence/hcp/attachments-packet.json

python scripts/build_hcp_supplemental_packet.py memberships \
  --input /run/evidence/hcp/memberships-input.json \
  --output /run/evidence/hcp/memberships-packet.json

python scripts/build_hcp_supplemental_packet.py reviews \
  --input /run/evidence/hcp/reviews-input.json \
  --output /run/evidence/hcp/reviews-packet.json
```

For a fresh acquisition, add `--prior <sealed-prior-packet>`. The output reports
exact `CREATE`, `UNCHANGED`, `CHANGED_REVIEW_REQUIRED`, and
`SOURCE_UNAVAILABLE` identity changes plus current `source`, `admitted`, `held`,
`unknown`, and `unexplained` counts.

## Closure receipt

Release publishes only non-sensitive totals and packet digests:

- source, admitted, held, unknown, and unexplained per domain;
- failed/retry/orphan totals for attachments;
- export completeness assertion and acquisition cutoff;
- input manifest, content-set, packet, and replay digests;
- exact held-reason categories;
- confirmation that identical replay created no duplicate content or bindings.

Closure requires `unexplained = 0`. `unknown` may remain nonzero only with the
explicit provider/export blocker; it must never be relabeled as zero.
