import { createQboEvidenceService } from "../src/api/qboEvidence";
import type { ApiClient } from "../src/api/client";
import { capabilitiesFromPermissions } from "../src/permissions/capabilities";

describe("read-only owner cash evidence", () => {
  it("uses the canonical cash-basis source evidence route", async () => {
    const request = jest.fn().mockResolvedValue({ contract_version: "qbo.v1", source: "quickbooks_online", mode: "blocked", provider_environment: "historical_control", company_identity_sha256: null, company_info_verified_at: null, source_manifest_sha256: null, completeness: "unavailable", accounting_basis: "cash", as_of: null, acquired_at: null, refresh_state: "unavailable", snapshot_id: null, snapshot_digest: null, limitations: [], accounts: [], invoices: [], bills: [], ar: {}, payments: [], reports: [], conflicts: [], mutation_authority: "none" });
    await createQboEvidenceService({ request } as unknown as ApiClient).cash();
    expect(request).toHaveBeenCalledWith("/api/v1/accounting/source-evidence/qbo?basis=cash", expect.anything());
  });

  it("gates the surface behind the existing accounting report permission", () => {
    expect(capabilitiesFromPermissions(["COMPANY_ACCOUNTING_REPORT_READ"])).toContain("accounting.read");
    expect(capabilitiesFromPermissions(["COMPANY_JOB_READ"])).not.toContain("accounting.read");
  });
});
