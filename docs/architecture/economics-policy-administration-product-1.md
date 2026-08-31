# Economics policy administration product

`ECONOMICS.POLICY.ADMINISTRATION.PRODUCT.1` composes existing Business Economics authority into a read-only owner administration experience. It does not calculate economic results, select policy, or mutate source domains.

## Product contract

The `/business-economics/administration` workspace answers four bounded questions:

1. Which admitted source categories are available, partial, unavailable, stale, conflicting, or policy-blocked for the selected period?
2. Which registered finance-policy families have accepted authority, and which still require an explicit owner decision?
3. Which immutable policy versions and safe policy snapshots exist?
4. Which immutable profitability result is current, what did it supersede, and why?

The readiness projection reuses the authoritative ten-source Economics matrix: revenue, settlement, direct labor, employer burden, materials, other direct costs, overhead allocation, Job identity, service category, and Accounting evidence. Missing values are never displayed as zero.

## Policy and allocation decisions

The service reads the canonical policy-family registry and Company policy evidence. It exposes strategy identifiers and required/configured parameter keys, but not protected values. An unconfigured or deferred allocation policy is presented as `OWNER_DECISION_REQUIRED`; ACP does not preselect an All County allocation method or invent weights.

This release deliberately has `mutation_authority: none`. Policy creation, approval, retirement, and supersession remain with the accepted policy-authority workflow and permissions.

## History and truth layers

Policy history exposes effective dates, current/historical classification, supersession identity, definition version, decision-evidence digest, and policy digest. Profitability history uses the existing append-only result and supersession authority. Company and active-Branch authorization is resolved by the server before lineage is returned.

Navigation preserves the authority boundary:

```
Economics immutable result -> Luminary interpretation -> read-only LIA question
```

Economics owns measured truth. Luminary does not replace that truth, and LIA has no Economics mutation authority.

## Authorization and safe output

- `COMPANY_ECONOMICS_POLICY_READ` gates the administration workspace and projection.
- `COMPANY_ECONOMICS_MEASUREMENT_READ` separately gates profitability-result history.
- Company and Branch scope come from the authenticated authorization context; clients cannot supply either scope.
- Cross-scope and unknown result identities use the same safe not-found response.
- The projection contains IDs, states, counts, versions, and digests. It excludes policy values, Payroll details, protected source payloads, credentials, and tokens.

## Responsive behavior

Readiness and policy cards are single-column at phone width and expand at larger breakpoints. Period and result-history forms stack on phone width. Wide policy history remains usable through horizontal containment rather than shrinking text below the design-system baseline.

## Qualification and integration packet

Qualification covers permission denial, truthful unconfigured allocation state, stale/conflicting readiness propagation, deterministic fingerprints, safe history, separate measurement-history authority, navigation, frontend production build, and backend Economics regressions. No schema or migration change is required.

Real Company policy values, targets, allocation methods, and weights remain `UNCONFIGURED` until an authorized owner decision is recorded through canonical policy authority. Preview deployment and authenticated acceptance remain centralized integration activities. Production is untouched.
