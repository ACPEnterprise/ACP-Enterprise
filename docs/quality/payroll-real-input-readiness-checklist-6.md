# Real Payroll readiness — launch checklist item 6

Date: 2026-09-12

## Result

`PAYROLL_READINESS_PACKET_READY`

`CHECKLIST_6_CALCULATION_READY = FALSE`

Checklist item 6 is not passed. ACP has not reconciled its calculations against an
independently accepted real Payroll reference, and this workstream has no sanctioned
authenticated access to the current real Preview employee/payroll population.

## Authority and scope

- Current protected authority: `origin/customer-management-v1` at
  `68cdc38976fcfb2d5a20e7ce52fc78306bde91ce`.
- The prior ECO candidate was rebased intact onto that authority; governing contract:
  `eco.launch-evidence-readiness.v1`.
- New bounded contract: `payroll.real-input-readiness.v1`.
- No Payroll calculation result, payable record, run, direct deposit, filing, tax
  payment, Accounting posting, Preview mutation, or Production operation was created.

## Real population packet

| Field | Result |
|---|---|
| Source population | `SOURCE_MISSING` for this authorized workstream |
| Exact population blocker | `authorized_real_active_employee_population_unavailable` |
| Total active employees evaluated | `UNKNOWN` — not zero |
| `PAYROLL_READY` count | `UNKNOWN` — not zero |
| `BLOCKED_FOR_PAYROLL` count | `UNKNOWN` — not zero |
| Employee-by-employee matrix | Not emitted because the authoritative roster and protected Payroll evidence were unavailable |
| Independent accepted reference reconciled | No |

The public Preview health endpoint was reachable, but Payroll/Economics evidence is
authorization-protected. The configured SSH identity was also rejected. Local
PostgreSQL contains 29 active records spread across explicitly synthetic/test Company
names; those records were not mislabeled as real All County employees and were not
used in readiness totals.

Smallest access request: Enterprise must run the read-only evaluator in an approved
owner/Payroll-administrator context against the intended All County Company and
provide its digest-bound, protected-value-free output packet. This requires roster
identity, authority metadata, presence states, and evidence digests—not plaintext W-4,
compensation, deduction, or YTD values in an ordinary report.

## Employee evaluation contract

Every active Employee is returned as exactly `PAYROLL_READY` or
`BLOCKED_FOR_PAYROLL`. A blocked result carries one or more exact categories:

- `TIME_NOT_READY`
- `COMPENSATION_NOT_READY`
- `WITHHOLDING_NOT_READY`
- `DEDUCTION_NOT_READY`
- `YTD_NOT_READY`
- `JURISDICTION_NOT_READY`
- `TAX_TABLE_NOT_READY`
- `CONFLICTING`

The evaluator checks compensation basis/rate/effective date/revision; accepted paid
time, Timecard status, corrections, overtime and period assignment; all requested W-4
fields; work/residence and withholding/unemployment jurisdiction; deduction identity,
treatment, dates and limits; Social Security, Medicare, Additional Medicare, federal
withholding and prior-payroll coverage; and effective-dated tax-table provenance.

It consumes only presence and authority metadata. Protected values are not copied into
the packet. `AUTHORITATIVE_ZERO` satisfies a required field; `MISSING` does not.
`NOT_APPLICABLE` must be explicit. Blank, absence, conflict, or unapproved evidence
cannot become zero or ready.

Job-specific time also requires an explicit available-or-not-applicable state. It
cannot be derived from scheduled duration or generic paid time.

## Current engine acceptance

The existing calculation engine is mechanically capable of deterministic gross-pay
calculation when its admission is ready:

- hourly calculation requires approved paid-time snapshot and effective compensation;
- scheduled duration is not an input;
- overtime requires resolved effective Company/Employee authority;
- salary requires compatible pay frequency or a separately approved proration policy;
- tax/deduction calculation requires protected, effective, admitted authorities;
- immutable digests bind policy, compensation, time, tax/deduction and calculation;
- calculation remains distinct from review, finalization, payment and Accounting.

Real calculation comparison was not run because no real Employee was proven
`INPUT_READY`, and no independently accepted Payroll reference was available. Creating
synthetic payable records or using the local test population would not close this gate.

## Smallest owner-input request per employee

Once authorized population evidence is supplied, the packet emits only exact missing
keys for that Employee, for example `missing w4_step_2`,
`missing social_security_wages_ytd`, or `conflicting compensation_rate`. The current
smallest request cannot truthfully be individualized until the real active roster is
available. The single predecessor request is:

1. Authorize Enterprise to execute the read-only readiness collector for the intended
   All County Company and payroll period.
2. Supply or approve only the exact Employee fields returned missing by that packet.
3. Supply an independently accepted Payroll reference for calculation reconciliation.

No employee or compensation facts should be entered from this report alone.

## Qualification

- Fresh PostgreSQL zero-to-head migration: passed at `d4f6h8j0l2n4`.
- Payroll, Timekeeping, and governing ECO contract suites: 147 passed.
- Focused readiness suite: 10 passed.
- Changed-file Ruff: passed.
- Changed-source MyPy: passed.
- Python compilation and `git diff --check`: passed.
- Alembic current=head and drift check: passed; no new upgrade operations.
