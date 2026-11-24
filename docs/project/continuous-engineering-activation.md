# TwelveHats Continuous Engineering Activation

Status: `PREPARED — NOT ACTIVATED`

This register is the laptop-side coordination handoff for the existing
Development Factory. It does not replace the repository roadmap, Factory
Control authority, worker transport, release governance, or owner gates.

## Verified laptop register

The following facts were verified in the current laptop workspace before this
activation package was prepared:

| Field | Verified value |
| --- | --- |
| Machine label | `LAPTOP_MASTER` |
| Hostname | `Mac.lan` |
| OS | macOS `26.5.2`, build `25F84` |
| Repository | `/Users/michaelfouse/Development/ACP-Enterprise-Master` |
| Branch at inventory | `work/existing-business-db-compatibility` |
| HEAD at inventory | `1f213a652b88c97dca738437dc65e291f62cbe90` |
| Origin | `https://github.com/ACPEnterprise/ACP-Enterprise.git` |
| Worktree at inventory | clean |
| Codex | `/Users/michaelfouse/.local/bin/codex`, `codex-cli 0.167.0` |
| Docker | `29.6.2`, 10 CPUs, 8 GiB Docker memory |
| Host resources | approximately 17.18 GiB RAM; approximately 613 GiB free |
| Factory state | DF.1–DF.4D, worker control, authenticated transport, scheduler and Factory Control present |

The current branch is a task worktree, not a claim that it replaces a protected
integration branch. Protected branch and Beta mutation remain separately
governed.

## Unverified machine facts

OM1 Enterprise and OM2 were not reachable from this execution context. Their
hostname, OS, repository path, branch, worktree status, divergent commits,
remote access, Codex installation, Docker capacity, storage, and factory state
are therefore `UNVERIFIED`. Existing roadmap documents establish the permanent
capacity labels and intended lanes, but they are not evidence of current host
state.

No OM1/OM2 activation, SSH attempt, credential inspection, checkout, reset,
stash, cleanup, commit, push, deployment, or protected data access was done.

## Permanent allocation and boundaries

| Capacity | Sole lane | Can prepare autonomously | Must stop for independent review/owner gate |
| --- | --- | --- | --- |
| `LAPTOP_MASTER` | Product integration, All County operational acceptance, coordination, Keith demo, release preparation | Isolated code/tests, source reconciliation preparation, task-branch work, evidence packets | Beta/Production deployment, protected credentials, migrations/admission, financial logic, tenant/security changes, external writes |
| `OM1` | Development Factory, CI/CD, IaC, migration/release governance, manifests, protected qualification, monitoring/recovery | Isolated tooling and qualification work after inventory | Protected authority, live infrastructure, release/governance mutation, deployment |
| `OM2` | HCP/QBO history, communications, reconciliation, isolated native-admission preparation | Read-only acquisition verification and isolated rehearsals | HCP/QBO writes, OAuth, financial admission, customer-identity merges, irreversible data changes |
| `REVIEWER` | Independent architecture, security, regression, protected release and commercial readiness review | Independent inspection in separate worktree/evidence custody | Cannot integrate, approve itself, deploy, or waive failures |

## Existing factory boundary being extended

The repository already provides the implementation basis and is retained:

- DF.1–DF.4D local task contracts, workspaces, bounded worker execution,
  validation, provenance, owner-review packages, and evidence chains.
- Engineering Control / Execution / Worker Control for durable execution state.
- Authenticated Worker Transport, expiring leases, optimistic versions,
  heartbeats, replay protection, and crash-recovery records.
- Scheduler queue, permanent capacity identities, dependency-aware eligibility,
  advisory Factory Control telemetry, and explicit owner/delegation gates.

The current factory does **not** provide unattended cross-machine dispatch. It
does not commit, push, merge, deploy, or grant authority by itself. The new
machine inventory command and queue below make activation reproducible without
creating a second orchestration system. A true cross-machine execution mode
requires an isolated implementation and independent review of queue authority,
worker identity, shared-resource fencing, and persistence semantics.

