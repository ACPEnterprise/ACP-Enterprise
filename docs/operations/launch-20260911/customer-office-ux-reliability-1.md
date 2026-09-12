# Customer Office UX Reliability 1

## Authority

- Mission ref: `origin/work/launch-20260911-mission`
- Pinned mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission document SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`
- Protected base: `68cdc38976fcfb2d5a20e7ce52fc78306bde91ce`
- Preserved predecessor candidate: `12ade09412eb7f00370bf18562063c342cb0caa7`

This increment consumes the existing Customer and Migration-readiness contracts. It does not decide source identity, admit source records, mutate source data, or claim that a rendered page represents the complete Customer population.

## Reliability behavior

- The roster keeps server-side pagination and supported name, phone, email, and location/address search.
- Source readiness failures identify completeness and freshness as unverified and offer an explicit retry.
- Stale source projection is prominent and does not prevent use of admitted native records.
- Partial source population identifies held, exception, deferred, unresolved, and delta evidence as outside native Customer authority.
- Empty Locations and Contacts are described as an absence of admitted native records, not proof that upstream evidence is empty.
- Missing optional Contact phone/email fields have a stable textual fallback.
- Related-work failures preserve the Customer identity surface and fail safely.

## Authenticated Preview acceptance checklist

Run this only after Enterprise integrates and deploys the increment. Use the accepted authenticated owner/office identity and approved synthetic or admitted non-Production records. Do not expose credentials and do not mutate HCP/QBO source evidence.

1. Confirm Preview reports the exact integrated deployment SHA and healthy backend/frontend status.
2. Open `/customers` and record the admitted native total, page size, current page, source counts, and source as-of timestamp. Do not infer completeness from page 1.
3. Traverse the first, a middle (when present), and the last roster page; return to the first page and verify stable identities and totals.
4. Search separately for a known admitted Customer by name, phone, email (where admitted), and Service Location address. Confirm every result resolves to the same authoritative Customer identity expected by the acceptance dataset.
5. Clear search and verify the original population and pagination return without a stale filtered projection.
6. Open a full Customer and verify identity, optional contact fields, Contacts, multiple Service Locations, source metadata when available, and archive status.
7. Open a Customer with no current Job and verify the UI reports no linked native Jobs without implying that source history is complete.
8. Follow related Job and Appointment links, then navigate back. Confirm Customer and Location context remains intact and no manual re-search is required.
9. Verify held/source-only counts are visibly distinguished and are never represented as admitted/selectable native Customers.
10. Using an accepted deterministic Preview fixture or controlled API interception, exercise partial, stale, unavailable, and empty readiness states. Confirm truthful copy, safe errors, and successful retry; do not change source admission to manufacture these states.
11. Exercise an API failure on Customer detail/related work. Confirm no raw backend/provider detail leaks and the stable Customer identity remains usable where already loaded.
12. At practical phone width, verify roster cards, search, pagination, source status, Customer detail, Contacts, Locations, and related-work links have no blocking horizontal overflow and remain keyboard/touch operable.
13. After Migration publishes an accepted admission packet, rerun steps 2–9 and reconcile totals/as-of/digest to that packet. Any remaining difference stays explicitly partial or held.

Record the deployed SHA, authenticated role, Company/Branch, fixture or admitted record IDs, observed totals/as-of, each assertion result, and screenshots only as supporting evidence. A screenshot alone is not acceptance.

## Deferred ownership

Migration owns source identity, admission, held/conflict resolution, and completeness packets. Scheduling owns scheduling behavior. Communications owns Customer communication mutation. Any mismatch in those contracts should be returned to the owning lane with request/response evidence rather than repaired here.
