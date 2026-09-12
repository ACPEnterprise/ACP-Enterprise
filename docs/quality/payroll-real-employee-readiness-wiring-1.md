# Real Employee Payroll readiness wiring

## Authority and scope

- Starting protected authority: `27b89ecf1d702acbe75d0e1f95cf83c5f6bba5c9`.
- Employee setup authority: protected change #235.
- Federal/FICA provider lineage: PR #228, unchanged.
- Independent reconciliation lineage: PR #233, unchanged.
- Assembly contract: `payroll.real-employee-readiness-assembly.v1`.

This candidate connects existing effective-dated Employee setup evidence to
`payroll.real-input-readiness.v1` and the 2026 provider. It does not approve
inputs, execute Payroll, transmit wages, file or pay taxes, post Accounting, or
move money.

## Deterministic chain

The assembler binds one Company-scoped Employee to the pay period and requires:

1. active compensation authority overlapping the period;
2. accepted time for the same Employee;
3. one effective Employee-specific 2026 authority for every W-4 field;
4. explicit Social Security and Medicare applicability;
5. same-Employee, same-year YTD and prior-Payroll coverage;
6. effective deductions or explicit approved non-applicability;
7. explicit work/residence jurisdiction;
8. the 2026 federal provider selected by period date; and
9. `payroll.federal-tax-2026-reconciliation.v1` reference evidence.

Missing, overlapping, foreign-Employee, wrong-year, or out-of-period evidence
remains `BLOCKED_FOR_PAYROLL` with exact blockers. Florida state income-tax
withholding becomes `NOT_APPLICABLE` only when both work and residence evidence
are explicitly `US-FL`.

## Protected input boundary

`ProtectedPayrollInputCipher.decrypt()` provides authenticated server-only
unsealing by stored key ID. The active key seals new inputs while retained old
keys support rotation and superseded evidence. Company identity is authenticated
as AES-GCM additional data and the plaintext is verified against the persisted
content digest. The API/UI continues to return presence and provenance only;
neither decrypted values nor ciphertext enter readiness packets, responses,
generic events, logs, or client mutation caches.

## Calculation preview

A preview is produced only when the complete synthetic fixture is
`READY_FOR_PAYROLL` and the caller explicitly enables fixture preview. It binds
the provider version and returns component amount, taxable basis, and evidence
digest. `READINESS`, `CALCULATION_PREVIEW`, and Payroll execution remain separate
states; this module has no execution entry point.

## Real-Employee acceptance

Lianne remains an authorized readiness target only. No value was read, entered,
or inferred for her. After Enterprise integrates and deploys the setup, provider,
reconciliation, and wiring candidates and configures the protected keyring:

1. authorized office staff enter and a separate authorized approver approves
   Lianne's real effective W-4, applicability, jurisdiction, deduction, and YTD
   evidence;
2. Enterprise assembles the applicable period with approved compensation and
   accepted time;
3. exact blockers must be empty and status must be `READY_FOR_PAYROLL`;
4. Enterprise may run a separately authorized non-transmitting preview and
   reconcile it independently; and
5. Payroll execution, filing/payment, Accounting posting, and money movement
   remain separately prohibited.

## Next bounded acceptance gap

After handoff, the next non-overlapping gap is persistence/API composition of a
specific Payroll period with accepted Timecard evidence and the assembled
readiness result. It should be implemented only against the protected integrated
contracts so this lane does not create a second pay-period authority.
