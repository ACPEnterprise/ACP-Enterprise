# Mission Control V1 owner experience

Mission Control V1 is a product projection over the completed PHONE.4–PHONE.7
architecture. It does not create a second execution or event path.

The owner experience reads authoritative workstream projections and persisted
Mission Control notifications, then stays current through the authenticated SSE
stream. Owner decisions continue through the existing permission-checked command
review and workstream-control services.

## Screens

- **Overview** — active work, owner attention, running work, today's outcomes,
  worker truth, current activity, Preview delivery health, and an executive summary.
- **Approval inbox** — approval requests and persisted notifications grouped by
  attention, failures, recovery, and completion. It supports approve, reject,
  request revision, read, acknowledge, and archive workflows.
- **Morning briefing** — overnight outcomes, attention, worker and Preview health,
  deliveries, failures, and a next-action recommendation.
- **Analytics** — execution, validation and approval latency, worker uptime,
  completed milestones, failure rate, deployment success, and reconnect count.
- **Workstream journey** — a human-readable realtime timeline with timestamps and
  elapsed durations, replacing raw developer-log presentation.

## Notification lifecycle

Notification evidence remains event-derived and Company scoped. `unread`, `read`,
`acknowledged`, and `archived` states are explicit, versioned owner transitions.
Escalation remains server governed. Browser contracts expose no credentials,
headers, repository contents, tokens, or runtime secrets.

## Mobile principles

The primary experience is a single four-view surface with 44-pixel-or-larger
actions, short owner language, progressive detail, horizontal-safe filters, and
truthful empty or unavailable states. Missing metrics are never estimated.
