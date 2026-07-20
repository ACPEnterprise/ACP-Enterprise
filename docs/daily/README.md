# Daily Development Records

Daily records provide a concise, durable handoff of development activity. They make progress, evidence, decisions, risks, and unfinished work discoverable across time zones and teams.

They do not replace:

- Issues or tickets for planned and tracked work
- Pull requests for code review and implementation discussion
- ADRs for durable architecture decisions
- Module documentation for product behavior and business rules
- Incident records for production events

## File naming and location

Create one Markdown file per active engineering day under a year/month hierarchy:

```text
docs/daily/YYYY/MM/YYYY-MM-DD.md
```

Use the ACP Enterprise business timezone (`America/New_York`) for the date. If multiple teams contribute, maintain one shared record with entries grouped by workstream rather than creating private diaries.

## Required content

Each daily record contains:

1. **Date and participants** — contributors or accountable workstream owners.
2. **Objectives** — the intended outcomes for the day, linked to issues or release milestones.
3. **Completed** — behavior or decisions completed, with pull request, commit, deployment, or document links.
4. **Validation evidence** — tests, migrations, demonstrations, reconciliation results, performance measurements, or screenshots where useful.
5. **Decisions** — decisions made that day and their rationale. Link or create an ADR when the decision is durable or architecture-significant.
6. **Risks and blockers** — impact, owner, next action, and required resolution date.
7. **Production or environment changes** — deployments, flags, migrations, configuration, data operations, and rollback status.
8. **Next actions** — explicit handoff for the next development day.

Do not include secrets, access tokens, raw customer information, payment data, or sensitive production logs.

## Template

```markdown
# Daily Record — YYYY-MM-DD

## Participants

- Name or team — workstream

## Objectives

- [Issue link] Measurable outcome

## Completed

- [PR/document/deployment link] User-visible or architectural result

## Validation evidence

- Check performed — result and evidence link

## Decisions

- Decision — rationale — ADR link if applicable

## Risks and blockers

- Risk/blocker — impact — owner — next action — target date

## Environment changes

- Environment — version/change — verification — rollback status

## Next actions

- Owner — specific next outcome
```

## Writing standards

- Describe outcomes, not a chronological activity log.
- Use links to authoritative evidence rather than copying long build output or discussion.
- Quantify results and risks where possible.
- State “none” when a required section has no entry; do not omit the section silently.
- Update the record before the final handoff of the day.
- Correct factual errors in place and note material corrections with date and author.
- Move durable knowledge into the appropriate architecture, engineering, product, or operational document and link it from the daily record.
