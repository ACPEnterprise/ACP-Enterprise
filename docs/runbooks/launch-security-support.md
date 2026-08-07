# Launch Security and Support Runbook

## Authorization incident

1. Record the safe correlation identifier, release, timestamp, Company, and
   Branch. Do not collect session material.
2. Ask an authorized Company Administrator to inspect bounded audit evidence.
3. Classify the denial as authentication, Company membership, permission, or
   Branch access. Do not broaden access merely to diagnose a denial.
4. If a policy correction is required, the Company Administrator uses the
   authenticated Administration workflow. Authorization-version invalidation
   requires normal reauthentication.
5. Confirm the original denied request remains denied until the authorized policy
   change is complete.

## Suspected secret exposure

1. Stop copying or displaying the value. Do not place it in audit details or a
   support ticket.
2. Identify the owning credential workflow from metadata only.
3. Revoke the credential using its approved authority boundary.
4. Issue a replacement only through the owning protected workflow.
5. Validate the old credential fails closed and record only safe identifiers and
   state transitions.

## Cross-tenant or cross-Branch concern

1. Preserve the request correlation identifier and bounded denial evidence.
2. Reproduce with synthetic identifiers in a non-production environment.
3. Verify both Company scope and Branch scope independently.
4. Escalate as a security incident if any foreign resource metadata is returned.
5. Never inspect another tenant's records to prove isolation.

## Support escalation package

An escalation package may contain release identifiers, safe timestamps,
correlation identifiers, route and method, HTTP classification, and redacted
screenshots. It must not contain cookies, authorization headers, tokens, private
keys, environment values, database exports, raw customer records, or unrestricted
logs.
