# Commercial Sales non-Production completion

The Commercial Sales boundary composes immutable Price Book snapshots with governed Estimate revisions. It does not recognize revenue, calculate profitability, collect payment, or deliver a Customer communication.

## Operator workflow

1. Configure Branch Commercial readiness. Unknown Company values remain `UNCONFIGURED`; ACP does not assume discount, expiration, tax, template, delivery, or follow-up cadence policy.
2. Select an authorized Customer, optional service location, and active Price Book service. The application creates the immutable commercial snapshot and then the Estimate revision.
3. Preview the deterministic HTML artifact. Draft output is visibly marked; issued revisions remain distinguishable by revision and digest.
4. Record presentation, then prepare protected Customer access. The API returns the access credential once, stores only its HMAC digest, never puts it in a URL, and performs no provider delivery.
5. Record provider-neutral follow-up work. Missing cadence remains explicit and does not prevent manually governed work.
6. A protected Customer view requires the credential header and the exact non-expired, non-revoked current revision. A decision binds that revision and presentation. Equivalent replay returns existing authority; contradictory or stale decisions fail closed.
7. Inspect the pipeline, aggregate Commercial metrics, and immutable Commercial timeline. Estimate value is labeled Commercial value, never recognized revenue.

## Synthetic Preview rehearsal

Use synthetic Company, Customer, location, Price Book, and recipient data only:

- activate a synthetic Price Book version and create a multi-option snapshot;
- create an Estimate without discount, then exercise a synthetic active `permitted` discount policy within its explicit limit;
- present and render the exact revision;
- prepare protected access without invoking email or SMS;
- view with `X-Estimate-Access-Token`, record an exact-revision decision, and replay it;
- verify contradictory and superseded-revision decisions return controlled conflicts;
- create, snooze, and complete follow-up evidence, then inspect the queue and timeline;
- convert an accepted Estimate once and verify replay produces no second Job;
- confirm the aggregate report separates accepted, outstanding, and converted evidence by currency.

Preview deployment and provider delivery remain centralized integration responsibilities. Production communication, payment, legal terms, and Company policy values are outside this boundary.
