# Workforce Employee access/history route defect — Enterprise handoff

## Authority and reproduction

- Starting protected authority: `a109743968fc764fc1885ecf8fbd4abeb87846d7`
- Broken card destination: `/workforce?employee=<employee-id>`
- Browser result: application not-found route because `/workforce` is not registered.
- Canonical destination: `/employees?employee=<employee-id>`
- Root cause classification: stale route.
- Subject identifier: the card already supplied the canonical ACP Employee ID. No User, Membership, or other identifier substitution was involved.

The router registers the Employee workspace at `/employees`. `WorkforceRoute` reads the `employee` query parameter and uses it to load the selected Employee detail, administration state, and authorized timeline.

## Authorization and data boundary

The existing Office Manager launch role includes `COMPANY_WORKFORCE_READ`. Workforce read endpoints continue to require that permission and resolve records within the caller's Company and authorized Branch scope. This candidate changes no permissions, roles, identity records, authorization versions, backend contracts, or data.

The existing Employee workspace continues to control Payroll navigation and does not expose protected Payroll values. Unauthorized, cross-Company, and cross-Branch access remain governed by the existing backend authorization boundary.

## Candidate change

The Workforce real-roster card now links to:

`/employees?employee=<employee-id>`

Coverage verifies both a field Employee card and Lianne's Office Manager card, direct URL loading and refresh-compatible routing, selected Employee query preservation, active navigation, and browser back/forward behavior. The existing responsive card/link layout is unchanged.

## Qualification

- Focused frontend tests: 4 files, 22 tests passed.
- TypeScript production build: passed.
- ESLint with zero warnings: passed.
- Backend code inspection: Office Manager Workforce read permission, permission-gated endpoints, Company-scoped Employee lookup, and Branch-scoped directory behavior preserved.
- Backend focused test attempt: blocked at collection because the host `python3` is Python 3.9 and cannot parse the repository's Python 3.10+ union type syntax. No backend code changed.

## Preview retest after integration and deployment

1. Sign in as Lianne with her existing Preview credentials.
2. Open **Employees & Time** and locate Lianne's Workforce card.
3. Select **Open access, capabilities and history**.
4. Confirm the browser opens `/employees?employee=<Lianne Employee ID>` without a not-found page.
5. Confirm Lianne's authorized account/access, Membership, MAIN Branch, roles, Mobile readiness, Workforce profile, and timeline appear.
6. Confirm protected Payroll values do not appear.
7. Refresh the URL, then exercise browser back and forward; confirm the same selected Employee context is retained.
8. Repeat from one other authorized Employee card.

No Preview or Production deployment was performed by this lane.
