# Platform Bootstrap

## Purpose

Platform Bootstrap provides the one-time, explicit initialization boundary for a brand-new ACP Enterprise database. It creates the minimum tenant, identity, and authorization graph required for the first administrator to authenticate and operate the installation. Bootstrap is not an HTTP endpoint, does not run during application startup, and is not a general seed-data system.

## Lifecycle

Bootstrap has two terminal outcomes:

- **Initialized:** the database contained no Company, and one complete initial platform graph was committed.
- **Already initialized:** at least one Company existed after acquiring the initialization lock, so the command committed no changes and returned successfully.

The presence of any Company is the initialization boundary. Operators must not use bootstrap to repair or add tenants to an existing installation. Tenant administration belongs to authenticated Platform services.

## Execution flow

```text
Environment variables
→ BootstrapConfiguration validation
→ Password policy validation
→ BootstrapService transaction
→ BootstrapRepository PostgreSQL advisory transaction lock
→ initialized-state check
→ Company and primary Branch
→ active Administrator User and Argon2id UserCredential
→ active all-branch Membership
→ centralized Permission catalog
→ system Roles
→ administrator Permission and Role assignments
→ atomic commit
```

`BootstrapService` owns orchestration and the transaction. `BootstrapRepository` owns database locking, initialization detection, model construction, and persistence. Password hashing is delegated to the established `PasswordService`. Permission definitions come exclusively from the validated centralized Permission catalog.

The PostgreSQL transaction advisory lock serializes bootstrap attempts across processes and hosts. A concurrent caller waits for the first transaction, then observes the committed Company and exits without writing. Any exception rolls back the entire graph and releases the lock automatically.

## Created reference data

Bootstrap persists every active definition in the centralized Permission catalog and creates two protected company system Roles:

- `COMPANY_ADMINISTRATOR` receives every currently registered company Permission and is assigned to the initial Membership.
- `COMPANY_USER` is a baseline system Role with no implicit Permission. Administrators may assign approved Permissions through company administration before assigning the Role.

Empty Role assignments and empty Permission assignments continue to grant nothing. The initial Membership receives explicit `has_all_branch_access=true`; its default Branch does not independently grant access.

## Configuration contract

The explicit command reads these required environment variables only when invoked:

```text
BOOTSTRAP_COMPANY_NAME
BOOTSTRAP_COMPANY_CODE
BOOTSTRAP_COMPANY_TIMEZONE
BOOTSTRAP_BRANCH_NAME
BOOTSTRAP_BRANCH_CODE
BOOTSTRAP_ADMINISTRATOR_EMAIL
BOOTSTRAP_ADMINISTRATOR_FIRST_NAME
BOOTSTRAP_ADMINISTRATOR_LAST_NAME
BOOTSTRAP_ADMINISTRATOR_PASSWORD
```

`BOOTSTRAP_ADMINISTRATOR_DISPLAY_NAME` is optional and defaults to the normalized first and last name. Company and Branch codes are trimmed and uppercased. Email is trimmed, lowercased, and validated. The password must pass the active centralized password policy.

Do not place bootstrap credentials in repository files, Compose files, shell history, tickets, logs, or chat. Use an approved secret-delivery mechanism, export variables into the operator's process, invoke the command with variable names rather than literal values, and unset them immediately afterward.

## Operational runbook

1. Confirm the target is a new environment and the migration state is at Alembic head.
2. Confirm the database contains no business data. Do not infer emptiness solely from a missing login.
3. Load the required `BOOTSTRAP_` variables through the approved secret-delivery process.
4. Execute exactly once from the backend runtime environment:

   ```bash
   python -m app.platform.bootstrap
   ```

5. A successful first run prints only:

   ```text
   ACP Enterprise bootstrap completed successfully.
   ```

6. A safe repeated run prints only:

   ```text
   ACP Enterprise is already initialized; no changes were made.
   ```

7. Unset all bootstrap variables.
8. Authenticate through the standard login service and verify the Company, Branch, Membership, Role, Permission, and Branch scope.

For Docker Compose, inject already-exported variables by name rather than placing values on the command line:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml run --rm \
  -e BOOTSTRAP_COMPANY_NAME \
  -e BOOTSTRAP_COMPANY_CODE \
  -e BOOTSTRAP_COMPANY_TIMEZONE \
  -e BOOTSTRAP_BRANCH_NAME \
  -e BOOTSTRAP_BRANCH_CODE \
  -e BOOTSTRAP_ADMINISTRATOR_EMAIL \
  -e BOOTSTRAP_ADMINISTRATOR_FIRST_NAME \
  -e BOOTSTRAP_ADMINISTRATOR_LAST_NAME \
  -e BOOTSTRAP_ADMINISTRATOR_DISPLAY_NAME \
  -e BOOTSTRAP_ADMINISTRATOR_PASSWORD \
  backend python -m app.platform.bootstrap
```

Do not add this command to container startup. Bootstrap always requires an intentional operator action.

## Failure and recovery

Configuration or password-policy failures occur before persistence. Database failures roll back all records. After a failed attempt:

1. Preserve the error and database logs without recording environment values.
2. Verify whether any Company exists using an approved administrative inspection path.
3. If no Company exists, correct the cause and rerun the same command.
4. If a Company exists, do not rerun bootstrap as a repair tool. Investigate the committed state and use an approved forward repair procedure.

Never manually delete partially suspected records, downgrade migrations, or reset a database without a reviewed recovery plan and backup.

## Security considerations

- Plaintext passwords exist only in process memory long enough for policy validation and Argon2id hashing.
- Only the encoded Argon2id hash is persisted.
- Secrets are never included in command output or application logs.
- The administrator is active and email-verified because bootstrap is an operator-controlled proofing ceremony, not a public invitation flow.
- Permissions come from the validated catalog; no implicit administrator bypass or role-name authorization is introduced.
- All authorization remains Membership- and Company-scoped.
- The initial administrator receives all Branch access explicitly, not through default-Branch inference.
- Advisory locking and a single database transaction prevent concurrent partial initialization.

## Non-goals

Bootstrap does not create demo customers, operational records, employees, additional users, production secrets, API keys, OAuth clients, or sample Business Events. It does not synchronize an existing Permission catalog or create additional Companies. Those operations belong to their established authenticated services and future deployment tooling.
