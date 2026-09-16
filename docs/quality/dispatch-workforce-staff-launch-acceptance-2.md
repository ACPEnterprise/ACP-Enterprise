# Dispatch and Workforce staff launch acceptance 2

## Authority sweep

- Starting protected authority: `a65a104c21282fd8f94a2e9bac37ba576a91a75c`.
- Branch: `work/om2c-dispatch-workforce-staff-launch-acceptance-2`.
- Protected Workforce authority includes real-roster binding, exact source certification, unified Employee timeline, readiness explanations, notification targeting, MAIN Branch readiness, canonical roles, capability profiles, availability windows, and Dispatch eligibility.
- Protected Dispatch authority includes canonical Workforce eligibility consumption, blocked-technician explanations, primary/crew assignment, optimistic concurrency, assignment history, operator board context, and Appointment/Job projections.
- Enterprise integrated equivalents of the former calendar, Dispatch-board, and assignment-history candidates in protected batch 3. Their historical branch heads are not replayed here.

## Stale navigation finding

Protected commit `7de1013af5914d74eb8512ef826b3a7642b4fbd6` previously reconciled Employee links to `/employees?employee=<id>`. Later commit `d393ddd1` added `RealRosterActivationConsole` with one stale `/workforce?employee=<id>` link. No current branch or protected successor corrected that component.

This candidate centralizes the canonical Employee-detail path and applies it to:

- Real employee activation → access/capabilities/history;
- Dispatch eligibility → Employee readiness.

The Employee identity is URL-encoded. Authorization still applies at the canonical Employee route; no Dispatch or roster permission is broadened.

## Real staff launch state

The owner-confirmed roster contract remains:

- Michael Fouse: Administrator;
- Lianne Hernandez: Office Manager;
- Alex Donahue: Office Staff;
- Melvin Santiago, Adam Mari, Dareis Montgomery, Dakota Wilcox, and Jason Calci: Field Technicians.

Lianne's known authenticated Office Manager operation is accepted as owner-provided current fact. This lane did not impersonate her, alter her roles, or add technician capability. Other identities remain owner-certification gates unless already bound by authoritative roster evidence at execution time.

Independent product surfaces are present for roster visibility, account/Membership/MAIN Branch/role state, Workforce and Mobile state, technician capability, bounded availability window, Dispatch handoff, Payroll handoff, blockers, source-certification history, Employee timeline, assignment eligibility, and immutable Dispatch assignment history.

Remaining launch gates are factual, not missing Dispatch architecture:

1. owner certification of each intended real Employee/source binding;
2. owner confirmation of MAIN Branch and role for non-Lianne staff;
3. owner-approved field-technician capability and bounded availability evidence for each real technician;
4. authenticated real-staff acceptance for Dispatch selection and Employee My Day;
5. a sanctioned real Appointment for assignment persistence acceptance.

No duplicate Employee was created. No Office Manager was converted into a technician. No real assignment, availability, identity, role, Membership, or Customer record was mutated.

## Owner acceptance

1. Sign in to Preview with authorized owner or Office Manager access.
2. Open **Employees** and **Real employee activation**.
3. Confirm Lianne shows Office Manager, MAIN Branch, and non-technician state.
4. For each owner-certified Field Technician, inspect account, Membership/MAIN, roles, capability, availability, Dispatch handoff, and history.
5. Follow **Open access, capabilities and history** and verify the selected Employee opens at `/employees?employee=<id>`.
6. Open a sanctioned real Appointment in Dispatch.
7. Verify all canonical Workforce candidates remain visible, including blocked candidates with exact explanations.
8. Follow **Open employee readiness** for a blocked and an eligible candidate and confirm the same Employee and evidence.
9. Assign an owner-certified eligible real technician only after the real Appointment is sanctioned.
10. Refresh and verify Appointment, Job, Dispatch, Employee My Day, and assignment history agree.

Preview and Production were not mutated.
