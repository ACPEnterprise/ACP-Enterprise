# OM1-B continuous supervisor operations

## Current operating boundary

The OM1-B supervisor executes only explicitly supported, bounded qualification
profiles from a secret-free execution plan. It discovers Laptop Master queues
from remote `handoff/*` refs, requires a manual reservation for `OM1-B`, binds
execution to the assignment and reservation digest, and never creates Worker
Control claims or leases. Automatic commit, push, merge, deployment, protected
data access, and production acceptance remain disabled.

The runtime and coordination checkpoints are mode `0600`, digest protected, and
single-instance fenced. A process holding the runtime lock is the only process
allowed to report itself active. On the next start, a PID left by an abrupt
termination is recorded as stale and reconciled while holding that lock.

## GitHub credential resolution

Git's system configuration supplies `osxkeychain`, but the user configuration
resets that helper specifically for `https://github.com` and replaces it with
`gh auth git-credential`. In the Codex environment, GitHub CLI reports its saved
ACPEnterprise credential as invalid. The sandbox also cannot query the login
keychain, and the Codex process has no interactive terminal prompt. Git
therefore reaches the GitHub CLI helper, receives no usable credential, and
fails instead of prompting for a username.

No credential value was read during this diagnosis. The supported correction
is to refresh GitHub CLI's HTTPS credential from a normal interactive Terminal
and let GitHub CLI maintain Git's helper configuration:

```sh
gh auth login --hostname github.com --git-protocol https --web && gh auth setup-git
```

Do not export a personal access token into the supervisor environment and do
not place credentials in the LaunchAgent property list.

## User-level launchd handoff

Do not bootstrap the LaunchAgent while another supervisor owns the runtime
lock. From the repository root in the owner's normal Terminal, use exactly:

```sh
/bin/zsh scripts/install-om1b-supervisor-launchagent.sh
```

The command renders and validates a user LaunchAgent, installs it mode `0600`
under `/Users/<user>/Library/LaunchAgents`, requests a safe checkpointed stop
from the existing managed supervisor, waits up to 90 seconds for its active PID
to clear, and only then bootstraps the replacement in the user's GUI launchd
domain. It refuses to continue if the label is already registered or if the
existing process does not stop, preventing duplicate execution.

The LaunchAgent uses a 60-second poll interval, a six-hour per-process runtime,
an eight-assignment cap, a 5 GiB free-disk floor, a 512 MiB process-RSS ceiling,
60 consecutive authority-rejection limit, low-priority I/O, and launchd restart
throttling. A rejected or malformed authority is checkpointed and retried after
the poll interval without executing it; exhausting the bounded rejection budget
stops the child fail closed. Because `KeepAlive` is set,
launchd replaces each bounded process after it exits; every replacement must
revalidate the execution plan and current authority before doing work.

## Qualification and escalation

New work is executable only after Laptop Master publishes a descendant queue
containing a manual reservation for the exact execution identity and all
dependencies are evidenced complete. A newly replenished assignment must also
declare an `execution_profile` already implemented by the supervisor; the
current supported values are `supervisor_continuation` and
`supervisor_unattended`. This permits authority-driven replenishment without
allowing an authority packet to inject a shell command. A dependency-blocked
reservation is skipped independently; it does not block another eligible
reservation for the same identity. Unsupported profiles and non-descendant
authority updates fail closed.

Completion evidence is local and secret-free until its branch is published.
Remote completion publication and production automated claims remain disabled
until Laptop Reviewer independently qualifies the supervisor and Laptop Master
authorizes the corresponding publication mechanism.
