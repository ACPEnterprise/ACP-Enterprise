# Authenticated Live Worker Runtime

## Ownership

The runtime is a provider-neutral client of authenticated Worker Transport. It owns
only private-key possession, transport-session continuity, periodic heartbeats, and
explicit renewal of an already-authoritative Worker Control lease.

Worker Identity owns identity and credential lifecycle. Worker Transport owns
challenges, sessions, replay protection, message ordering, receipts, and the
authenticated inbound-message transaction. Worker Control owns durable workers,
heartbeats, capabilities, and leases. Engineering Control and Engineering Execution
remain the only owners of approval and execution state.

The runtime has no provider registry, provider client, execution method, offer
acceptance, repository access, shell, Git, Docker, queue, or deployment authority.

## Authentication

An operator provisions an Ed25519 key pair outside the runtime:

- the public key is stored as the existing immutable Worker Identity credential
  verifier with algorithm `ed25519`;
- the private key remains in an owner-readable file outside the repository;
- the runtime rejects a private-key file with group or world permissions.

`X-Worker-ID` locates public verification metadata for challenge creation but grants
no authority. The worker signs the one-time challenge, and the server derives
Company, orchestration Worker, provider identifier, identity, credential record, and
credential version from durable records.

After establishment, `X-Worker-Session-ID` is only a durable-session locator. The
server derives authority from that active session and revalidates its exact identity
credential on every operation. Each message signs a deterministic canonical envelope
containing its session, Worker, message identifier, sequence, timestamp, kind,
key version, and structured payload.

Revoked, rotated, expired, suspended, mismatched, or cross-Company credentials fail
closed before heartbeat or lease mutation. Altered payloads fail signature
verification. Existing transport sequence and receipt persistence provide replay and
duplicate protection transactionally.

## Runtime lifecycle

The local immutable runtime projection uses:

```text
stopped -> authenticating -> connected -> closed
                              |
                              +-> degraded -> closed
```

The durable source of truth remains the transport session and Worker heartbeat.
Engineering Control reports connected only for an active credential-bound session
with a heartbeat no older than the existing 90-second policy. Stopping the runtime
does not fabricate immediate disconnection; the projection becomes disconnected
when its authoritative heartbeat freshness rule is no longer satisfied.

Transport sessions retain the existing 15-minute bound. PHONE.5 adds a bounded
service reconnect loop and durable recovery journal; it never retries execution
when an acquired offer has an ambiguous outcome.

## Lease behavior

Lease acquisition remains exclusively in Worker Control and requires an eligible
Engineering Execution and immutable offer. This runtime can only submit an explicit,
signed renewal for a lease identifier and optimistic version already issued by
Worker Control. The server revalidates Company, Worker, session, credential, lease
ownership, expiry, and version inside the transport-owned message transaction.

No lease is created merely because a runtime connects.

## Deployment boundary

The runtime entry point is:

```text
python -m app.worker_runtime
```

It requires `ACP_WORKER_BASE_URL`, `ACP_WORKER_ID`, and
`ACP_WORKER_PRIVATE_KEY_FILE`; optional bounded heartbeat, timeout, and capability
configuration follows the names in `WorkerRuntimeConfig`.

Credential provisioning and the hardened worker Compose service are implemented by
PHONE.5. Provisioning remains an explicit permission-checked operation and runtime
startup never creates or displays credentials.
