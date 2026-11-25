# OM2 browser history acceptance

Assignment `OM2-BROWSER-HISTORY-ACCEPT-03` was run in a fresh Vitest/jsdom
browser process against the composed historical-detail and QBO-navigation task
commits. Evidence classification is **synthetic isolated acceptance**.

Accepted browser contracts:

- historical Customer search remains separate from native Customer admission;
- actual source-backed Location, Job, Appointment, Estimate, Invoice, Payment,
  and Refund detail renders with provider identities;
- missing relationships render as held evidence rather than inferred links;
- QBO accounts, bills/vendors, invoices, payments, and reports expose source
  identity and provenance;
- report detail remains read-only, QBO authoritative, not ACP-posted;
- no edit, admission, provider-write, OAuth, or posting control is present.

Qualification: 2 test files / 5 tests passed, focused ESLint passed, TypeScript
passed, and the production Vite build completed. This is not protected-source,
live All County, deployment, or financial acceptance. Tenant isolation remains
enforced by the authenticated server contracts and was not replaced by the
synthetic browser fixture.
