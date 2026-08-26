# TECH.1 controlled execution boundary

`TECH.1 — Establish technician application shell` is a migration-free,
frontend-only Field Service milestone. The scheduler manifest owns its versioned,
fingerprinted execution boundary. Scheduler reconciliation copies that contract
into the durable milestone evidence; the owner Start path validates the identity
and fingerprint before composing an Engineering Command.

The approved implementation surface is the technician feature, route, API, hook,
and type modules, the exact shared router/navigation integration files, and this
technician architecture documentation. The exact shared shell files are
`frontend/src/layout/navigation.ts`, `frontend/src/layout/navigation.test.ts`,
`frontend/src/layout/Sidebar.tsx`, and `frontend/src/layout/types.ts`. The type
file is the closed navigation identity contract; the Sidebar is the established
permission-aware projection boundary. No other `frontend/src/layout/**` path is
implied. Backend code, Alembic migrations,
deployment and infrastructure files, credentials, environments, and unrelated
product modules are outside the boundary.

`frontend/src/layout/ApplicationShell.tsx` remains deliberately excluded. The
pre-existing application-shell architecture requires feature routes to register
beneath the shell and explicitly says shell structure must not change merely to
add a module. Technician navigation scope therefore belongs in the approved
route metadata, navigation catalog, Sidebar, and closed layout-type contract.

The bounded execution may inspect, modify, validate, commit, perform safe
mechanical reconciliation, and push normally. It may not deploy Preview or
Production, import or cut over data, force-push, resolve semantic conflicts, or
perform irreversible operations. Its provider validation contract is `git diff
--check`, ESLint, and TypeScript production validation. Device-oriented and
focused frontend tests remain required completion evidence in the milestone
instruction and provider completion evidence.

Changing this scope requires a new boundary version and fingerprint in the
authoritative scheduler manifest. A Ready code-changing scheduler milestone
without a valid boundary remains fail-closed.

## Shell contract

The technician destination is `/technician` and is exposed only when the active
Company authorization context includes `COMPANY_JOB_EXECUTE`. The route repeats
that check and redirects unauthorized direct navigation to the authenticated
landing page. A role label, title, or client-side assignment filter does not
grant access.

The shell reads `GET /api/v1/technician/itinerary?service_date=YYYY-MM-DD` as a
typed, assignment-scoped projection. It deliberately does not reuse the broad
Dispatch board or filter Company-wide records in the browser. The response is
ordered by the authoritative service window and contains only minimum visit,
Job, customer display, location display, assignment, and arrival context. API
authorization remains authoritative; the frontend guard is defense in depth.

The experience uses the existing application drawer and focus-restoration
behavior. Visit cards and date controls retain 44-pixel-or-larger touch targets,
single-column phone layout, semantic itinerary ordering, labelled loading and
error feedback, and a truthful empty state.

The Day-1 field-execution successor is governed by the separate
[Technician Day-1 Field Execution Contract](tech-field-day-1-contract.md). It
may not begin until this TECH.1 shell is owner-accepted and integrated; the
successor contract does not authorize changes to an active TECH.1 worktree.
