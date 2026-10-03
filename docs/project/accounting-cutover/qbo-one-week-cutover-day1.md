# QBO replacement: active Day 1 closure board

Protected base: `66fd912d4be1986731190b1d0603be5101d022e6`.

The seven-day closure clock is active. This board covers only the first-day
banking/source-custody targets; it does not authorize production accounting
mutation or money movement.

| Lane | Day 1 assignment | Exit evidence | State |
| --- | --- | --- | --- |
| LPTP1A | Bank account/source contract, import evidence, deterministic matching, replay and reconciliation controls | Qualified controls plus sanctioned source package admitted | ENGINEERING_READY / REAL_SOURCE_REQUIRED |
| LPTP1B | Banking operator workflow and cash-flow presentation/drill-down | Normal UI path exercised against accepted evidence | UI_AND_REAL_DATA_REQUIRED |
| LPTP1Phone | No bookkeeping implementation; stand by for read-only owner/accountant status need | Explicit mobile requirement or remain idle | NOT_REQUIRED |
| LPTP1E | Integrate bounded current-protected candidate; maintain parity, acceptance, and cutover packets | Immutable release packet with evidence states | IN_PROGRESS |

## Day 1 human and external gates

- Owner authorizes the exact All County company/bank scope and confirms whether
  any additional bank accounts are used.
- Accountant provides matching, transfer, fee, undeposited-funds, and
  cash-flow classification policy.
- Authorized source custodian supplies a read-only bank connection or a dated
  statement/CSV/OFX package with opening/ending balances and source identity.
- OM1E/OM2 provides the sanctioned release/database environment for the
  operator workflow and current-to-head migration qualification.

Until these are supplied, the engineering controls remain qualified but the
three banking/cash-flow rows remain YELLOW and QuickBooks retirement cannot be
declared.
