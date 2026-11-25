# Immutable CI application and tooling artifacts

The `Immutable CI artifacts` workflow qualifies one exact Git commit and emits
two deterministic archives plus `enterprise-ci-artifacts/v1` evidence. It has
read-only repository permission and contains no deployment job or credentials.

The application archive contains the committed backend application and Alembic
sources, frontend and mobile sources, their locked runtime dependencies, and
their build definitions. The tooling archive contains committed release,
qualification, migration, and Development Factory tooling. Both archives are
created with `git archive` from the full candidate SHA and gzip `mtime=0`, so a
dirty runner workspace cannot change their contents.

The evidence manifest binds:

- the exact candidate commit and Git tree;
- SHA-256 and byte size for both archives;
- every archived source-path definition;
- backend, frontend, and mobile dependency-file digests; and
- Docker and Compose configuration-file digests.

The workflow independently rebuilds both archives and requires the rebuilt
digests to match before upload. GitHub actions are pinned to full commit SHAs,
artifact names include the full candidate SHA, upload recompression is disabled,
and missing artifacts fail the job. CI evidence always records
`deployment_authorized: false`.

## Local generation and verification

Use a new private output directory. Existing artifacts are never overwritten:

```bash
candidate_sha="$(git rev-parse HEAD)"
artifact_dir="$(mktemp -d)/twelvehats-artifacts"
chmod 700 "$artifact_dir"
scripts/ci-artifacts build \
  --candidate-sha "$candidate_sha" \
  --output-directory "$artifact_dir"
scripts/ci-artifacts verify \
  --candidate-sha "$candidate_sha" \
  --manifest "$artifact_dir/ci-artifact-manifest.json"
```

An independent release lane can use the verified application and tooling
archive paths as the corresponding inputs to `scripts/release-manifest`. The
release manifest remains responsible for binding migration, backup, and
rollback artifacts. Neither CI artifact generation nor verification signs,
approves, merges, or deploys a release.
