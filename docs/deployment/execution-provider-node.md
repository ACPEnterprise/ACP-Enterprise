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

## Unattended non-production publication

An owner Start for a code-changing READY milestone grants the provider the bounded
`modify`, `validate`, `commit`, `mechanical_reconcile`, and normal `push`
operations recorded in the immutable execution boundary. It never grants deploy,
Production, import, cutover, migration execution, force-push, or conflict-resolution
authority.

The worker observes the provider's authenticated, append-only journal and publishes
monotonic workstream progress to Mission Control. The provider stages only the
approved file boundary, creates one controlled commit, fetches the authoritative
branch, and pushes normally. If origin advanced, automatic reconciliation is limited
to a disjoint fast-forward descendant with no migration or shared control-plane
files. Overlap, migration ancestry, shared security/control-plane changes, divergent
history, or a push race produces `reconciliation_required` and preserves the local
commit for review. Force-push is never used.

The terminal controlled result records the starting head, prior remote head,
published commit SHA, whether a mechanical rebase occurred, validation evidence,
and the exact file boundary. Mobile Roadmap progression uses that published SHA as
the next authoritative repository head before exposing subsequent work.
