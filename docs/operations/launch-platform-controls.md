# Launch Platform Controls

## Purpose

PLAT.1 closes the minimum authorization, audit, secrets, and support boundaries
required for launch. These controls do not create Roles or grants automatically.
Company owners remain responsible for assigning the least privilege needed in
their Company and Branch scope.

## Launch role matrix

| Role | Intended authority | Explicit exclusions |
| --- | --- | --- |
| Company Administrator | Company access-policy administration and Company audit review | No Platform operator, worker credential, repository, or production authority |
| Office Manager | Customer, schedule, Job, Dispatch, Price Book, analytics, and audit operations in assigned Branches | No Role administration, worker control, or tenant impersonation |
| Dispatcher | Customer read, Scheduling, Job coordination, Dispatch assignment, and Price Book read in assigned Branches | No Price Book mutation, audit access, or access-policy administration |
| Technician | Customer/Scheduling context read and Job execution in assigned Branches | No Dispatch assignment, commercial mutation, or audit access |
| Auditor | Company audit and analytics read in assigned Branches | No operational mutation |
| Support | No standing tenant permissions | No tenant impersonation, credential access, or direct database access |

Permission grants never expand Branch access. A user must have both the named
permission and explicit access to the targeted Branch. For restricted members,
audit queries return only records explicitly attributed to authorized Branches.
Company-level audit records require all-Branch access.

## Audit access boundary

`COMPANY_AUDIT_READ` permits the authenticated Company member to read bounded
audit evidence through `GET /api/v1/platform/audit`. Results are Company scoped,
newest first, and limited to 100 records. A requested Branch outside the caller's
authorized Branch set fails closed. Restricted members cannot see audit evidence
from other Branches.

The response excludes IP addresses and user-agent strings. Audit detail payloads
are admitted only after recursive sensitive-key validation and must never contain
passwords, tokens, cookies, authorization headers, API keys, private keys,
credentials, or secrets.

## Secrets boundary

- Secrets belong only in approved protected runtime configuration or credential
  stores; never in source, audit payloads, Business Events, support tickets, logs,
  screenshots, exports, or browser responses.
- Support personnel must never ask an owner to paste a password, token, cookie,
  authorization header, private key, recovery code, worker credential, or
  environment file.
- Credential validation reports only bounded state and a correlation identifier.
- Suspected exposure requires revocation and replacement through the owning
  credential workflow. Never copy a credential to diagnose it.

## Support boundary

Support has no standing Company Role and no tenant impersonation path. Support
may use owner-provided, non-sensitive evidence and correlation identifiers.
Authorized Company personnel execute any tenant-scoped read or mutation and
remain accountable in audit evidence.

Permitted support evidence:

- public release identifier and application version;
- bounded health state and timestamps;
- correlation identifier;
- owner-redacted screenshot;
- documented error classification;
- Company/Branch identifiers when required for authorized escalation.

Prohibited support access:

- direct PostgreSQL or Redis mutation;
- session or credential extraction;
- permission grants or Branch-access changes on behalf of an owner;
- production shell, deployment, worker, Git, or repository authority;
- raw customer exports, unrestricted logs, or repository contents.

## Review checklist

1. Confirm the caller is authenticated in the intended Company.
2. Confirm the operation has a named permission.
3. Confirm the target Branch is in the caller's authorized Branch set.
4. Confirm denial behavior does not reveal cross-tenant existence.
5. Confirm audit evidence contains no sensitive keys.
6. Confirm support evidence is bounded and owner-mediated.
7. Confirm no automatic grant, impersonation, or break-glass bypass was added.
