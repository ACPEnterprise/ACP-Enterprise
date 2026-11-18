# Payroll blind historical replay

This workflow calculates historical Payroll independently, freezes the result, and
only then admits read-only QuickBooks output as an answer key. It never executes
Payroll, creates payment instructions, files or pays taxes, posts authoritative
Accounting, mutates Employee YTD, or writes to QuickBooks.

## Admission order

1. Place the protected pre-calculation JSON packet in restricted custody. It must use
   `payroll.blind-replay-input.v1` and contain explicit values plus provenance for
   every field. Zero is a value; omission is not zero.
2. Produce the value-free readiness report:

   ```bash
   cd backend
   PYTHONPATH=. python -m scripts.payroll_blind_readiness \
     --input /restricted/blind-payroll-input.json \
     --output /restricted/blind-payroll-readiness.json
   ```

3. Require every Employee to be `COMPLETE`. The parser rejects selected-period QBO
   gross, withholding, FICA, net-pay, employer-tax, and journal outputs.
4. Calculate with `calculate_shadow_payroll`, then persist with
   `BlindReplayEvidenceService.freeze`. The full input and result are encrypted using
   the existing Payroll protected-input keyring. Retain the calculation ID, input
   digest, engine SHA/version, tax-table version, timestamp, result digest, and
   `frozen_before_qbo_reveal=true`.
5. Only after the committed freeze may an authorized operator import a read-only QBO
   export using `import_qbo_answer_key_csv`, or complementary exports using
   `import_qbo_answer_key_reports`. The source-file digest deduplicates replay.
6. Compare with `compare_frozen_to_qbo`. Material differences remain `UNRESOLVED`
   until a reviewer selects one of the bounded classifications and explains it.
7. Render the owner artifact with `owner_comparison_html`. Differing rows alone are
   highlighted.

## Required pre-calculation fields

The packet requires period start/end, pay date, pay frequency, Company identity, and
packet provenance. Each Employee requires:

- identity, employment status, compensation type/rate/effective interval;
- regular, overtime, and other paid hours plus overtime multiplier;
- commission, bonus, other authorized earnings, and reimbursement;
- all federal W-4 fields, FICA applicability, work/residence/local jurisdiction;
- explicit state/local treatment, FUTA/SUTA rate and wage-base configuration;
- an explicit deductions list, including tax treatment and employer contribution;
- opening gross, FIT, Social Security, Medicare, unemployment, state, and local YTD
  bases and withheld amounts immediately before the selected payroll; and
- source ID, effective date, evidence digest, and VERIFIED/SUPPORTED classification
  for compensation, time, tax, jurisdiction, opening YTD, and every deduction.

The readiness collector returns every field as `PRESENT` or `MISSING` and never
returns the protected value.

## Persistence and replay rules

- A replay identity returns the original frozen snapshot only when input and result
  digests agree; conflicting replay fails closed.
- A deliberate rerun uses a new replay identity and creates a successor snapshot
  version. It never overwrites the prior result.
- The same QBO file digest is admitted once per Company and must remain bound to its
  original frozen snapshot.
- One comparison exists for each frozen-snapshot/answer-key pair.
- Database columns contain ciphertext and safe metadata only.
- The shadow journal is evidence only. Its accounting delta must equal `$0.00`.
