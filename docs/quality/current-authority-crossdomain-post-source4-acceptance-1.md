# Current Authority Cross-Domain Post-SOURCE.4 Acceptance 1

## Purpose and authority boundary

This packet prepares OM2-C read-only acceptance immediately after Migration admits
SOURCE.4 and Enterprise clears Preview. It composes, without replacing, the
authoritative `operations.realdata.acceptance.v1` Customer → Location → Job →
Appointment → Scheduling → Dispatch harness and extends the inspected chain through
Estimate → Invoice/AR.

The extension consumes only a bounded, server-generated admitted projection bundle.
It cannot import, repair, map, issue, invoice, collect, post, send, or otherwise mutate
source or ACP state. Raw HCP records, credentials, Customer contact values, free text,
payment evidence, and Accounting facts are not accepted fields.

## Hard execution gates

The command returns status `3` and creates no report unless the bundle includes both:

1. Migration-generated SOURCE.4 admission evidence with source system
   `housecall_pro_source4`, state `PLAN_CONFORMING`, a package digest, and a completion
   evidence digest.
2. Enterprise-generated Preview clearance with state `CLEARED` and its authority
   digest.

The presence of acquired SOURCE.4 files, synthetic fixtures, repository tests, a
healthy Redis service, or a Preview deployment does not substitute for either gate.

## Projection contract

In addition to the existing `lineage`, `appointments`, `schedules`, `dispatches`, and
`crosswalks` arrays, Migration supplies bounded `estimates` and `invoices` arrays.
They contain opaque source identities/digests, native UUID relationships, Company and
Branch scope, accepted Estimate snapshot evidence, Invoice line-evidence completeness,
and Invoice/AR status and amounts. Arrays are independently capped at 10,000 rows.

The report classifies each commercial projection as:

- `MATCHED`: admitted lineage, native identity, scope, relationship, snapshot/line
  evidence, and AR invariants agree.
- `PARTIAL`: admitted source evidence is explicitly absent or incomplete; no fact is
  fabricated.
- `MISSING_NATIVE`: required native Estimate, Invoice, or Job identity is missing.
- `ORPHANED`: Customer, Location, Job, or Estimate lineage is absent.
- `CONFLICTING`: tenant scope, duplicate/replay identity, relationship, or AR amount
  evidence disagrees.

Unmapped technicians remain `PARTIAL`. Foreign Company/Branch, contradictory replay,
negative AR, open balance greater than Invoice total, missing native identity, and
relationship disagreement fail closed. Source order does not change the report digest.

## Sanctioned execution

Enterprise writes the admitted projection bundle and report to protected operator-
selected paths, then runs from `backend`:

```text
ENVIRONMENT=preview python -m scripts.crossdomain_post_source4_acceptance \
  --input /protected/operator-selected/admitted-crossdomain-projections.json \
  --output /protected/operator-selected/crossdomain-acceptance-report.json
```

Exit `0` means no conflicting, missing-native, or orphaned condition. Exit `1` means
the report contains a blocking acceptance finding. Exit `3` means SOURCE.4 admission
or Preview clearance was not proven, and no report was created.

This command reads only the supplied projection file and writes only the requested
report file. No API, provider, source, database, Preview, or Production mutation is
performed.

## Prepared scenarios

1. Fully matched Customer → Location → Job → Appointment → Schedule → Dispatch →
   accepted Estimate snapshot → Invoice/open AR.
2. Unmapped technician with empty native assignments remains partial across Schedule
   and Dispatch.
3. Missing accepted Estimate snapshot and missing Invoice lines remain partial.
4. Missing native identities and missing parent lineage fail closed.
5. Foreign Company/Branch and relationship substitution fail closed without exposing
   another tenant's fields.
6. Duplicate/contradictory source replay fails closed deterministically.
7. Invalid negative AR or open balance above Invoice total fails closed.
8. Missing either admission receipt or Preview clearance prevents execution and report
   creation.

## Current gate state

At preparation time, the repository and sanctioned local paths contained no protected,
Migration-generated admitted cross-domain SOURCE.4 projection bundle and no explicit
Enterprise Preview-clearance receipt. Therefore only deterministic synthetic contract
qualification is authorized. Real-data acceptance must stop at the gate.
