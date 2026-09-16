# Twelve Hats Beta recovery automation 1 — Enterprise Release handoff

## Candidate

- Starting protected authority: `a3006bd2f72910cc0895ecc5ba85d5d04f33a806`
- Scope: non-destructive Beta/Preview host admission and restricted PostgreSQL backup
  automation.
- Schema impact: none.
- Preview/Production deployment performed: no.

## Live evidence

- Root disk is 81% utilized with approximately 16 GiB free.
- Docker reports 1.633 GiB of stopped-container data and 8.583 GiB of build cache as
  reclaimable. No cleanup was performed because the host contains many explicitly
  named rollback/evidence containers that require classification before deletion.
- Numerous mode-0600 database dumps exist; the newest observed dump was created at
  2026-09-16 22:43 UTC.
- No ACP database-backup systemd timer exists. Backup freshness therefore depends on
  deployments or a human remembering to create one.
- No failed systemd units were present during the sweep.
- The new host audit fails closed on the live host, correctly identifying Mission
  Control API/web and Phone7 API as unhealthy or restart-looping.
- Caddy logs show multiple authenticated workers repeatedly receiving 502 from the
  broken Preview worker-transport upstream. PR #392 is the bounded coherent Mission
  Control runtime repair; do not silence those errors or redirect workers to Beta.

## Backup behavior

`scripts/backup-preview-postgres.sh`:

- targets the exact existing Preview PostgreSQL container by its explicit protected
  runtime identity and verifies that it is running before acquisition;
- creates a custom-format dump under a mode-0700 directory with umask 0077;
- writes to a unique temporary file;
- rejects an empty dump;
- runs `pg_restore --list` before publication;
- publishes the dump and SHA-256 sidecar atomically at mode 0600;
- performs no retention deletion.

The daily systemd templates retain journald success/failure evidence. They provide
same-host recoverability, not disaster recovery. Enterprise still needs encrypted
off-host replication, a named alert recipient and a scheduled isolated restore
rehearsal.

## Host admission behavior

`scripts/audit-beta-runtime-host.sh` fails closed when:

- Caddy is inactive;
- root disk reaches 90% (warning begins at 85%);
- any running container is unhealthy or restarting;
- no database dump exists, the newest is older than 26 hours, or its mode is not 0600;
- public Preview/Beta connectivity fails.

The audit intentionally reports rather than deletes reclaimable Docker state.

## Enterprise Release actions

1. Integrate and deploy PR #392's coherent Mission Control profile first.
2. Classify Phone7 API as active or superseded; repair its secret through the approved
   boundary or retire it while preserving evidence.
3. Run the host audit and require a passing result before marking Beta runtime healthy.
4. Install, review and enable the backup timer; run one backup manually and record its
   checksum and `pg_restore --list` result.
5. Copy the backup to encrypted off-host storage and rehearse an isolated restore.
6. Inventory stopped containers/images by release and evidence purpose before any
   targeted cleanup. Never run an unreviewed global prune.

## Qualification

- Recovery automation and existing platform contracts: 12 tests passed.
- Shell syntax, Ruff, formatting and diff checks: passed.
- Live host audit: failed as designed on the three known unhealthy/restarting
  containers.
- No backup, cleanup, restart, container removal or Production action was performed.
