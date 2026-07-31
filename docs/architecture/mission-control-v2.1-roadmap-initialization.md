# Mission Control V2.1 roadmap initialization

The approved ACP Enterprise roadmap catalog is initialized once for the `ACP`
Company by `app.engineering_control.mobile.roadmap_initialization`. Repeating
the initializer is a no-op for existing roadmap titles.

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

The sole initial Ready item is a read-only V2.1 phone acceptance rehearsal. It
sets `requested_code_changes=false`; promotion cannot dispatch it, and only an
explicit owner Start action can create its bounded Engineering Command.

Preview serves Mission Control from its isolated stack through route-level
Caddy handlers. V2 assets use `/mission-assets/`, allowing the general Preview
application and active Customer Migration containers to remain untouched.
