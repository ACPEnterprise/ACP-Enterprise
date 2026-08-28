<!-- markdownlint-disable MD013 -->

# BANK.ACC.001 Accounting Authority and Lineage Reconciliation

## Canonical identity

`BANK.ACC.001` resolves to the accepted `ACC.IC.1` integration boundary at
`65377ad5cba31c0945324965f81dd60e7102174c`. That commit is the canonical tip of
one linear Accounting evidence chain; it does not replace or duplicate the
runtime milestones beneath it.

The accepted ancestry is:

| Capability | Authoritative evidence |
| --- | --- |
| Native Accounting core | `ACC.CORE.1` — `ee87e572d0f0e53fbc826978ab4d3a8ff489120a` |
| Invoice and AR | `43018e22786341116f77a606ccf70a8fa1e3ae14` plus identity preservation at `5f66495` |
| Payments | runtime `8c10708`, migration reconciliation `1e631689bddddc1ff8fd763bb2d8fd6016eacc7b` |
| AP/vendor/bills | `6260b006f7e40a1cc9283ab7a7f069c58090f29f` |
| Domain-fact posting and receipts | `ACC.POST.1` — `359e3afac2141f54362b98f3ae2616074330fea2` |
| Native financial statements | `ACC.RPT.1` — `1f012258cba67300c3481953aa18a62e12e5b634` |
| Opening-state reconciliation/posting boundary | `ACC.MIG.1` — `d772702a14885e72b4743c6960ca1bde99b6f134` |
| Immutable integration candidate | `ACC.IC.1` — `65377ad5cba31c0945324965f81dd60e7102174c` |

`accounting_ledger_reporting` remains the collision domain for the native
ledger, posting, reporting and authority chain. No other accepted active
ownership record claims this collision domain. BANK.ACC.001 completes the
historical identity reconciliation and releases only its hard dependency edge
to BANK.ACC.002.

## Source and policy boundaries

The accepted provider-neutral QBO acquisition and reconciliation evidence at
`819b2685`, `30ffdd27` and `dc3a7eff` describes source observations only. QBO is
not the native ledger, does not become Accounting authority through this record,
and supplies no inferred mapping or Finance policy.

Unresolved chart mappings, revenue recognition, Company cash/accrual policy,
source precedence, tolerances, materiality, opening balances, real financial
values and real-import acceptance remain unresolved. Consequently BANK.ACC.002
has its predecessor satisfied but remains blocked by its own Finance gate. This
record authorizes no Accounting runtime change, import, Preview or Production
operation.
