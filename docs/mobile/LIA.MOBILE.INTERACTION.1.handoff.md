# LIA.MOBILE.INTERACTION.1 — Mobile-to-Enterprise Intelligence Handoff

Status: `SERVER_REQUIRED` before an ACP Employee LIA surface can be enabled.

## Current authority inspected

- Protected branch: `origin/customer-management-v1`
- SHA: `a65a104c21282fd8f94a2e9bac37ba576a91a75c`
- Current ACP Employee Mobile tree contains no LIA client, route, capability,
  native voice dependency, microphone permission, or speech playback.

## Contract boundary

Enterprise currently exposes `POST /api/v1/lia/ask`, plus readiness and briefing
routes. The service is a governed owner-oriented assistant: its source registry
includes Customer, Job, Scheduling, Dispatch, Estimates, Invoices, Payments,
Accounting, Payroll, Inventory, Assets, Price Book, Workforce, Beacon, and other
domains. Selection is based on the authenticated principal's permissions, not on
an Employee-assignment-safe Mobile product contract.

ACP Employee must not call this endpoint directly. A Job UUID or navigation context
cannot grant access, and client-side filtering cannot make a broad response safe.

## Required Enterprise.Intelligence contract

Provide an employee-safe, read-only route (name/version chosen by Enterprise) that:

1. resolves authenticated User → Membership → active Employee server-side;
2. requires an explicit Employee Mobile/LIA read permission;
3. scopes Company and authorized Branches;
4. optionally accepts a Job/Appointment context but revalidates the current
   assignment on every request;
5. allowlists employee-safe sources and fields;
6. excludes Payroll values, Accounting, margins/costs, payments, office notes,
   unrestricted Customer history, credentials, and foreign assignments;
7. returns classification, answer, limitations, source authority, as-of/freshness,
   evidence digest, authorization version, and safe navigation only;
8. fails closed for foreign, stale, removed, or reassigned Job context;
9. preserves no transcript by default unless a separately approved retention policy
   exists;
10. treats voice/transcript input as a transport concern, not a second intelligence
    engine.

The likely initial sources are the employee's current My Day/assigned Job, bounded
Service Location context, and approved operational status. Enterprise should decide
the permission code, safe question vocabulary, context contract, and retention/
privacy policy before Mobile implementation.

## Mobile follow-on after contract acceptance

Mobile will add a centralized typed client and permission-derived text-only “Ask
LIA” surface. It will preserve existing authentication/session, Branch and
assignment authority, stale/error/retry behavior, and back navigation to My Day or
Job Workspace. Voice input and spoken playback remain separately gated and will use
the same accepted LIA authority.

No Mobile feature, API, schema, Apple configuration, Preview deployment, or
Production change was made by this handoff.
