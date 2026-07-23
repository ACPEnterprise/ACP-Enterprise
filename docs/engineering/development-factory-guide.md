# Development Factory Operating Guide

The Development Factory checks work and writes reports. It does not change
source files, stage changes, commit, push, merge, or deploy.

Run commands from the repository root.

## Commands

Full validation:

```sh
./scripts/development-factory validate
```

Backend only:

```sh
./scripts/development-factory validate --backend
```

Frontend only:

```sh
./scripts/development-factory validate --frontend
```

Safe disposable-database migration validation:

```sh
./scripts/development-factory validate --migrations
```

Architecture and security policies:

```sh
./scripts/development-factory validate --architecture
```

Select checks based on currently changed files:

```sh
./scripts/development-factory validate --changed
```

Print the latest Markdown report:

```sh
./scripts/development-factory report
```

Reports are stored locally at:

```text
.development-factory/latest.json
.development-factory/latest.md
```

This directory is ignored by Git.

## Understanding results

- `passed`: the check ran and succeeded.
- `failed`: the check ran and found a problem.
- `skipped`: your explicit selection did not request the check.
- `unavailable`: a required program or safe dependency was missing.
- `blocked`: an earlier required failure prevented safe execution.
- `not_applicable`: the check does not apply to this repository state.

Skipped and unavailable checks are never called passed. A required failure or
unavailable dependency blocks owner-review readiness.

Docker and the local ACP backend/PostgreSQL containers are required for backend
tests and migration validation. Node/npm dependencies are required for
frontend checks. Migration validation creates a uniquely named disposable
database, removes it afterward, and fails if removal cannot be confirmed.

The tool may report warnings from heuristic architecture or security scans.
Open the Markdown report for file and line references. Warnings require human
judgment; do not change product architecture mechanically to silence them.
