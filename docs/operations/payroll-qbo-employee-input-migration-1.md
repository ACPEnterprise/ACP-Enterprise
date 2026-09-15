# QBO Employee Payroll input migration

## Authority and result

- Starting protected authority: `7f1d98dc68016dc55e8454fb009d319aa4ee6396`.
- QBO source contract: `qbo-accounting-evidence/v1`, Production, sealed complete
  acquisition reported by the owner with 19,368 records.
- ACP acceptance remains `accepted_as_acp_accounting=false`; this work does not change
  that classification.
- Result: `QBO_PAYROLL_INPUT_SOURCE_EXECUTION_REQUIRED`.

The repository's QBO Accounting API acquisition catalog includes generic `Employee`
and `TimeActivity` objects plus accounting transactions, accounts, tax payments and
related records. It does not acquire QBO Payroll API paychecks, employee tax profiles,
W-4 elections, payroll deductions, employee-level tax-liability detail, or payroll
reports. No existing QBO-native-ID → ACP Employee crosswalk exists. Therefore the
reported total record count cannot safely be translated into Employee Payroll setup.

This candidate adds a deterministic, value-free inventory command and a pure
reconciliation planner. It creates no Payroll authority. Enterprise must run the
inventory inside the protected Preview backend where the sealed evidence volume is
mounted:

```bash
python -m scripts.qbo_payroll_input_inventory \
  --evidence-root "$QBO_PRODUCTION_EVIDENCE_ROOT"
```

Do not print the environment variable, raw blobs, QBO Employee objects, or protected
Payroll inputs. The command emits manifest identity, entity counts and field
classifications only. Its output digest should be attached to the owner/accountant
review, not treated as Payroll authority.

## Source capability classification

| Required family | Current repository-proven QBO source state | Automatic import |
| --- | --- | --- |
| Employee identity/crosswalk | `PARTIAL_SOURCE_EVIDENCE`: QBO Employee native IDs may exist; no approved QBO→ACP crosswalk | No; exact approved crosswalk required |
| Compensation basis/rate/history/effective date | `PARTIAL_SOURCE_EVIDENCE`: generic Employee/TimeActivity billing or time history is not pay authority | No; review only |
| Pay frequency | `ABSENT` from the acquired Accounting API contract | No |
| Federal withholding YTD | `ABSENT` as Employee-level Payroll authority | No |
| Social Security wages/tax YTD | `ABSENT` as Employee-level Payroll authority | No |
| Medicare wages/tax YTD | `ABSENT` as Employee-level Payroll authority | No |
| Additional Medicare | `PARTIAL_SOURCE_EVIDENCE` at most from historical transactions; not current applicability | No; review only |
| Deduction history/applicability | `PARTIAL_SOURCE_EVIDENCE` at most from accounting history; not current Employee elections | No; review only |
| Prior-Payroll coverage/history | `PARTIAL_SOURCE_EVIDENCE`: aggregate accounting history cannot establish complete Employee coverage | No; accountant review |
| Payroll-period history | `PARTIAL_SOURCE_EVIDENCE` at most; no Payroll report/entity contract | No |
| Work jurisdiction | `PARTIAL_SOURCE_EVIDENCE` at most from time/operational history | No; review only |
| Residence jurisdiction | `PARTIAL_SOURCE_EVIDENCE` at most from address history | No; review only |
| State/local applicability | `PARTIAL_SOURCE_EVIDENCE` at most from historical behavior | No; review only |
| W-4 filing status and Steps 2/3/4(a)/4(b)/4(c) | `ABSENT` from the acquired contract | Never infer |

The protected inventory run must replace every conditional “may/at most” above with
actual entity counts. A zero entity count means source absence, not a zero Payroll
value. Even a nonzero count remains partial until an exact record supplies a supported,
provider-authoritative Employee fact.

## Crosswalk and reconciliation rules

The planner accepts only an approved crosswalk binding Company, hashed realm/company
identity, QBO native Employee ID, ACP Employee ID and evidence digest. Name, email,
phone, address, Employee-number similarity, or a unique-looking candidate is
insufficient. No match is `SOURCE_MISSING`; multiple target Employees are
`HOLD_FOR_OWNER_REVIEW`; foreign Company/realm evidence is ignored.

An explicitly provider-authoritative non-W-4 fact with source record IDs, source
digest, effective period and value digest may produce an `importable_as_draft`
instruction. It still must enter the existing encrypted/effective-dated Payroll setup
service and preserve drafter/approver separation. A planner instruction never directly
creates approved authority.

Partial history produces `REVIEW_REQUIRED`. An approved ACP value is always preserved;
disagreement with provider-authoritative evidence produces `CONFLICTING`, never an
overwrite. Exact replay produces the same packet digest. Missing and partial zero are
never authoritative zero.

## Lianne field-by-field packet

No sanctioned authenticated Payroll/QBO evidence-volume access was available to this
lane, so no current ACP field state or QBO Employee record was inspected. Lianne's
private values were not read or inferred.

| Field family | Current ACP state | QBO source state | Importable | Review | Owner/accountant input |
| --- | --- | --- | --- | --- | --- |
| Exact Employee crosswalk | `AUTHORIZED_READ_REQUIRED` | protected inventory required | No | Yes if a candidate exists | Owner approval of exact provider-ID binding |
| Compensation | `AUTHORIZED_READ_REQUIRED` | accounting catalog is partial only | No | Yes | Owner unless a stronger explicit source is admitted |
| W-4 filing status / Steps 2–4 | `AUTHORIZED_READ_REQUIRED` | absent from acquisition contract | No | No inference | Owner input required only for fields deployed readiness reports missing |
| Jurisdiction/applicability | `AUTHORIZED_READ_REQUIRED` | historical/address evidence partial only | No | Yes | Owner/accountant approval if actually missing |
| Deductions | `AUTHORIZED_READ_REQUIRED` | historical accounting evidence partial only | No | Yes | Owner/accountant approval if actually missing |
| Employee-level YTD taxes/wages | `AUTHORIZED_READ_REQUIRED` | absent from current entity contract unless protected inventory proves explicit detail | No currently | Accountant reconciliation | Accountant input if deployed readiness reports missing |
| Prior-Payroll/period coverage | `AUTHORIZED_READ_REQUIRED` | partial aggregate history only | No | Accountant review | Accountant evidence if actually missing |
| Accepted time / ACP PayPeriod / provider / reconciliation | existing ACP authorities, not QBO migration facts | not imported from QBO | No | No | Resolve only through deployed Payroll readiness |

After Enterprise runs the inventory and supplies an approved exact crosswalk packet,
run `reconcile_employee()` with metadata/digests only. Apply any importable instruction
through existing draft/approval services, then rerun
`payroll.real-input-readiness.v1`. Classify remaining blockers exactly as
`RESOLVED_FROM_QBO`, `REVIEW_REQUIRED`, `OWNER_INPUT_REQUIRED`,
`ACCOUNTANT_INPUT_REQUIRED`, `SOURCE_MISSING`, or `CONFLICTING`. Do not claim
`READY_FOR_PAYROLL` until all deployed authorities are approved and effective.

## Qualification and safety

Focused tests cover exact and ambiguous crosswalks, authoritative draft instructions,
partial review state, missing-versus-zero, approved ACP precedence, W-4 non-inference,
deterministic replay, and Company/realm isolation. The candidate adds no migration,
QBO mutation, Payroll execution, tax filing/payment, Accounting posting, money
movement, Preview deployment, or Production action.
