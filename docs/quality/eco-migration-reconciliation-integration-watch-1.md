# ECO Migration Reconciliation Integration Watch 1

## Watch outcome

The prior reconciliation candidate did not reach protected authority before a
new protected migration claimed its proposed successor identity.

At protected authority `52dc336766a67fc0c4698244b9894bab0fe65913`:

- Payroll `e5g7i9k1m3o5` remains unchanged (SHA-256
  `6f6726dfb165d7b66d2ce63084ef71c36d2bb9211927597efab40ac457859aaa`).
- Protected password-reset delivery now owns `f6h8j0l2n4p6`, with
  `down_revision = e5g7i9k1m3o5`.
- Its SHA-256 is
  `66a337d26aa64d52d157f5f21419f04207bba0efdca7cf5ba118cdcf33a92abe`.
- The prior ECO file under `f6h8j0l2n4p6` had SHA-256
  `6c12b6645456490412dbbc49be4ec0e775c0db02a13075f56fade6dabd51c02f`
  and different schema operations.

This is a second real revision-ID collision. Candidate `5567932d` must not be
integrated as-is. The composed ECO migration is moved to unique successor
`g7i9k1m3o5q7`, with `down_revision = f6h8j0l2n4p6`. No protected migration is
renumbered or rewritten.

## Enterprise order

1. Retain protected Payroll `e5g7i9k1m3o5` unchanged.
2. Retain protected password-reset delivery `f6h8j0l2n4p6` unchanged.
3. Integrate only this watch reconciliation candidate, producing head
   `g7i9k1m3o5q7`.
4. Do not separately integrate `5567932d`, `863cab13`, or historical ECO
   predecessors.
