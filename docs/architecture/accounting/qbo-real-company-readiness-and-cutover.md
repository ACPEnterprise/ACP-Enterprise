# QBO real-company acquisition readiness and source cutover

Status: planning and synthetic qualification only. QBO Production, the real
QuickBooks company, ACP Production, and cutover remain prohibited.

## Real-company acquisition gate

Real acquisition requires a separately approved Production Intuit application,
an exact Production callback, read-only Accounting scope, owner OAuth selection
of the intended real realm, and independent `CompanyInfo` verification. Sandbox
credentials, tokens, realm IDs, evidence roots, and API hosts cannot be reused.
The owner gate occurs before OAuth; no Production credential is requested by
this plan.

After authorization, acquisition uses a protected snapshot identity, pagination
to exhaustion, immutable page/blob/envelope evidence, bounded retry, checkpoint
resume, serialized refresh, and a sealed manifest. A changed realm, company,
scope, source cutoff, query version, or transformation version fails closed.
Disconnect retires usable authority but preserves audit evidence.

## Authority and dependency order

HCP remains operational source evidence, QBO remains historical/accounting
source evidence, and ACP is the provider-neutral destination. Authority is
assigned per fact—not globally—and may be HCP-authoritative, QBO-authoritative,
ACP-native, corroborated, conflicting, or unresolved. Names and descriptive
fields never establish cross-source identity.

The dry-run order is:

1. Verify repository/schema/actor/Company/Branch and both source authorities.
2. Freeze HCP operational writes, acquire its final delta, and seal the manifest.
3. Freeze QBO accounting writes, acquire its final delta, and seal the manifest.
4. Admit identities and mappings before dependent operational/accounting facts.
5. Reconcile open Jobs and Estimates, then open AR, open AP, unapplied Payments,
   cash/bank opening evidence, payroll liabilities, and tax liabilities.
6. Persist explicit HOLD/exception outcomes for every unresolved population.
7. Close only when source totals, child outcomes, and accounting invariants agree.
8. Replay identical authority and prove zero duplicate identities or effects.

Source freezes require explicit owner confirmation and a timestamped cutoff.
Abort before destination acceptance on realm/scope/digest contradiction,
unexplained delta, cross-company leakage, unsafe financial promotion, or a
missing required control report. Resume reuses completed checkpoints and rejects
changed immutable input.

## Go/no-go controls

Owner go/no-go is required after final source manifests and again after the
reconciliation report. Open AR/AP, payments, payroll/tax liabilities, bank/cash
opening evidence, exceptions, and HOLDs must be reviewed separately. No sandbox
mapping is a final All County account mapping. No journal, settlement, revenue,
tax, or opening balance is accepted merely because a source reports it.
