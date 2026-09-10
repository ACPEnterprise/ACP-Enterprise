# WORKFORCE.TIME.ECONOMICS.READINESS.1 integration packet

Protected authority is `origin/customer-management-v1` at
`cd89dc3dd0f69e28cc5bf836e59da890797cb7b1`. The published OM1 measurement
foundation was composed because it is not yet integrated. Its unchanged
snapshot migration was re-parented from prior protected head `n0p8r16g3t9u` to
current protected head `b2d4f6h8j0l2`, which already descends from the prior
head. The resulting intended head is `a1c3e5g7i9k1`.

The `workforce.time-economics-readiness.v1` contract composes explicit
Employee–Job–Appointment assignment provenance with mechanically distinct
scheduled, worked, jobsite, paid, and productive intervals. Job evidence
reports each duration independently. Employee evidence reports approved paid
minutes, attributable Job-work overlap, explicit productive time, and
unclassified paid time without presuming that unclassified time is
nonproductive.

Scheduled duration never substitutes for actual worked duration. Timekeeping
paid intervals cannot carry Job identity. Job intervals without an
authoritative Dispatch relationship are rejected. Multi-technician Jobs retain
separate Employee evidence. Overlapping intervals, foreign Company/Branch
evidence, productive time without worked evidence, and attributed overlap that
exceeds paid time are reported as conflicts rather than precise measurements.
Every result carries source authority, record identity, version, digest,
confidence, missing inputs, conflicts, limitations, and a deterministic digest.

HCP remains Migration-owned. Only successor-aware, admitted, digest-bound HCP
evidence can populate these inputs. Missing HCP arrival, jobsite, pause/resume,
technician crosswalk, timezone, travel, or actual-work evidence remains partial
or source-required.

No compensation amount, labor burden, overtime rule, Payroll policy,
break-even assumption, productive-efficiency policy, employee ranking,
employment recommendation, Luminary action, Price Book activation, or repricing
is produced.

Qualification used a fresh isolated PostgreSQL 16 cluster. Zero-to-head reached
`a1c3e5g7i9k1`, `alembic current` equaled that head, and `alembic check`
reported no drift. Of 950 affected tests, 949 passed. The sole failure,
`test_wrong_builder_scope_fails_without_protected_output`, reproduces unchanged
on protected `cd89dc3d`: current protected Migration accepts independently
authorized nonzero scopes while that older test expects every non-default UUID
to fail. This bounded Workforce/Economics branch does not change that unrelated
Migration authority or test.
