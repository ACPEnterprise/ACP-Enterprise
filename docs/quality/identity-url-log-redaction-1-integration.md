# Identity URL log redaction 1 — Enterprise Release handoff

## Candidate

- Starting protected authority: `9dbdea7933a69ea8b147a63ed6cc6437d5401825`
- Scope: prevent single-use activation and password-reset URL material from entering
  Preview/Beta edge access logs or same-origin referrers.
- Authentication, token, schema and delivery behavior: unchanged.
- Preview/Production deployment performed: no.

## Proven boundary defect

Identity delivery intentionally creates `/activate?token=...` and
`/reset-password?token=...` URLs. Both frontend routes copy the token into component
state and remove it from browser history after React loads. That is too late for the
initial Caddy/Nginx request, and the global `strict-origin-when-cross-origin` policy can
allow the complete secret-bearing URL to appear as the referrer of same-origin static
asset requests made before the effect runs.

No real token was used or printed during diagnosis.

## Repair

On both Preview and Beta, Caddy now:

- skips access logging for exact `/activate` and `/reset-password` page requests; and
- sets `Referrer-Policy: no-referrer` for those responses before any subresource loads.

Frontend Nginx also suppresses access logging for the two exact SPA entry routes. API
requests, failures and all secret-free identity evidence retain normal observability.
The existing frontend history replacement remains defense in depth.

## Acceptance

Enterprise Release must validate/reload Caddy and deploy the reviewed frontend image,
then use a sanctioned disposable Preview identity token without including it in shell
arguments or retained test output. Confirm the page receives `no-referrer`, activation
or recovery works once, replay fails, and the token is absent from Caddy, Nginx,
application and audit logs. Do not use a real employee merely for this test.

## Qualification

- Caddy candidate validation: passed.
- Nginx candidate validation: passed.
- Focused edge security contracts: 7 tests passed; Ruff, formatting and diff checks
  passed.
- Production and `app.twelve-hats.com`: untouched.
