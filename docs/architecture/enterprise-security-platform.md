# Enterprise Security Platform

## Purpose and Boundaries

The Enterprise Security Platform provides operational security controls shared by every ACP Enterprise module. It hardens established authentication, authorization, and company-administration architecture without introducing business functionality or bypass paths.

Authentication establishes global User identity and Session validity. Authorization resolves tenant Membership, Branch scope, Roles, and Permissions. Company administration mutates access policy through its centralized service. Enterprise Audit records security-sensitive activity. Business Events remain an independent integration stream describing business activity.

## Authentication Flow

Authentication verifies an active User and usable password Credential, creates a version-bound Session, issues a short-lived signed access token, and creates a hash-only rotating refresh credential. Authentication outcomes produce operational authentication security events and Enterprise Audit records in the relevant database transaction.

Access tokens carry `kid`, issuer, audience, User subject, Session identifier, credential version, authorization version, issue/expiry timestamps, and token identifier. The server selects the validation key by an allowlisted configured `kid`; unknown identifiers are rejected. The configured active key signs new tokens while older configured keys continue validating existing tokens during a controlled rotation window. Removing an old key ends that validation window. Rotation automation and asymmetric key distribution remain future operational work.

Refresh rotation locks the presented token and Session, consumes the current token once, and creates its linked replacement atomically. Replay compromises the Session and token family. Password change and reset increment credential versions and revoke Sessions. Redis-backed authentication rate limiting fails closed: when Redis is unavailable, protected authentication requests return a temporary-unavailability response rather than proceeding without safeguards.

## Authorization Flow

The authenticated identity dependency validates the access token and version-bound Session. The authorization dependency then resolves the active Company, active Membership, authorized Branches, effective Roles, and effective Permissions. Reusable dependencies enforce required Permission and Branch access. Business services consume the resulting `AuthorizationContext` and do not recalculate access.

Denied decisions return generic 403 responses while a structured internal record captures timestamp, actor, Company, Branch, requested Permission, resource, and controlled denial reason. Denial reasons never include credentials, tokens, or arbitrary exception text. Authorization infrastructure failures do not grant access.

## Company Administration

Company administration remains the only mutation boundary for Membership lifecycle, Branch access, Role assignment, and Role Permission assignment. Mutations are Company-scoped, use PostgreSQL row locking, increment affected Users' authorization versions, enforce final-administrator protection, and stage Business Events and Audit Records independently in the same transaction.

## Enterprise Audit Architecture

`AuditService` stages immutable `AuditRecord` rows for authentication, recovery, verification, logout, Membership, Branch-access, Role, Permission, and company-administration activity. Records include action, outcome, timestamp, actor when known, tenant and Branch when applicable, resource identifiers, correlation identifier, controlled reason code, network metadata, and non-sensitive details.

Audit rows intentionally do not use business-history foreign keys, allowing evidence to survive later archival and preventing identity deletion rules from erasing history. PostgreSQL rejects UPDATE and DELETE through an immutability trigger. Application validation prohibits sensitive detail keys including passwords, hashes, tokens, secrets, and credentials. The audit ledger is not an event bus and Business Events are not compliance evidence.

Security-sensitive mutations fail closed when their transactional audit write fails. Authentication failures that reach the database record their audit evidence transactionally. If PostgreSQL itself is unavailable, the operation cannot authenticate, authorize, mutate policy, or record audit evidence and therefore fails.

## Security Metrics

Security telemetry is exposed through a centralized adapter boundary rather than module-specific counters. Initial counters cover authentication outcomes, authorization denials, rate-limit denials and unavailability, recovery and password activity, refresh rotation and replay, email verification, and company-administration operations. The in-process implementation is deterministic and testable; a future exporter can forward the same boundary to Mission Control or an external metrics system.

Metrics are operational signals, not authorization inputs or audit evidence. Metrics exporter failure must not grant access or weaken a security decision. Security transactions remain authoritative even when telemetry delivery is degraded.

## HTTP Security Headers

Responses use configurable secure defaults:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- a restrictive Content Security Policy
- a restrictive Permissions Policy
- HSTS on HTTPS responses when enabled

Production configuration requires security headers and HSTS. CSP may be extended narrowly for explicitly approved frontend assets; broad wildcard sources and `unsafe-eval` require security review.

## Trusted Proxy Deployment

Forwarded headers are disabled unless `TRUST_FORWARDED_HEADERS` is enabled and `TRUSTED_PROXY_CIDRS` contains the direct reverse-proxy networks. Requests carrying `X-Forwarded-For` or `X-Forwarded-Proto` from any other direct peer are rejected. Forwarded IP values and protocols are parsed strictly.

Configure only networks controlled by ACP Enterprise infrastructure, such as the private addresses of Nginx, Traefik, DigitalOcean load balancers, or a verified Cloudflare egress range. Never configure `0.0.0.0/0` or `::/0`. Keep load-balancer network lists current through deployment configuration, not application-code edits.

## Permission Catalog

Future modules register stable Permission definitions through the centralized catalog. Startup validation rejects duplicate or malformed codes, blank definitions, and scope-prefix mismatches. Company capabilities use `COMPANY_`; platform-operator capabilities use `PLATFORM_`. Reserved company-administration codes cannot be reclassified as platform capabilities. Permission catalog validation does not create tenant Role assignments or implicit administrators.

## Infrastructure Failure Modes

| Component | Expected behavior |
| --- | --- |
| PostgreSQL unavailable | Startup or request fails; identity, authorization, policy mutation, and audit writes do not proceed. |
| Redis unavailable | Rate-limited authentication/recovery requests return 503; the safeguard is not bypassed. |
| Audit write unavailable | Security-sensitive transactional operation rolls back and fails; no partial policy mutation is accepted. |
| Metrics unavailable | Security operation and audit evidence remain authoritative; telemetry degradation is reported operationally and never grants access. |

## Production Hardening Checklist

- Supply a production-only JWT key ring and active `kid` through secret management.
- Supply a distinct high-entropy security-token HMAC key.
- Remove retired JWT keys only after the maximum active-token validation window.
- Enable security headers and HSTS after HTTPS termination is verified.
- Configure only exact trusted proxy networks and validate the real client IP in staging.
- Keep Redis and PostgreSQL health alerts connected to Mission Control.
- Restrict direct database privileges so application roles cannot disable audit immutability controls.
- Back up and retain audit records according to the approved compliance policy.
- Alert on authentication failures, refresh replay, authorization denials, rate-limit denials, and final-administrator protection events.
- Validate the Permission catalog during every deployment startup.
- Exercise database, Redis, proxy, and key-rotation failure drills before production rollout.
- Review CSP changes and proxy CIDR changes as security-sensitive configuration changes.
