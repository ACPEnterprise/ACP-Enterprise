# OM2-A HCP source completeness tooling

This assignment adds an executable, fail-closed missing-payload inventory
generator for Laptop Master to run against the sealed current-schema packet and
its protected evidence root. The inventory retains provider Company binding,
source packet digest, provider identity, payload locator, source digest, and
parent relationships.

Only missing Employee, Estimate, and Invoice bodies are classified as eligible
for the existing scoped GET-only supplemental retriever. Other absent domains or
incomplete locators remain explicitly unsupported; the tool does not infer an
endpoint, relationship, or source body. Held/non-executable records remain held
and are not silently converted into retrieval work.

```bash
umask 077
cd backend
PYTHONPATH=. python scripts/build_hcp_missing_payload_inventory.py \
  --packet /protected/hcp/current-schema-packet.json \
  --evidence-root /protected/hcp/evidence \
  --output /protected/hcp/missing-payload-inventory.json
```

The output is mode 0600 and is refused if already present. Qualification uses
synthetic records only. OM2-A did not possess the protected 7,293-record packet,
the 621 media bodies, provider credentials, or provider Company proof, so no
actual All County retrieval or protected acceptance is claimed.
