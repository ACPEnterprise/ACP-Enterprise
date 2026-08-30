# CRM Customer Experience program

## Authority boundary

Customer remains the authority for identity, Contacts, Service Locations,
internal notes, lifecycle, and recorded communication-consent evidence. Jobs,
Scheduling, Estimates, Invoices, and Payments remain separate authorities and
are composed into Customer 360 only through their scoped read contracts.

The Customer timeline consumes the Company-scoped Customer timeline API. It
does not query an unscoped generic event feed and exposes only the API's safe
event summary, actor display name, and timestamp.

## Operator capabilities

- active Customers may be edited or archived; archived Customers retain their
  history and may be explicitly restored through the accepted lifecycle API;
- Contacts and Service Locations remain Customer-bound and Company-isolated;
- the operational workspace composes authorized Estimate, Job, Appointment,
  Invoice, and Payment status without importing their authority into CRM;
- duplicate review uses normalized evidence from the accepted duplicate-check
  contract, excludes the current record, and never performs an automatic merge;
- communication readiness distinguishes missing recipient, recorded grant,
  recorded withdrawal, and preference not established. It does not infer legal
  consent, provider availability, or deliver a message.

## Explicit gates

Native Customer consolidation, survivorship, householding, marketing consent
policy, public Customer portal access, and real communication delivery remain
outside this boundary. A possible duplicate is review evidence only. Production
policy values remain unconfigured until separately authorized.

## Communications composition

Customer 360 may read the provider-neutral Communications history through an
explicit `customer_id` filter. The repository applies Company scope first and
then the Customer evidence filter; Branch remains an optional authorization
scope. The UI exposes delivery state, safe recipient evidence, retry count, and
terminal-review state. It provides no send, retry, cancel, provider, or template
mutation controls.

## Qualification

Frontend tests cover archive confirmation, restore, safe timeline rendering,
communication readiness, duplicate review, and the absence of merge controls.
Database-backed Customer isolation and lifecycle suites remain part of
integrated qualification when PostgreSQL is available.
