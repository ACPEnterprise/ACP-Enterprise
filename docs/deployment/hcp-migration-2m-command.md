# HCP.MIGRATION.2 sanctioned command

The repository-owned executable boundary is:

```text
python -m app.operational_migration.hcp_migration2_command MODE --authority-file /protected/path/hcp-migration-2-authority.json
```

`MODE` is `qualify`, `execute`, or `replay`. `execute` and `replay` additionally require `--authorize-execution`. Qualification is read-only. Execution invokes `HcpMigration2Application.execute()` exactly once; replay uses the same call and the application's completed-master path.

The authority JSON must be stored outside Git with mode `0600`. It contains only protected path references and sealed IDs/digests: repository SHA, SOURCE.4/package and owner-evidence paths, master/original-plan/repair/sequence/checkpoint authorities, Financial successor authority, Company, Branch, actor, builder version, and expected Alembic head. Never place source rows, credentials, tokens, customer data, or financial payloads in this file or on the command line.

The process environment must supply the isolated loopback `DATABASE_URL`, `TARGET_ENVIRONMENT=migration_rehearsal`, `PRODUCTION_ACCESS_ENABLED=false`, and `PREVIEW_ACCESS_ENABLED=false`. The command rejects other hosts, databases, environments, schema heads, scopes, actors, authority digests, unsafe authority-file permissions, and credentialed actor substitution.

Run `qualify` first and retain its safe JSON summary for owner review. Run `execute --authorize-execution` only after explicit owner authorization. After successful completion, run `replay --authorize-execution`; it verifies the completed authority without reapplying persistence. A nonzero exit with a safe error code is fail-closed: preserve the target and escalate rather than constructing a manual fallback.