The queue contract is executable through the existing factory CLI:

```sh
./scripts/development-factory coordination validate
./scripts/development-factory coordination summary --active-lane LAPTOP_MASTER
./scripts/development-factory coordination inventory-check /tmp/twelvehats-om1-inventory.json --require-clean
```

These commands validate dependencies, project eligibility, or an inventory
receipt only. They do not activate a machine, claim work, or create a lease.

## OM1 activation procedure

Run from the existing OM1 repository root. These commands are read-only and
must be run before creating any worktree or assigning active work:

```sh
./scripts/development-machine-inventory --role OM1 --repo-root "$PWD" > /tmp/twelvehats-om1-inventory.json
git status --short --branch
git rev-parse HEAD
git remote -v
git worktree list
```

If the existing checkout does not yet contain the inventory command, use the
read-only fallback below first, then fetch the exact handoff branch and create
an isolated worktree only after Laptop Master verifies the receipt:

```sh
hostname
uname -a
pwd
git status --short --branch
git rev-parse HEAD
git remote -v
git worktree list
git fetch --no-tags origin handoff/continuous-engineering-activation-633ad6cd
git show --stat --oneline FETCH_HEAD
```

The fetch is not an activation or deployment. Do not checkout, reset, clean,
stash, merge, or overwrite the existing checkout.

Return the JSON receipt and the exact output of the four Git commands through
the approved coordination channel. Do not include environment dumps, secret
values, private-key material, OAuth tokens, database URLs, or customer data.

After Laptop Master verifies the receipt, OM1 may create a new isolated
worktree from the agreed immutable starting SHA. It must not alter existing
worktrees or protected branches.

## OM2 activation procedure

Run the same read-only procedure from the existing OM2 repository root:

```sh
./scripts/development-machine-inventory --role OM2 --repo-root "$PWD" > /tmp/twelvehats-om2-inventory.json
git status --short --branch
git rev-parse HEAD
git remote -v
git worktree list
```

Return the receipt through the approved coordination channel. OM2 must also
report, as booleans only, whether the already-authorized HCP/QBO custody roots
are mounted; it must not print paths containing secrets or copy source data into
ordinary logs. No OAuth, provider write, live admission, or customer-data export
is part of activation.

The laptop currently has read-only custody evidence in Downloads: the HCP CSV
matches the accepted 4,056,093-byte / 450-column / 5,464-record source digest,
and the QBO archive matches its accepted SHA and sealed acquisition structure.
This does not authorize OM2 to copy, extract, admit, or transmit that evidence.

## Activation acceptance

Laptop Master marks a machine `ACTIVE` only when all of the following are
present and independently checked:

1. machine receipt with hostname, OS, exact repository path, branch, HEAD,
   remote, clean/uncommitted state, tool versions, and resource summary;
2. no conflicting active worktree or undeclared divergent branch;
3. exact starting SHA and allowed file boundary for the first task;
4. worker identity and capability evidence through the existing authenticated
   Worker Control path;
5. independent reviewer assignment for any security, migration, tenant,
   financial, release, or infrastructure impact.

Until then, the capacity is `UNVERIFIED`, not available for automatic claiming.

## Failure and recovery rules

Use the existing task workflow and worker leases. A stale lease is fenced by its
lease version and expiry; a worker restart reconciles durable state before any
new claim; ambiguous execution is reconciled rather than replayed; a network
failure never authorizes a duplicate operation. Repeated failures of one class
pause that assignment and preserve evidence while unrelated safe assignments
continue.

No unattended 24-hour or 48-hour run is authorized by this document. Those
qualification periods begin only after synthetic tests prove atomic claiming,
fencing, recovery, secret redaction, resource limits, and safe shutdown, and
after the owner/independent reviewer accepts the resulting evidence.
