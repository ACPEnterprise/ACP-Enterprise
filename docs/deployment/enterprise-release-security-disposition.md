# Enterprise Release Security Disposition — d5148f60

This packet is a worker analysis, not security-risk acceptance and not deployment
authority. The frozen candidate is `d5148f60ba842f9b4e7c9e83f16d1d3301372491` on
`origin/customer-management-v1`.

## Baseline and decision

The fetched protected branch equaled the supplied candidate during inspection.
The isolated worker worktree started clean. The migration lineage independently
reproduced 178 revisions, one root, one head (`o1q9s27h4u0v`), no lineage risks,
and digest `9436cd69cd5a6d7603d339013f98af5db6eb69820abbaa819f6396610c391e8e`.

The controlled-production engineering security gate is **BLOCKED**. The
machine-readable matrix is
`docs/deployment/enterprise-release-security-disposition-d5148f60.json`.
Installed versions cannot be truthfully reported because neither the sealed
scanner inventory nor `/opt/acp-enterprise/artifact-builds/d5148f60...` exists
on this worker. The verifier deliberately treats both omissions as blockers.
Three Expat findings also require sealed-image linkage/version evidence and a
proof that no externally controlled XML reaches Python `pyexpat` or another
Expat consumer. No worker may convert these blockers into acceptance.

## Runtime minimization result

The production compose contract already applies a read-only root filesystem,
`tmpfs` for `/tmp`, `cap_drop: ALL`, `no-new-privileges`, resource limits,
internal networking, and read-only secret/evidence mounts. These materially
constrain the local filesystem, privilege, mount, and container-impact paths.

No ACP source invocation was found for curl/libcurl, `infocmp`, systemd-homed,
ACL mutation tools, `nsenter`/mount helpers, Perl, or Archive::Tar. Those tools
are candidates for removal only after an ELF/package dependency scan of the
sealed image. Git is explicitly installed and is invoked by ACP execution-node,
workspace, repository-operation, and guarded migration code; removing it would
trade away functionality. The image currently has no Dockerfile `USER`, so
non-root conversion remains a desirable but separately qualified runtime
change. Secret-file modes, repository workspace ownership, and engineering
execution behavior must be proven before making it. A distroless switch was not
attempted, and the previously rejected Debian 12 fallback was not repeated.

## Enterprise verification

Run on the sanctioned artifact host without modifying the sealed directory:

```bash
install -d -m 700 /var/tmp/enterprise-release-security-d5148f60
scripts/enterprise-release-security-verify \
  --packet docs/deployment/enterprise-release-security-disposition-d5148f60.json \
  --artifact-root /opt/acp-enterprise/artifact-builds/d5148f60ba842f9b4e7c9e83f16d1d3301372491 \
  --scanner-inventory /protected/path/backend-scan.json \
  --output /var/tmp/enterprise-release-security-d5148f60/verification.json
```

The artifact walk must locate the backend archive
`df627754...bf96174`, frontend archive `eeeee7e...3eb4b`, and release
manifest `ddce024...91a86`. Separately verify the Docker daemon reports the
backend and frontend image IDs exactly as recorded in the JSON packet; an
archive file digest is not proof of a daemon image ID. Reconcile every scanner
occurrence to package name, installed version, file/layer, CVE and fixed-version
status. Then run an ELF dependency inventory and Python `pyexpat` runtime probe
inside the sealed backend image. Any mismatch is `FAIL`; missing evidence is
`BLOCKED`.

Run the existing qualification profiles against the frozen SHA:

```bash
scripts/enterprise-release-qualify --profile local --execute \
  --candidate-sha d5148f60ba842f9b4e7c9e83f16d1d3301372491 \
  --evidence-dir /var/tmp/enterprise-release-d5148f60/local
scripts/enterprise-release-qualify --profile database --execute \
  --candidate-sha d5148f60ba842f9b4e7c9e83f16d1d3301372491 \
  --evidence-dir /var/tmp/enterprise-release-d5148f60/database
```

Preview and post-deployment profiles remain Enterprise-owned. They must bind the
candidate, image IDs, archive/manifest digests, migration evidence, backup and
verified restore receipt. Authentication, RBAC, health, PostgreSQL, Redis,
workers and routes must be run with sanctioned protected credentials. Do not
reuse All County business records for CRUD smoke tests.

## Required authority disposition

ENTERPRISE.RELEASE should keep the candidate frozen and the gate blocked until:

1. the scanner inventory supplies exact installed versions for all 54 package
   occurrences and the verifier evidence is complete;
2. sealed artifact and daemon-image digests all match;
3. Expat linkage/reachability is disproved or a fixed image successor is built
   and fully requalified;
4. removal feasibility is proven for unused OS tools without removing Git or
   another required transitive library; and
5. a named security authority explicitly accepts or rejects the remaining
   residual risk. This worker does not grant that acceptance.
