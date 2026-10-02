# Acceptance read-only service principal

This principal is a non-human, Company-scoped release reader. It is restricted to
the six permissions in `READ_PERMISSION_CODES`, uses the canonical access-token and
authentication-session machinery, has no refresh token, and cannot authenticate by
password or password recovery.

## Beta provisioning

Release first provisions or rotates the dedicated non-human actor from the trusted
backend Release environment:

```sh
python -m scripts.provision_beta_release_actor \
  --company-id "$ACP_BETA_COMPANY_ID" \
  --minutes 60
```

This writes only `/run/secrets/release_actor_token` (mode `0600`) and emits
non-secret IDs, expiry, and that reference. Re-running rotates the actor session
and invalidates prior actor tokens. The actor has exactly
`PLATFORM_ACCEPTANCE_PRINCIPAL_MANAGE`: no business permission, branch access,
refresh token, password login, or password-recovery path.

Run inside the deployed backend container after the schema is at the protected
head. Supply the Release actor credential through the process environment; never
place it or the resulting reader token on the command line.

```sh
install -d -m 0700 /run/acp-release/acceptance-reader
ACP_RELEASE_ACTOR_TOKEN_FILE=/run/secrets/release_actor_token
export ACP_RELEASE_ACTOR_TOKEN="$(<"$ACP_RELEASE_ACTOR_TOKEN_FILE")"
python -m scripts.provision_acceptance_readonly_principal \
  --company-id "$ACP_BETA_COMPANY_ID" \
  --minutes 60 \
  --token-output /run/acp-release/acceptance-reader/access-token
unset ACP_RELEASE_ACTOR_TOKEN
```

The directory is mode `0700` and the token file is mode `0600`. Handoff consists
of the protected filesystem reference plus the returned principal/session metadata,
never the token value. Acceptance tooling reads the file at request time and must
not copy it to logs, chat, source control, or browser storage.

## Revocation

```sh
export ACP_RELEASE_ACTOR_TOKEN="$(</run/secrets/release_actor_token)"
python -m scripts.revoke_acceptance_readonly_principal \
  --company-id "$ACP_BETA_COMPANY_ID" \
  --principal-id "$ACP_ACCEPTANCE_PRINCIPAL_ID"
unset ACP_RELEASE_ACTOR_TOKEN
```

Revocation disables the service User, advances authorization and credential
versions, revokes every active session, and writes an audit record. Deleting the
token file is an additional custody cleanup step, not a substitute for revocation.

No Production principal is authorized by this procedure.

Release can invalidate the actor and all of its sessions with:

```sh
python -m scripts.revoke_beta_release_actor \
  --company-id "$ACP_BETA_COMPANY_ID"
```
