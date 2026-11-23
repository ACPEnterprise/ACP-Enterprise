# Acceptance read-only service principal

This principal is a non-human, Company-scoped release reader. It has exactly
the six permissions in `READ_PERMISSION_CODES`, uses the normal access-token
and authentication-session machinery, has no refresh token, and cannot use
password login or password recovery.

Provisioning is allowed only after a candidate-bound v2 Enterprise approval
validates successfully and the protected schema is current. It does not itself
constitute Release GO.

## Protected host custody

On the Beta host, the release actor and reader use separate, root-controlled
paths outside the repository and container image:

```sh
install -d -m 0700 /run/acp-release/release-actor
install -d -m 0700 /run/acp-release/acceptance-reader
install -m 0600 /dev/null /run/acp-release/acceptance-reader/access-token
```

Set this exact host reference in the protected Preview environment before
Compose validation or startup:

```sh
PREVIEW_SMOKE_TOKEN_FILE_HOST=/run/acp-release/acceptance-reader/access-token
```

The backend mounts that file at `/run/secrets/preview-smoke-token:ro`. No token
value belongs in `.env.preview`, a command argument, logs, chat, source control,
or browser storage.

## Authorized provisioning window

Start only PostgreSQL, Redis, and the one-shot migration service. Then run an
ephemeral backend container with the custody root as its only writable bind
mount:

```sh
docker compose --env-file .env.preview -p acp-enterprise-preview \
  -f docker-compose.preview.yml up -d postgres redis
docker compose --env-file .env.preview -p acp-enterprise-preview \
  -f docker-compose.preview.yml run --rm migrate

docker compose --env-file .env.preview -p acp-enterprise-preview \
  -f docker-compose.preview.yml run --rm --no-deps \
  --volume /run/acp-release:/run/acp-release \
  backend python -m scripts.provision_beta_release_actor \
  --company-id "$ACP_BETA_COMPANY_ID" --minutes 60
```

The actor token is written only to
`/run/acp-release/release-actor/access-token` with mode `0600`. Re-running the
command rotates its session and invalidates the former actor token. The actor
has only `PLATFORM_ACCEPTANCE_PRINCIPAL_MANAGE`.

Provision the reader without putting the actor token on the command line:

```sh
docker compose --env-file .env.preview -p acp-enterprise-preview \
  -f docker-compose.preview.yml run --rm --no-deps \
  -e ACP_BETA_COMPANY_ID="$ACP_BETA_COMPANY_ID" \
  --volume /run/acp-release:/run/acp-release \
  --entrypoint /bin/sh backend -eu -c '
    ACP_RELEASE_ACTOR_TOKEN="$(cat /run/acp-release/release-actor/access-token)"
    export ACP_RELEASE_ACTOR_TOKEN
    python -m scripts.provision_acceptance_readonly_principal \
      --company-id "$ACP_BETA_COMPANY_ID" \
      --minutes 60 \
      --token-output /run/acp-release/acceptance-reader/access-token
    unset ACP_RELEASE_ACTOR_TOKEN
  '
```

The protected runner may start the backend only after both files are nonempty,
regular, not symlinks, and mode `0600`. Handoff records only principal/session
IDs, expiry, and filesystem references.

## Independent protected smoke

The deployed backend contains `scripts.protected_smoke_check`; the host runner
invokes it through `scripts/protected-runtime-check.py`. The checks prove:

- anonymous denial followed by successful short-lived authentication;
- denial of an administrative permission not assigned to the reader;
- cross-tenant denial against `SMOKE_DENIED_COMPANY_ID`;
- protected route readback and health.

No fixture token is an acceptable substitute.

## Revocation and cleanup

Revoke the reader first, using the actor only through the process environment:

```sh
docker compose --env-file .env.preview -p acp-enterprise-preview \
  -f docker-compose.preview.yml run --rm --no-deps \
  -e ACP_BETA_COMPANY_ID="$ACP_BETA_COMPANY_ID" \
  -e ACP_ACCEPTANCE_PRINCIPAL_ID="$ACP_ACCEPTANCE_PRINCIPAL_ID" \
  --volume /run/acp-release:/run/acp-release \
  --entrypoint /bin/sh backend -eu -c '
    ACP_RELEASE_ACTOR_TOKEN="$(cat /run/acp-release/release-actor/access-token)"
    export ACP_RELEASE_ACTOR_TOKEN
    python -m scripts.revoke_acceptance_readonly_principal \
      --company-id "$ACP_BETA_COMPANY_ID" \
      --principal-id "$ACP_ACCEPTANCE_PRINCIPAL_ID"
    unset ACP_RELEASE_ACTOR_TOKEN
  '
```

Then revoke the actor from an ephemeral backend container and remove only the
two known token files. Database revocation must succeed before file cleanup;
file deletion alone is not revocation.

```sh
docker compose --env-file .env.preview -p acp-enterprise-preview \
  -f docker-compose.preview.yml run --rm --no-deps \
  backend python -m scripts.revoke_beta_release_actor \
  --company-id "$ACP_BETA_COMPANY_ID"
rm -f /run/acp-release/acceptance-reader/access-token
rm -f /run/acp-release/release-actor/access-token
```

No Production principal is authorized by this procedure.
