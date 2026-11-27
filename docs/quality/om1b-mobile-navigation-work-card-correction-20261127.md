# OM1-B mobile navigation and work-card correction — 2026-11-27

## Authority and isolation

- Candidate branch: `work/om1b-mobile-responsive-navigation-correction`.
- Exact integrated baseline:
  `6783a78aed1e73dbde1b3ba4787afae47a3fe338` from
  `handoff/p0-final-correction-recovery-6783a78a`.
- The later timestamped OM1-A native-accounting branch is a separate lineage;
  it is not a successor of this combined P0 recovery baseline.
- No protected business data, provider, deployment, Docker environment, or
  supervisor process was read, mutated, started, or reconfigured.

## Correction

The shared application shell now uses a 64rem desktop breakpoint. Below that
breakpoint, the persistent sidebar is absent from layout and the workspace uses
the full viewport width. The hamburger opens a fixed, safe-area-aware modal
drawer with a backdrop, background and horizontal scroll containment, focus
entry and trapping, Escape handling, and focus restoration for dismiss actions.
Destination selection closes the drawer and retains route-focus behavior.
Desktop navigation remains persistent at 1024 CSS pixels and above.

The permission-filtered navigation catalog now includes the existing
Accounting destination. Customers, CSR/Scheduling, Dispatch, Accounting,
Employees, and Payroll remain governed by their existing permission checks.

The owner-approved work-card contract is now centralized as:

- width: exactly `2px`;
- style: `solid`;
- color: `#c01529` through `--semantic-panel-outline` in both themes; and
- radius: the existing component radius remains unchanged.

The shared `Card`, primary work panels, dashboard cards, and the Job Details
invoice panel all consume this contract. Semantic card tones no longer replace
the owner-approved work-card border.

## Automated qualification

- Complete frontend suite: **175 files / 812 tests passed**.
- Mobile shell and router qualification: **2 files / 22 tests passed**.
- ESLint: **PASS**.
- Production Vite build: **PASS**.
- JavaScript syntax and Git whitespace checks: **PASS**.
- Regression coverage asserts the shared token, both theme bindings, global
  selector contract, Job Details usage, permission filtering, modal semantics,
  scroll locking, destination/backdrop/close/Escape dismissal, and focus
  behavior.

## Real-browser qualification boundary

`frontend/tests/mobile-navigation-work-card-real-browser.mjs` performs an
authenticated actual-browser matrix across widths 320, 375, 390, 414, 430,
768, 1024, desktop, and iPhone landscape; light and dark themes; and Company
Setup, Customers, Job Details, CSR, Dispatch, Accounting, Employees, and
Payroll. It checks computed `2px solid` border values, layout width and overflow,
drawer geometry, scroll lock, authorized links, every dismissal path, and emits
representative PNGs with SHA-256 digests.

No isolated application runtime or synthetic credential receipt was listening
on this machine during this qualification. Existing containers are unrelated
database and callback services and were preserved. Therefore the browser
matrix and requested screenshots are **NOT YET EXECUTED**, and this handoff does
not represent them as passed. A sandbox-compatible Chromium 140 headless shell
was located and its executable health check passed.

From a normal host Terminal, Laptop Reviewer can run the matrix against an
already-authorized isolated runtime using a mode-0600 synthetic credential file
and the secret-free receipt produced by that runtime:

```text
OM1B_CHROME_EXECUTABLE=/Users/michaelbfouse/Library/Caches/ms-playwright/chromium_headless_shell-1187/chrome-mac/headless_shell OM1B_SERVING_SHA=<candidate-sha> node frontend/tests/mobile-navigation-work-card-real-browser.mjs <frontend-url> <credential-file> <receipt-file> <output-json> after enforce
```

The output JSON and adjacent `.artifacts` directory are the independent
browser evidence package. This synthetic qualification is not protected All
County acceptance, does not close Owner Acceptance Finding 001, and does not
authorize deployment or production claims.
