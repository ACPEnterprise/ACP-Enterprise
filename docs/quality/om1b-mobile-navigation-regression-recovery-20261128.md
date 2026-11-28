# OM1-B mobile navigation regression recovery — 2026-11-28

## Root cause

Two independent lineage checks explain why the November 27 correction is not
effective in the hosted application:

1. The published correction
   `7105ab8a2bbdbded418f1c3d2f975496289f2375` is not an ancestor of the current
   P0 handoff `5d2e46b9db953f41c6cb084949de7537ef060352`. Their merge base is the older
   `6783a78aed1e73dbde1b3ba4787afae47a3fe338`. The handoff advanced along a
   separate customer-history lineage and omitted the mobile candidate.
2. A read-only request to `https://preview.allcountyhomeservices.com/` returned
   `assets/index-BVLtwvDa.js` and `assets/index-DbALZJeK.css`, both served by an
   index with `Last-Modified: Wed, 07 Oct 2026 01:17:30 GMT`. The hosted server
   is therefore serving an artifact that predates the November correction. This
   is server-side artifact identity evidence, not an inference from an iPhone
   cache.

The hosted JavaScript contains an earlier navigation implementation. It does
not contain the recovered modal identity, inert application shell, robust
scroll lock, explicit mobile/desktop navigation variants, or the shared shell
CSS introduced by the approved correction.

## Recovery

- Isolated branch: `work/om1b-mobile-navigation-regression-recovery`.
- Exact baseline: `5d2e46b9db953f41c6cb084949de7537ef060352`.
- The approved shared navigation implementation was reapplied without changing
  the integrated customer-history work.
- Below 1024 CSS pixels, the desktop sidebar is both structurally marked
  `hidden lg:flex` and explicitly hidden by the shared stylesheet. The shell
  reserves zero sidebar width and the workspace occupies the full viewport.
- The hamburger opens a fixed modal drawer outside the inert application shell.
  Destination selection, backdrop activation, close control, and Escape all
  close it. Dismiss actions restore trigger focus.
- The body, document element, and workspace are scroll-locked while the drawer
  is open. Horizontal overflow is contained at the document root.
- Header, workspace, drawer, and close control consume the existing iPhone
  safe-area tokens.
- Desktop navigation remains persistent at 1024 CSS pixels and above.
- Existing authorization filtering remains the source of visible navigation;
  the existing Accounting destination is restored to its permission-aware
  navigation group.

## Qualification

- Customer, Job Details, Accounting, navigation, router, and CSS contract
  qualification: **5 files / 34 tests passed**.
- Complete frontend regression: **175 files / 815 tests passed**.
- Production TypeScript/Vite build: **PASS**.
- Changed-file ESLint, JavaScript syntax, and Git whitespace: **PASS**.
- Repository-wide ESLint has one baseline failure outside this changeset at
  `HistoricalCustomerSearch.tsx:26` (`react-hooks/set-state-in-effect`). The
  integrated HCP/customer-history component was not changed.

`frontend/tests/mobile-navigation-shell-browser.mjs` mounts the real shared
React shell and production CSS with synthetic authorization, starts a local
Vite server, and checks customer, job, and accounting routes at 320, 375, 390,
414, 430, and 844×390 iPhone-compatible viewports plus 1024 and 1440 desktop.
It validates full-width content, no horizontal overflow, overlay geometry,
safe-area insets, scroll lock, route-selection dismissal, backdrop dismissal,
and desktop preservation, with representative screenshots and digests.

The managed Codex environment cannot launch a browser UI process: Chromium 140
fails at macOS `MachPortRendezvousServer` registration with permission denied,
and SafariDriver is unavailable. Therefore engine-level browser execution is
an explicit external gate and is not represented as passed. Laptop Reviewer
can execute the secret-free local matrix in a normal Terminal with:

```text
cd /Users/michaelbfouse/Development/ACP-Enterprise-OM1B-Mobile-Recovery/frontend && node tests/mobile-navigation-shell-browser.mjs /private/tmp/om1b-mobile-navigation-recovery-evidence.json
```

This recovery performed no hosted write, deployment, protected-data access, or
QuickBooks access. Integration and deployment remain Laptop Master authority.
