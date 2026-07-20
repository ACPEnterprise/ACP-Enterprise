# Version 1.0 Production Readiness Checklist

This checklist is the evidence-based gate for production rollout. Each item requires an owner and a link to evidence in the release record. Items marked **Blocker** prevent launch unless executive, product, engineering, operations, and applicable security/finance owners approve a documented exception with a time-bounded mitigation.

## Governance and scope

- [ ] **Blocker:** Release scope and acceptance criteria are approved.
- [ ] **Blocker:** Every launch-critical Housecall Pro workflow has an implement, integrate, migrate, temporarily retain, or retire disposition.
- [ ] QuickBooks system-of-record boundaries and reconciliation ownership are documented.
- [ ] Known limitations, deferred work, and user workarounds are approved and communicated.
- [ ] Release owner, technical lead, migration lead, support lead, and go/no-go authority are named.
- [ ] Change freeze and emergency-change process are active.

## Product and workflow readiness

- [ ] **Blocker:** Customer intake, service location, booking, scheduling, dispatch, field execution, estimate, completion, invoice, payment, and receipt workflows pass acceptance.
- [ ] **Blocker:** Office, dispatcher, technician, manager, and finance roles can complete their required workflows.
- [ ] Cancellation, rescheduling, no-access, declined estimate, failed payment, refund, and correction paths are verified where in scope.
- [ ] Empty, error, offline/degraded, unauthorized, stale, and retry states provide safe user guidance.
- [ ] Required reports, exports, notifications, and operational dashboards are accurate.
- [ ] Supported browser, device, responsive, and accessibility checks pass.

## Security and privacy

- [ ] **Blocker:** Authentication and session controls are production configured.
- [ ] **Blocker:** Role, company, branch, resource, and administrative authorization tests pass.
- [ ] **Blocker:** No known critical or high-severity exploitable vulnerability is open.
- [ ] Secrets are stored outside source control, rotated for production, and access-reviewed.
- [ ] TLS, secure headers, CORS, rate limits, and external callback verification are configured.
- [ ] Sensitive data is excluded from logs, analytics, error responses, and non-production datasets.
- [ ] Administrative, export, role-change, refund, and financial adjustment actions are audited.
- [ ] Dependency, container, code, and secret scans pass under the approved policy.
- [ ] Incident response and credential-revocation procedures are verified.

## Data and migration

- [ ] **Blocker:** Final source-to-target mappings and transformation rules are approved.
- [ ] **Blocker:** At least one full migration rehearsal completed within the cutover window.
- [ ] **Blocker:** Reconciliation covers customers, locations, open jobs, appointments, estimates, invoices, payments, attachments, and other in-scope records.
- [ ] Duplicate, invalid, orphaned, and rejected-record procedures have named owners.
- [ ] Source extraction time, cutoff rules, incremental changes, and write restrictions are defined.
- [ ] Migration scripts are versioned, repeatable, logged, and safe to rerun as designed.
- [ ] Data validation queries and business spot checks are documented.
- [ ] Data retention and secure handling of migration files are defined.

## Database and infrastructure

- [ ] **Blocker:** Production infrastructure is reproducible from reviewed configuration.
- [ ] **Blocker:** Alembic migrations succeed from the production revision and migration state is verified.
- [ ] **Blocker:** Encrypted backup and point-in-time recovery are enabled.
- [ ] **Blocker:** A representative restore has succeeded and recovery evidence is recorded.
- [ ] Production database, application, worker, cache/queue, storage, DNS, and certificate capacity is reviewed.
- [ ] Services run with least-privilege identities and production-safe settings.
- [ ] Health, readiness, graceful shutdown, timeouts, connection pools, and resource limits are configured.
- [ ] Development ports, reload modes, default credentials, and debug output are absent.
- [ ] External dependency limits, credentials, webhooks, and sandbox-to-production switches are verified.

## Application and integration quality

- [ ] **Blocker:** Required CI checks and the release test suite pass on the immutable release artifact.
- [ ] **Blocker:** Payment idempotency and duplicate webhook/callback handling pass.
- [ ] **Blocker:** State and business events commit atomically through the outbox.
- [ ] Event consumers are idempotent and retry/dead-letter behavior is verified.
- [ ] QuickBooks, payment, SMS/email/phone, maps, storage, and other launch integrations pass production smoke tests.
- [ ] OpenAPI and event contracts match deployed behavior.
- [ ] Critical queries and workflows meet approved latency and load targets.
- [ ] No unexplained skipped or flaky critical-path test remains.

## Observability and operations

- [ ] **Blocker:** Logs, metrics, traces, dashboards, and alerts cover critical workflows and dependencies.
- [ ] Request correlation and business-event correlation are visible end to end.
- [ ] Alerts have thresholds, runbooks, routing, escalation, and tested delivery.
- [ ] On-call coverage and vendor escalation contacts cover the cutover and stabilization period.
- [ ] Queue/outbox lag, failed integrations, payment exceptions, migration discrepancies, and job-workflow failures are visible.
- [ ] Deployment, migration, smoke-test, rollback, restore, and common-incident runbooks are accessible.
- [ ] Support intake, severity, triage, status communication, and issue ownership are defined.

## Training and organizational readiness

- [ ] **Blocker:** Role-based training is complete for all launch users or approved delegates.
- [ ] Users know how to obtain support and how to identify a launch-critical issue.
- [ ] Training uses the final workflows and accurately reflects known limits.
- [ ] Office and field devices, connectivity, credentials, printers/scanners, and payment hardware are ready where applicable.
- [ ] Customer-facing templates, phone/SMS/email identities, and support messages are approved.
- [ ] Business continuity procedures are distributed for platform or connectivity loss.

## Cutover and rollback

- [ ] **Blocker:** A minute-by-minute cutover plan lists owners, dependencies, verification, and communication points.
- [ ] **Blocker:** Rollback thresholds, decision authority, latest safe decision time, and data treatment are explicit.
- [ ] **Blocker:** Coexistence rules prevent conflicting updates between ACP Enterprise and Housecall Pro.
- [ ] Final data export, import, reconciliation, deployment, and smoke-test commands are reviewed.
- [ ] Immutable application artifacts, migration packages, and configuration versions are recorded.
- [ ] Internal and external launch, delay, rollback, and recovery communications are prepared.
- [ ] Command-center schedule and stabilization review cadence are confirmed.

## Final approval

- [ ] Product approval
- [ ] Engineering approval
- [ ] Security/privacy approval
- [ ] Operations/dispatch approval
- [ ] Field-service approval
- [ ] Finance/reconciliation approval
- [ ] Executive go/no-go approval
- [ ] Final decision, timestamp, release version, approvers, and evidence location are recorded
