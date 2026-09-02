# Employee Access Support and Recovery

Use Employee Administration diagnostics before changing authority. Never request or
record passwords, activation tokens, provider payloads, pay values, banking, or tax
data in support evidence.

| Symptom | Inspect | Safe next action |
|---|---|---|
| Cannot log in | User, credential activation, Membership, authorization version | Resolve the owning identity state; revoke sessions or use accepted credential recovery when required |
| Wrong or missing Branch | Default Branch and explicit grants | Correct the explicit grant, then require refresh/reauthentication |
| Missing Job/My Day | Employee linkage, Branch, field permission, authoritative assignment | Correct the owning missing contract; do not grant broad Customer access |
| Permission denied | Role/profile grant, Branch scope, own-data scope, authorization version | Apply the narrow authorized change or explain the denial |
| Invitation not received | Invitation status versus Communications delivery state | Reissue only through accepted lifecycle; provider-not-configured is not delivered |
| Bounced/rejected/deferred/uncertain | Communications evidence | Follow Communications recovery; do not substitute recipients |
| Activation expired/revoked/used | Invitation lifecycle | Issue a governed replacement; never recover the old secret |
| Lost/replaced phone | Active sessions and credential recovery need | Revoke the affected session, preserve authorization, sign in on the new device, rerun Mobile acceptance |
| Employee leaves Company | Membership/session/Branch/Employee operational state | Remove application access and preserve history; hand Payroll/HR policy to its owner |

Temporary access reduction uses existing role, permission-profile, Membership, or
Branch mechanisms. ACP has no invented time-based deny policy. Restoration requires
an explicit reviewed mutation and must not resurrect outdated authority implicitly.
