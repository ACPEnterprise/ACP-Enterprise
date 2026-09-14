# OM2-C persona contract authority — OM1 Phone handoff

Authoritative machine contract:
`backend/operations/preview-persona-contract-authority.v1.json` at protected authority
`e1015aada1daa5abf33bfa6968cd1eb1fe5da298`.

OM1 Phone must consume this file without translating role labels into authority. The
four persona permission arrays are exact. QBO_READ is safely represented by the
existing `COMPANY_ACCOUNTING_REPORT_READ` permission used by
`GET /api/v1/accounting/source-evidence/qbo`; it has no OAuth administration,
Accounting mutation, or money-movement permission.

The only accepted fixture tenant is Company
`31ba6867-2d8a-55dd-9e34-d67c684ee41c`, Branch
`95bf7a14-09b0-51b6-b3cb-7946523ec093`, version
`preview.synthetic.tenant.v1`. The repository-supported tenant command is
`backend/scripts/preview_synthetic_tenant_fixture.py`; it reads the authorizing token
from stdin and is Enterprise-only. Identity provisioning, session issuance, revocation,
and reset remain the existing service interfaces named in the machine contract.

For each run, Enterprise creates
`/run/secrets/acp-preview-acceptance/v1/<run-id>/<consumer-id>/` mode `0700`, with
`access-token` and `attestation.json` mode `0600`. The token content never appears in
the handoff, attestation, logs, evidence, or command arguments. The attestation schema
is `backend/operations/preview-acceptance-attestation.v1.schema.json`; the companion
example is deliberately expired, contains zero placeholders, and is never executable.

Mutation authority defaults empty. EMPLOYEE, OFFICE, and QBO_READ have an empty
maximum. CSR's sole possible route is
`/api/v1/operations/jobs/{job_id}/schedule`; it remains unavailable unless Enterprise
places that exact route in the sealed attestation for synthetic fixture records.

OM2-C consumes the references with the existing command:

```text
python backend/scripts/authenticated_preview_acceptance.py \
  --persona <csr|employee|office|qbo> \
  --token-file /run/secrets/acp-preview-acceptance/v1/<run-id>/<consumer-id>/access-token \
  --attestation-file /run/secrets/acp-preview-acceptance/v1/<run-id>/<consumer-id>/attestation.json
```

The consumer remains GET-only. It verifies exact permissions and their digest,
Company/Branch, fixture version and references, protected/deployed SHA bindings,
schema head, frontend digest, session and attestation expiry, and mutation allowlist.
No persona, session, token, fixture, or Preview mutation was created by OM2-C.
