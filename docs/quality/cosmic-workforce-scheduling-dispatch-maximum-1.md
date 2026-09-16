# Cosmic Workforce, Scheduling, and Dispatch maximum 1

## Authority and ownership

- Starting protected authority: `5f7a45118885a38e5faa4fcfcf98dd395d3ea7ea`.
- Branch: `work/om2c-cosmic-workforce-scheduling-dispatch-maximum-1`.
- Workforce remains authoritative for Employee identity, Membership, Branch,
  role, capability, availability, and technician readiness.
- Scheduling remains authoritative for Appointment timing and versioned moves.
- Dispatch consumes those contracts and does not infer technician capability.

The canonical `/employees?employee=<id>` navigation from the former PRs #366
and #377 is already present in protected authority, including the roster and
Dispatch-readiness entry points. Neither historical branch was replayed.

## Repaired operating defects

### Terminal assignment history projected as active work

The Dispatch board returns the latest assignment evidence, including terminal
`released`, `replaced`, and `cancelled` rows. Presentation code previously used
object presence as active-assignment truth. As a result, released work could:

- appear assigned rather than unassigned;
- retain a former technician in Schedule and Dispatch filters;
- contribute former crew to technician capacity;
- display a terminal assignment exception as an active exception; and
- offer **Manage assignment** instead of the normal assignment action.

Dispatch and Scheduling now share the existing active-assignment rule already
used by Needs Scheduling: terminal history remains preserved, but it does not
represent current assignment authority. Crew members are included in technician
filtering only while their assignment is active.

Appointment detail applies the same rule. A terminal assignment now appears as
retained history with its terminal state and release time rather than labeling
the former Employee as the current primary technician.

### Nested overlap undercount

Capacity previously compared each window only with the immediately preceding
window. A short Appointment nested inside a longer Appointment could hide a
later collision with the still-active long window. The descriptive capacity
projection now carries the maximum prior end time forward and counts each later
window that begins while prior work remains active. It still makes no travel,
availability, staffing, or autonomous assignment claim.

### Workforce navigation acceptance drift

The Payroll-to-Employee navigation regression test had stale complete-module
mocks after source certification, timeline, and real-roster readiness were
added. The acceptance scaffold now supplies those read-only contracts. No
Employee or Workforce product authority changed.

## Qualified connected surfaces

The focused UI suite covers Employee roster/detail/timecard navigation,
canonical access/capability/history links, Scheduling Day/Week/Work Week/Month,
Needs Scheduling, Appointment detail, refresh/reschedule, Dispatch board,
assignment controls, readiness explanations, operating filters, narrow-width
reachability, terminal assignment truth, crew filtering, and capacity overlap.

Backend qualification covers Workforce readiness and persistence, real-roster
and source-certification contracts, Scheduling API/service/persistence,
Dispatch assignment/history/eligibility/intelligence boundaries, and Employee
My Day projection.

## External acceptance gates

- Real Employee login, Mobile rendering, and physical-device behavior require
  actual human/device evidence.
- Real assignment, unassignment, crew change, or reschedule requires an
  owner-sanctioned real Appointment and confirmed technician.
- Current protected authority supplies no permission to create Employees,
  change Office Manager capability, or fabricate acceptance records.
- Preview and Production were not changed by this candidate.

## Unrelated protected-suite findings

The repository-wide frontend run exposed eight existing failures outside this
lane: five Invoice tests with a stale `getInvoiceCandidates` API mock, two
Customer reliability tests missing QueryClient/source-history scaffolding, and
one Financial Reports test missing the QBO source-backed report hook mock. They
are routed to their domain owners through Enterprise and are not repaired here.
