# Frontend Assets route collision 1 — Enterprise Release handoff

## Candidate

- Starting protected authority: `388226f2`
- Scope: restore the existing owner-facing `/assets` application route on Preview and
  Twelve Hats Beta.
- Schema/API/permission impact: none.
- Preview/Production deployment performed: no.

## Reproduction and root cause

A direct novice-user sweep exercised all 34 concrete frontend routes through both
public hostnames. Thirty-three routes returned the application shell correctly.
`/assets` failed on both hosts:

1. Nginx recognized the physical Vite `/usr/share/nginx/html/assets` directory before
   React Router could load.
2. It returned 301 with an incorrect absolute `http://<host>/assets/` location.
3. The trailing-slash URL then returned 403 because directory listing is forbidden.

This is a route/static-directory collision, not an authorization or React defect. It
blocks the normal owner Assets screen and creates an HTTPS downgrade redirect.

## Repair

Exact `/assets` and `/assets/` requests now serve the SPA entry point. Existing hashed
JavaScript, CSS and image files beneath `/assets/<filename>` still use Nginx's normal
existing-file behavior. No route, API or authorization model was duplicated.

## Acceptance

After the reviewed frontend image is deployed, verify on both Preview and Beta:

- `/assets` returns 200 without redirect;
- `/assets/` returns 200 without directory listing;
- browser refresh and back/forward preserve the Assets screen;
- a current hashed `/assets/index-*.js` response remains JavaScript and cacheable;
- an authenticated authorized owner sees Assets data;
- an unauthorized user remains subject to the existing application authorization;
- all other direct routes remain unchanged.

## Qualification

- Nginx syntax validation using the Preview Docker network: passed.
- Platform connectivity and network-exposure contracts: 10 tests passed.
- No Production or customer-data mutation.
