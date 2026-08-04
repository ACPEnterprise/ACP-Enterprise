# Trusted Engineering Node Execution Provider

The controlled execution provider runs only on an enrolled office engineering node. Preview never receives Codex credentials or a writable repository mount.

The node runs two separate processes:

1. the authenticated ACP worker transport agent receives immutable offers and leases;
2. the provider service listens on loopback, authenticates the local agent with a mode `0600` HMAC secret, and exclusively owns writable workspaces and Git authority.

Required protected configuration:

- `ACP_PROVIDER_TOKEN_FILE`: local agent/provider HMAC secret, mode `0600`;
- `ACP_PROVIDER_REPOSITORIES_FILE`: repository-key to trusted local checkout mapping;
- `ACP_PROVIDER_WORKSPACE_ROOT`: provider-only workspace root;
- `ACP_PROVIDER_STATE_ROOT`: provider-only durable journal;
- `ACP_PROVIDER_CODEX_EXECUTABLE`: pinned Codex executable;
- `ACP_PROVIDER_CODEX_HOME`: existing protected node-local Codex credential directory;
- `ACP_PROVIDER_EVIDENCE_ROOT`: bounded non-repository evidence directory.

Bind the provider to `127.0.0.1` only. Do not expose it through Caddy, Preview, or the public network. Enroll and revoke its associated worker/node identity through Engineering administration. Revocation fails closed at offer and result validation.

Every request is bound to Company, node, command, execution, lease, repository, branch, expected HEAD, allowed and forbidden paths, permitted operations, validation requirements, and immutable digests. Interrupted mutation phases become `reconciliation_required`; they are never automatically re-executed.
