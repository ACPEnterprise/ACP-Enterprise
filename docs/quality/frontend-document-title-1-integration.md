# Frontend document title 1 — Enterprise Release handoff

## Candidate

- Starting protected authority: `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`
- Scope: replace the scaffold browser title before JavaScript initializes.
- Deployment performed: no.

## Defect and repair

Both public hostnames serve `<title>frontend</title>` in the static HTML. JavaScript
eventually applies the already-authoritative `ACP Enterprise Command Center` title,
but users, browser history, accessibility tooling and link/document previews can see
the scaffold value during bootstrap or when JavaScript cannot initialize.

The static title now matches the existing platform `applicationTitle`. This does not
rename the Mobile app, introduce new Twelve Hats branding, alter tenant identity or
change routing.

## Acceptance

- Static metadata contract: passed.
- After deployment, both Preview and Beta root/login HTML must contain
  `ACP Enterprise Command Center` and must not contain the scaffold title.
- Production and `app.twelve-hats.com`: untouched.
