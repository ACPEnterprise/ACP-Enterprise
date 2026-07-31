# Mission Control V2 dispatch

Mission Control is the durable source of roadmap and milestone definitions. A
roadmap is Company-scoped and versioned; each ordered milestone stores its
objective, authority, constraints, validation, deliverables, stop conditions,
and expected completion evidence.

The owner workflow is:

1. Mission Control presents only `ready`, `waiting_review`,
   `waiting_approval`, and `blocked` milestones in **Waiting for me**.
2. An explicit owner **Start next milestone** action creates and approves the
   bounded Engineering Command and requests execution through the existing
   Engineering Control path.
3. Runtime completion moves the milestone to `waiting_review`.
4. Owner approval completes the milestone and promotes the next definition to
   `ready` when it is already approved, or `waiting_approval` otherwise.

Roadmap progression never creates a command, control request, lease, or worker
runtime. Promotion and execution are separate transactions and execution is
prohibited until an authenticated owner submits the `start` milestone action.
The API exposes no configuration or action that can begin execution without
the owner.

All milestone mutations use optimistic versions and durable milestone events.
Milestones linked to a command also publish through the existing committed
Engineering Workstream event stream, so the phone client invalidates roadmap
truth through authenticated SSE without polling.
