# JOB.SOURCE.2 complete historical Job source readiness

## Decision

Expanded Job migration is **BLOCKED — SOURCE REQUIRED**. The 305 Jobs in
Preview are the idempotent accepted subset of a filtered 950-row export, not the
complete Housecall Pro history. No additional Job import is authorized by this
readiness milestone.

## Available boundary

The accepted Phase 1 artifact used the registered 25-column schema
`housecall_pro_job_export_20240321_v1`. Its Housecall Pro download metadata
records a start filter from `2022-09-28T00:00:00Z` through
`2024-06-30T04:59:59Z`; the file was extracted on March 21, 2024 and contains
950 unique `HCP Id` values. It therefore cannot establish all-time
completeness.

A second same-day snapshot also contains 950 rows. The snapshots share 947
identities: 944 rows are byte-equivalent at the parsed-field level, three
shared identities have updated source values, and each snapshot contains three
identities absent from the other. Source versions must be retained; the files
must not be unioned and described as one consistent export.

The available 2026 eight-column export is registered for inspection as
`housecall_pro_jobs_export_2026_v1`. It contains `Job #`, not the legacy `HCP
Id`. `Job #` identity semantics are unproven, so the adapter deliberately does
not promote it to a stable identifier or use it for cross-schema merging.

Monthly and customer Job reports are aggregate controls only. They cannot be
used to manufacture row-level completeness or operational records.

The available customer exports contain customer, address, and free-text note
fields but no stable Job ID or row-level Job relationship. Their ZIP copies are
byte-equivalent to their extracted CSV members where duplicates exist. No
dedicated Housecall Pro Job-note or Job-attachment export was discovered. These
artifacts can support later parent review, but cannot expand the authoritative
Job identity boundary.

## Owner acquisition procedure

In Housecall Pro, an authorized owner must request or generate a Job export
with these settings and retain evidence of the selections:

1. Select all business units/branches and an all-time range with no lower date
   bound. Record the extraction/cutover timestamp and timezone.
2. Include every lifecycle state: completed, scheduled, in progress,
   unscheduled/needs scheduling, cancelled, archived, deleted, and voided where
   Housecall Pro permits export.
3. Include stable internal Job ID and keep display Job number as a separate
   field. Obtain written HCP documentation or API evidence for the identity
   semantics.
4. Include stable Customer ID and Service Address or Service Location ID. Names
   and formatted addresses are insufficient identity keys.
5. Include branch/business-unit ID, source status, and created, scheduled,
   completed, cancelled, archived, and updated timestamps where available.
6. Include relationship identifiers for visits/appointments, child work
   orders, estimates, invoices, payments, notes, and attachments.
7. Export cancelled/deleted/voided records separately if the primary grid
   cannot include them. Record every filter and the count displayed by HCP
   before downloading each file.
8. Place the files in a restricted migration source directory outside Git,
   make them owner-readable only, and record filenames, byte sizes, and SHA-256
   checksums before review.

If HCP cannot produce one complete file, acquire deterministic partitions:

- one nonoverlapping file per calendar year using created timestamp;
- a separate no-schedule-date partition;
- separate cancelled, archived, deleted, and voided partitions if required;
- a final delta from the last partition boundary through the recorded cutover;
- an HCP aggregate count using the identical scope as an independent control.

Partition boundaries must be explicit, nonoverlapping, timezone-qualified, and
recorded in the readiness evidence. Stable Job IDs are deduplicated only after
identity semantics are proven.

## Baseline control

The approximately 5,635 count remains an unproven owner-supplied control total.
Its report, measurement date, lifecycle scope, unique-ID semantics, treatment
of repeated visits/child work orders, and cancelled/deleted inclusion are not
available. The complete export must establish a new exact authoritative count
unless the original report and settings are supplied.

For the current accepted artifact only:

```text
950 source identities
= 305 imported
+ 642 Service Location dispositions
+   3 Customer identity dispositions
+   0 other rejection or duplicate
```

Against the approximate baseline, 4,685 identities remain unavailable because
the complete export has not been acquired. This is a control-total difference,
not a migratable manifest boundary.

## Future execution gates

After acquisition, validation must first produce an exact source-to-target
equation, preserve source-version history, reconcile the existing 305 HCP IDs,
and resolve or disposition Customer and Service Location parents. Only then may
cumulative 25, 100, 500, and full manifests be authorized. Every live Preview
stage requires a verified restricted PostgreSQL backup, immutable evidence,
identical-manifest replay, and zero duplicate operational or Business Event
delta.
