# Worker Control Activation Recovery

Status: `PREPARED — PROTECTED OPERATOR ACTION REQUIRED`

## Verified diagnosis

The Preview host
`https://preview.allcountyhomeservices.com` responds with `405 Method Not
Allowed` to non-mutating `GET` requests for both
`/api/v1/worker-transport/sessions/challenge` and
`/api/v1/worker-transport/sessions`. The worker-transport router is therefore
present on that host. The application's `worker_transport_not_found` response
is deliberately used for `TransportAuthenticationError` and
`TransportBindingError`; it does not distinguish the underlying cause.

The protected operator must therefore verify the following in the same Preview
database and release serving that endpoint:

1. The `EngineeringWorker` row exists for the machine's worker ID and company.
2. Its provider identifier, name, capabilities, and lifecycle are correct.
3. An active `WorkerIdentity` is bound to that exact worker ID and company.
4. An active, unexpired `WorkerCredential` is bound to that identity.
5. The machine-local private key matches the registered public verifier and key
   version.
6. The worker runtime is using the same Preview host, release contract, worker
   ID, and capability set.

No challenge POST is used for diagnosis because challenge issuance is a
protected database mutation.

## Repeatable protected recovery

Run on each machine from the isolated worktree, as a non-root user. The
operator supplies existing protected values through the environment or
`.env.preview`; no values belong in chat, Git, ordinary logs, or command
arguments.

```sh
set -euo pipefail
test "$(id -u)" -ne 0
install -d -m 700 /opt/acp-enterprise/shared/secrets
install -d -m 700 /opt/acp-enterprise/shared/worker-workspaces

# These values must come from the authorized Preview environment and existing
# identity record. Do not invent a company code, administrator, worker name, or
# provider identifier.
: "${ACP_WORKER_COMPANY_CODE:?}"
: "${ACP_WORKER_ADMINISTRATOR_EMAIL:?}"
: "${ACP_WORKER_NAME:?}"
: "${ACP_WORKER_PROVIDER_IDENTIFIER:?}"
: "${ACP_WORKER_CAPABILITIES:?}"
: "${ACP_WORKER_PRIVATE_KEY_FILE_HOST:?}"

test "$(stat -c %a "$ACP_WORKER_PRIVATE_KEY_FILE_HOST" 2>/dev/null || stat -f '%Lp' "$ACP_WORKER_PRIVATE_KEY_FILE_HOST")" = 600

docker compose --profile worker-provision --env-file .env.preview \
  -f docker-compose.preview.yml run --rm worker-provision
```

The provisioner is the supported permission-checked workflow and requires both
`COMPANY_ENGINEERING_WORKER_MANAGE` and `COMPANY_WORKER_IDENTITY_MANAGE`. It
generates the private key locally with mode `0600`, binds the identity to the
worker, issues an active credential, and prints only non-secret IDs.

If it reports `Existing credential requires explicit reconciliation`, do not
rerun unchanged and do not delete rows. Use the supported Worker Identity
administrative lifecycle to inspect the credential, explicitly expire/revoke
the stale credential, and then rerun provisioning. If it reports an
inconsistent identity binding or capability mismatch, reconcile that exact
binding through the same permission-checked workflow before retrying.

After provisioning, verify the returned worker ID locally. For OM1 it must be
exactly:

`a9959036-0e77-4f0a-93b7-ff9c64ed5a60`

If it differs, stop and investigate the company/name/provider binding; do not
start the runtime under the new ID as a substitute.

Start the worker only after the returned identity, credential, and key match:

```sh
test "$(stat -c %a "$ACP_WORKER_PRIVATE_KEY_FILE_HOST" 2>/dev/null || stat -f '%Lp' "$ACP_WORKER_PRIVATE_KEY_FILE_HOST")" = 600
ACP_WORKER_BASE_URL=https://preview.allcountyhomeservices.com \
ACP_WORKER_SERVICE_VERSION="$(git rev-parse HEAD)" \
  docker compose --profile worker --env-file .env.preview \
  -f docker-compose.preview.yml up -d worker
docker compose --profile worker --env-file .env.preview \
  -f docker-compose.preview.yml ps worker
```

The runtime must establish a connected session and fresh healthy heartbeat. A
heartbeat alone is not a lease. Laptop Master then validates the secret-free
machine activation receipt, and the existing Engineering Control workflow
issues the assignment-bound lease.

## OM2-specific gates

OM2 must use a distinct machine-local key and identity binding. Before its HCP
or QBO assignments are leased, the operator must report custody-root presence
as booleans through the protected coordination channel. Missing HCP or QBO
custody remains a hard gate; synthetic fixtures may be used for engineering,
but no actual All County acceptance may be claimed.

The prior ambiguous execution record must be reconciled before reassignment:

1. Restart the runtime with its durable state directory intact.
2. Let it establish a fresh authenticated session and read pending recovery
   acknowledgements.
3. Do not retry the offer while the local journal is `reconciliation_required`.
4. Use the authenticated Worker Control recovery-acknowledgement workflow only
   after the execution evidence and isolated workspace have been reviewed.
5. Preserve the local archive digest and acknowledgement receipt, then allow a
   new lease only after the control service records the reconciliation.

No direct database edits, forced lease clearing, credential copying, source
transfer, HCP/QBO writes, OAuth, or financial execution is authorized.

## Current manual path

While the above recovery is pending, the queue reserves
`OM1-DF-DURABLE-COORDINATION-01`, `OM2-HCP-HISTORY-RECON-01`, and
`OM2-QBO-HISTORY-RECON-01` for manual isolated-worktree execution and blocks
this coordinator's automated claim path. See
`docs/project/manual-engineering-activation-directives.md`.
