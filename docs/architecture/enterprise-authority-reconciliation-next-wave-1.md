# Enterprise authority reconciliation — next wave 1

Reviewed authority: `origin/customer-management-v1@23dea55713e09c97fbbb8a92fa28c8dc3159b39b`.

## Durable dispositions

- `BANK.ASSET.001` remains owner-blocked. No accepted native operational Asset/Fleet identity and mutation boundary or maintenance policy exists. An old operations worktree is not current ownership. `BANK.ASSET.002`–`.009` remain dependency-blocked.
- `BANK.JOB.001` remains owner-blocked; `BANK.JOB.002`–`.007` remain dependency-blocked. Current Jobs has launch lifecycle, cancellation/reopen reasons, generic completion guards, and appointment composition, but does not prove the exact BANK exception/hold, prerequisite, multi-visit continuity, financial-cancellation, reschedule-audit, completion-policy, and warranty/callback-linkage sequence.
- The qualified Customer 360 and scoped communication-history capability is authoritative through PR #94. It explicitly excludes native consolidation and survivorship, so `BANK.CRM.001` remains owner-blocked.
- The qualified read-only Workforce operations and eligibility workspace is authoritative through PR #95. `BANK.WF.001` still requires accepted mutation/admin and labor/Payroll-handoff authority and remains owner-blocked.
- `SERVICE_CSR` and `OWN_DATA_ROLE` definitions and fresh-tenant bootstrap provisioning are authoritative. Existing-tenant reconciliation is the distinct `PLATFORM.CANONICAL.ROLE.SYNC.1` boundary.
- LIA has a declared `get_customer_operational_context` tool contract, but no Customer-owned minimum-necessary projection implementation. Laptop1-A owns a bounded Customer-domain projection returning only scoped identity/status, safe contact/readiness summary, active Service Location references, and explicit evidence/version metadata; unrestricted Customer ORM access is prohibited.
- `BANK.ECO.007` is actively owned by ECO/Laptop1-B on `work/eco-overhead-allocation-evidence-completion-1`. The bounded engineering contract may define versioned pools/policies, admitted source/basis evidence, deterministic allocation, provenance, and fail-closed readiness. Real Company allocation values remain unconfigured owner/Finance policy and must not be invented.

## Next-wave ownership

| Lane | Boundary |
| --- | --- |
| OM2-A | Operational Assets/Fleet only after the owner approves the identity/mutation and maintenance-policy boundary. |
| OM2-B | `PLATFORM.CANONICAL.ROLE.SYNC.1`: idempotent existing-tenant synchronization for accepted canonical roles; no role expansion. |
| Laptop1-A | Customer-owned minimum-necessary LIA context projection and adapter; read-only and Company/Branch scoped. |
| Laptop1-B / ECO | `BANK.ECO.007` engineering authority/readiness without Company policy-value fabrication. |
| OM2-C | Quality, security, migration integrity, and release qualification only; no domain redesign. |

Current authority ownership is recorded separately from BANK.2's historical planning ownership. Absence of current ownership never resolves a product, owner, Finance, external, dependency, or identity-reconciliation gate.
