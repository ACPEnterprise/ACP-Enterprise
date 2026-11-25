# Bounded failure-injection qualification

`development_factory.failure_injection` is a qualification adapter around the
existing queue, runtime, migration, and recovery checks. It is not a scheduler,
release authority, deployment mechanism, or protected-environment runner.

A complete report requires these five scenarios exactly once:

- authoritative queue discovery failure;
- application or dependency health-check failure;
- expired or unavailable credential failure;
- candidate migration failure; and
- partial execution requiring recovery from a clean checkpoint.

Each scenario must observe its expected failure. An action that unexpectedly
succeeds is a failed qualification, never a PASS. Recovery is explicit and is
retried no more than the scenario's bound (maximum five attempts). Exhaustion,
an unexpected exception type, absent recovery evidence, a missing or duplicated
scenario, or a failed scenario makes the consolidated report FAIL.

Reports use `development-factory.failure-injection-report/v1`, bind the exact
candidate SHA, are canonical-digest sealed, contain
`deployment_authorized: false`, and are written atomically with mode `0600` to
a private directory. Failure and recovery reasons pass through the existing
Development Factory redactor so credentials, URLs, bearer tokens, and private
keys cannot be persisted in evidence.

The permanent regressions use injected local exceptions and disposable state.
They do not access a network, issue Worker Control claims, load protected
credentials, mutate a shared database, or deploy.
