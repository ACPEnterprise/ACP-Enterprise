# LOCATION.1 multi-property Customer expansion readiness

## Decision

Preview expansion is **BLOCKED — NATIVE SERVICE LOCATION ID REQUIRED**. The
current Housecall Pro Customer export proves stable Customer identity through
`ID`, but its 61 repeated address groups contain no native Service Location ID.
An address-group ordinal is preserved as versioned evidence, but is not promoted
to an authoritative operational identity: four shared Customer records changed
between the two newest exports, demonstrating that address content and slots can
change across source versions.

No fuzzy matching, Customer-name-only classification, Job-number matching, or
use of the unproven 4,754-row Job export is permitted.

## Candidate source

- file: `AllCountyPlumbingandLeak_customer_export 3.csv` outside Git;
- rows: 5,132; columns: 450; UTF-8;
- schema: `housecall_pro_customer_450_v1`;
- SHA-256: `d2569f0ad2d907ee8f8730a924f8a91ff47e18eb392ab26500b306e564e6ce24`;
- ordered-header fingerprint:
  `13e6808d571ad993e61323c73296b45d8d55ad034ebcf653d0c03bdae70a0662`;
- transformation: 4,319 accepted, 813 contact-name rejections, zero duplicate
  source IDs, and 209 incomplete-address child exceptions.

Compared with the preceding 5,121-row export, all 4,310 accepted identities are
retained, nine accepted identities are new, and four shared transformations
changed. The new source adds eleven rows overall.

## Multi-property classification

The accepted transformation contains 111 Customers with multiple complete
service addresses and 409 complete addresses across those Customers. Applying
the existing deterministic duplicate-signal policy produces:

| Primary review classification | Customers | Locations |
|---|---:|---:|
| Commercial/property-manager evidence without duplicate signals | 3 | 20 |
| Residential anomaly | 78 | 209 |
| Ambiguous Customer/duplicate signals | 30 | 180 |

“Commercial/property-manager” requires source `Customer Type=Business` plus
multiple complete addresses; it is never inferred from a name. The owner’s
general confirmation does not decide the 78 residential anomalies or 30
ambiguous identities individually.

Every unresolved subject supports approve, reject, duplicate, defer,
correction, and unrelated-Customer dispositions. Approval fails closed until a
native stable Location ID or an owner-approved identity policy is available.

## Operational re-evaluation

Using only the accepted 950-row Job evidence, exact Customer signals and exact
normalized addresses identify 141 blocked Job rows that could become eligible
after their parent Customer and Location are approved and migrated. Another 27
multi-property rows do not exactly match a source address and require review.
Currently unlocked is zero because no Location expansion was executed.

The prior accepted equation remains unchanged: 305 imported Jobs, 642 Service
Location dispositions, and three Customer dispositions. JOB.SOURCE.3 remains
blocked and isolated.

## Required next evidence

Obtain a Housecall Pro location/property export or API response containing a
stable Service Location/Address ID and stable Customer ID. If HCP cannot provide
one, the owner must approve a separate durable identity policy after reviewing
address-slot change evidence; this milestone does not infer that policy.
