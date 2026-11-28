# OM2 CSR, Scheduling, and Dispatch P0 Handoff — 2026-11-28

## Verdict

**FAIL — authenticated browser acceptance is blocked by the available Chrome runtime.**

The candidate application passed the complete authenticated HTTP workflow in a disposable working-company replica. It is not represented as 100% operationally accepted because neither the CSR nor technician rendered-browser gate could launch Chrome in this workspace.

## Candidate composition

- Branch: `work/om2-csr-scheduling-dispatch-p0`
- Integrated application baseline: `7ecc0722`
- Technician eligibility/My Day correction composed as: `dc8272d8`
- Runtime: production backend and frontend images, PostgreSQL, and Redis assembled with `docker-compose.application-acceptance.yml`
- Disposable loopback URL used for qualification: `http://127.0.0.1:18184`
- No hosted All County company, historical HCP record, real notification channel, or deployment was touched.

## Passed qualification

The expanded `scripts/application-integration-acceptance.py` gate passed against a clean disposable database and verified:

- authenticated owner/company/branch discovery and tenant isolation;
- creation of an identified test customer and service location;
- recording the service request on a new job and activating the job;
- appointment creation and qualified technician onboarding/readiness;
- eligibility evaluation and assignment of the technician;
- appointment rescheduling with `reschedule_count == 1`;
- assignment continuity after rescheduling;
- customer search returns the exact created customer;
- the daily dispatch board contains the exact appointment, scheduled status, and technician assignment;
- the technician's authenticated My Day contains the exact appointment and job;
- fresh CSR and technician login/readback;
- repeat CSR and technician login/readback after a backend restart.

Observed results:

```text
PASS initial authenticated workflow
PASS fresh CSR session readback
PASS fresh technician session readback
PASS backend restart
PASS post-restart CSR session readback
PASS post-restart technician session readback
PASS ruff scripts/application-integration-acceptance.py
PASS Python syntax compilation
PASS production frontend/backend image builds and health checks
```

The disposable receipt and credential files were mode `0600`. Test identities use `example.test`/`example.invalid`; no real customer notification was possible.

## Outstanding failure

Both existing rendered-browser gates failed before making an application request:

```text
CSR_BROWSER_EXIT=1        ECONNREFUSED 127.0.0.1:19422
TECHNICIAN_BROWSER_EXIT=1 ECONNREFUSED 127.0.0.1:19423
```

The installed Google Chrome 158 process exits with status 134 before opening its DevTools endpoint. A direct headless launch reproduced the abort, and no alternate Chromium-compatible executable is installed. The assembled application remained healthy and its authenticated HTTP gates continued to pass.

The host-side focused pytest attempt could not collect because the available isolated virtualenv lacks application dependencies (`httpx` and `fastapi`). This does not replace or invalidate the successful production-image runtime qualification, but it is recorded as an outstanding qualification-environment failure.

## Integration action

Laptop Master may integrate this non-protected candidate, assemble it in a browser-capable disposable environment, and run:

```text
node frontend/tests/real-browser-workflow.mjs BASE_URL OWNER_CREDENTIALS RECEIPT OUTPUT final
node frontend/tests/technician-my-day-real-browser.mjs BASE_URL TECHNICIAN_CREDENTIALS RECEIPT OUTPUT final
```

Operational acceptance becomes PASS only when both rendered-browser commands pass from authenticated CSR and technician perspectives. No deployment is authorized by this handoff.
