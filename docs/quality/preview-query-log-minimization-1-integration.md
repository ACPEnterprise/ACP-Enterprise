# Preview query-log minimization 1 — Enterprise Release handoff

## Candidate

- Starting protected authority: `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`
- Scope: minimize Preview/Beta container access telemetry without weakening request
  correlation or application security evidence.
- API, schema, authorization and customer data: unchanged.
- Preview/Production deployment performed: no.

## Proven defect

A harmless synthetic request to
`/api/v1/customers?search=edge-query-canary-not-real` was correctly rejected with 401,
but both frontend Nginx and Uvicorn retained the complete query string. Real routes use
queries for search text, Employee/Customer context, scheduling filters and identity
recovery. The current duplicated access output therefore exceeds the documented
sensitive-data logging boundary.

The synthetic canary contained no customer or credential material.

## Repair

Frontend Nginx now emits a JSON access record containing only timestamp, remote
address, request ID, method, normalized path, status, response bytes and duration. It
does not retain arguments, raw request targets, referrers or user agents.

Uvicorn's duplicate access logger is disabled in the Preview backend image. Nginx
remains the authoritative request access boundary; application logs, fixed security
decisions, correlation middleware, Caddy errors and audit evidence remain available.

Exact activation/reset request suppression from the prior identity repair remains in
place in addition to the path-only general policy.

## Enterprise acceptance

After deploying the coherent frontend/backend/Mission Control images:

1. Send harmless synthetic query canaries through Preview and Beta.
2. Confirm path/status/request ID remain in Nginx output.
3. Confirm the canaries are absent from Nginx and backend output.
4. Confirm failed authorization and application exceptions retain fixed safe codes and
   correlation without raw query values.
5. Confirm health, CORS, sessions, worker transport and Mission Control remain healthy.

## Cross-domain observation

The runtime sweep also proved a Workforce defect at
`GET /api/v1/workforce/employees/{employee_id}/timeline`: `Role.display_name` is read
at `employee_timeline.py:127/140`, but the authoritative Role model exposes `name`.
This produces repeated HTTP 500 responses. Workforce should replace the nonexistent
property and add a real-model regression test; no Workforce code is changed here.

## Qualification

- Focused access-log and Beta connectivity contracts: 8 tests passed.
- Nginx syntax and container-image command inspection: passed.
- The broader HTTP authentication module could not collect under the workstation's
  Python 3.9 because protected source uses Python 3.10+ union syntax; this candidate
  does not change authentication code.
- Production and `app.twelve-hats.com`: untouched.
