# Mission Control V2.1 roadmap initialization

The approved ACP Enterprise roadmap catalog is initialized for the `ACP`
Company by `app.engineering_control.mobile.roadmap_initialization`. Repeating
the initializer is idempotent: it creates missing roadmap titles and appends
missing catalog milestones by title without rewriting existing milestone truth.

Roadmap truth distinguishes:

- `completed`: committed milestone evidence; never redispatched;
- `externally_running`: active isolated work with durable branch evidence and
  no Mission Control command;
- `ready`: an approved definition that still requires an authenticated owner
  Start action;
- `draft`: future intent whose complete work order has not been approved.

Milestones persist their owning workstream and branch, dependencies, approval
state, and external evidence. Draft and externally-running records are excluded
from **Waiting for Me**, preventing duplicate dispatch and misleading counters.

The read-only V2.1 phone acceptance rehearsal remains Ready and sets
`requested_code_changes=false`. Ready state never dispatches it; only an
explicit owner Start action can create its bounded Engineering Command.

## V2.2 population

Mission Control V2.2 adds 15 Company-scoped, approved roadmap definitions in
ordered dependency chains. Customer Migration and Business Economics remain
Draft behind their externally-running prerequisites. Beacon BEA.6 and
Operations Scheduling Readiness are Ready because their prerequisites are
satisfied; later milestones in both chains remain Draft. Initialization never
creates an Engineering Command, control request, lease, or runtime.

Estimated duration is durable roadmap metadata stored as an
`Estimated duration:` constraint. This uses the existing milestone model and
keeps duration visible in the stored work order sent only after an explicit
authenticated owner Start action. Dependencies remain in the dedicated
`dependencies` field.

Preview serves Mission Control from its isolated stack through route-level
Caddy handlers. V2 assets use `/mission-assets/`, allowing the general Preview
application and active Customer Migration containers to remain untouched.
