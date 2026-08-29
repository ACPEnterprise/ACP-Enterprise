# SOURCE.4 native Service Location identity

SOURCE.4 establishes an acquisition boundary; it does not import Customers or
Service Locations and does not change an immutable pilot boundary.

## Provider evidence and capability

| Source | Customer ID | Service Location ID | Relationship evidence | Result |
| --- | --- | --- | --- | --- |
| Accepted Customer CSV | Yes | No | Repeated address groups under Customer | Insufficient for native location identity |
| Accepted Job CSV | Job ID varies by registered schema | No proven native location ID | Customer and service-address fields | Insufficient; Job number is not an identity substitute |
| Invoice/Payment exports | Financial IDs | No | Customer/Job references where exported | Insufficient |
| Appointment evidence | Appointment ID | No | Customer/Job scheduling references | Insufficient |
| Housecall Pro public API | Customer and Job IDs | Address ID accepted when creating a Job | Existing Customer ID plus existing Address ID | Authoritative acquisition path |

Provider documentation establishes that Customers may have multiple saved
addresses and that Job creation accepts the ID of an existing address and
Customer. The API is therefore the supported source capable of supplying native
address identity. CSV address text remains corroborating evidence only.

Evidence sources (accessed 2026-08-03):

- <https://docs.housecallpro.com/>
- <https://docs.housecallpro.com/docs/housecall-public-api/2dcf481ed7d69-create-a-job>
- <https://docs.housecallpro.com/docs/housecall-public-api/042bd3bf861ae-get-customers>
- <https://help.housecallpro.com/en/articles/932653-add-multiple-addresses-to-a-customer>
- <https://help.housecallpro.com/en/articles/1083638-using-notes-customers-jobs-and-addresses>
- <https://help.housecallpro.com/en/articles/2999685-exported-report-breakdown>

## Relationship map

```text
provider Customer ID ──owns──> provider Address/Service Location ID
        │                                  │
        │ hash(provider, customer, id)      │ hash(provider, service_location, id)
        v                                  v
CustomerSourceIdentity <──parent── ServiceLocationIdentityEvidence
                                      │
                                      └── optional accepted mapping later
                                          (ServiceLocationSourceIdentity)
```

The evidence record is Company-owned, branch-attributed, provider- and
entity-scoped, append-only, and distinct from the ACP Service Location ID. Raw
provider identifiers and payloads are not stored in the acquisition record or
returned by its API.

## Acquisition and reconciliation policy

An authorized provider adapter must obtain the native address ID and native
Customer ID, hash them before persistence, and supply artifact, record, and
address evidence digests. Contradictory or insufficient parent evidence remains
unbound. Exact replay produces the same observation and evidence digests.
Corrections add a new evidence version linked to prior evidence; accepted
evidence is never silently replaced.

The fail-closed classifications are: missing source identifier, duplicate
source identifier, one identifier with multiple candidate locations, one
normalized address with multiple identifiers, source Customer mismatch, missing
parent Customer, incomplete address, existing ACP identity conflict, previously
imported identity mismatch, and reconciliation required. Equal normalized
addresses never merge native identities.

## Readiness and next action

**READY WITH CROSSWALK.** The provider API can supply the native identity, while
accepted CSVs cannot. SOURCE.5/LOCATION.2 must not begin until an owner-authorized,
all-scope API extraction is captured as a restricted artifact and reconciled to
Customer source identities. The extraction must include provider address ID,
provider Customer ID, complete address fields, archived/inactive addresses when
available, extraction timestamp, paging evidence, and an artifact checksum.
Credentials and raw records remain outside Git.
