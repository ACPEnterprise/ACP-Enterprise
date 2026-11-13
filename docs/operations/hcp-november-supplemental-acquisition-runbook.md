# HCP November supplemental acquisition — exact missing identities

This procedure is GET-only and is prepared for the 1,013 identities in the
private inventory. It never calls an HCP mutation endpoint, changes provider
status, freezes work, or writes ACP, QBO, Payroll, or Production.

## Required protected inputs

- Inventory: `/opt/acp-enterprise/shared/hcp-admission/missing-payload-inventory.json`
- Inventory SHA-256:
  `2aa00cc12a35c828bbdbdadb3b0fa5d8361253c7f424da314830f96fed42bc51`
- Source packet SHA-256:
  `8d2b9c056f5eeaaf5b0eb96431c9ccd9906a6db89094bc677ef8a115136fd8a4`
- Source canonical digest:
  `dfa44599b3bfaf604f16a3117d5925eff8ec6fc25f5e0a35a0e4e64a3459bdb3`
- A mode-0600 secret file containing only `HOUSECALL_PRO_API_KEY` and
  `HOUSECALL_PRO_API_BASE=https://api.housecallpro.com`.

The secret must be supplied by the authorized original HCP acquisition worker
or OM1C owner. Do not place it in Git, chat, the Beta application `.env`, or a
receipt.

## Exact GET-only acquisition

Run on the authorized acquisition worker, with the private inventory copied
read-only from the sealed handoff:

```bash
umask 077
PYTHONPATH=/opt/acp-enterprise/builder/backend \
  /opt/acp-enterprise/builder/backend/.venv/bin/python \
  /opt/acp-enterprise/builder/backend/scripts/hcp_november_missing_payload_supplement.py \
  --secret-file /protected/hcp/hcp-get-only.env \
  --inventory /protected/hcp/missing-payload-inventory.json \
  --inventory-sha256 2aa00cc12a35c828bbdbdadb3b0fa5d8361253c7f424da314830f96fed42bc51 \
  --output-root /protected/hcp/november-supplemental \
  --source-packet-sha256 8d2b9c056f5eeaaf5b0eb96431c9ccd9906a6db89094bc677ef8a115136fd8a4 \
  --source-canonical-digest dfa44599b3bfaf604f16a3117d5925eff8ec6fc25f5e0a35a0e4e64a3459bdb3
```

The command fetches only `/employees/{id}`, `/estimates/{id}`, and
`/invoices/{id}` for identities in the inventory. It validates every returned
provider ID and source digest before writing. Raw responses are retained under
`raw/`; normalized records are written under the exact `acquisition/...json`
locators. The custody manifest and receipt are mode 0600.

## Stage on clean Beta

Copy the sealed supplemental directory to the new Beta only, preserving its
protected ownership and modes:

```bash
scp -i ~/.ssh/acp_beta_clean_ed25519 -r /protected/hcp/november-supplemental \
  root@162.243.232.59:/opt/acp-enterprise/shared/hcp-admission/
```

Verify the supplemental receipt and manifest digests without printing source
bodies. Merge the supplemental `acquisition/` directory into the private
evidence root only after conflict-free digest verification; never overwrite an
existing sealed artifact.

## Final preflight, then owner gate

Rebuild the current-SHA execution envelope, run source qualification, adapter
qualification, payload materialization, and the full PostgreSQL dry run. The
expected result is 5,191/5,191 payloads resolved, zero missing/ambiguous
identities, zero lineage gaps, zero held-parent edges, first-run projected
actions of 511 `CREATE_NATIVE`, 823 `BOOTSTRAP_CREATE_FROM_UPDATE`, and 3,857
`BOOTSTRAP_CREATE_FROM_REPLAY`, followed by 5,191 `REPLAY_NOOP` actions on an
identical second run.

Only after that evidence is reviewed may the owner authorize the existing
bounded command with `--authorize-execution`. This runbook does not authorize
that command.
