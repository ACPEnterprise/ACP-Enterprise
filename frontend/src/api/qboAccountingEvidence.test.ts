import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { getQboAccountingEvidence } from "./qboAccountingEvidence";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("QBO accounting source evidence API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requests read-only evidence with an explicit accounting basis", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        contract_version: "qbo-accounting-evidence/v1", source: "quickbooks_online",
        mode: "blocked", provider_environment: "production", company_identity_sha256: null,
        company_info_verified_at: null, source_manifest_sha256: null,
        source_company_label: "Real company not verified", source_company_id_masked: "unavailable",
        provider_authorization: "unverified", evidence_mode: "unavailable", completeness: "unavailable",
        entity_counts: {}, page_counts: {}, catalog_dispositions: [], accounting_basis: "cash",
        as_of: null, acquired_at: null, refresh_state: "unavailable", snapshot_id: null,
        snapshot_digest: null, is_live: false, limitations: [], accounts: [], invoices: [], bills: [],
        ar: { total_open: { amount: null, currency: null, state: "unavailable" }, current: { amount: null, currency: null, state: "unavailable" }, overdue: { amount: null, currency: null, state: "unavailable" } },
        payments: [], reports: [], conflicts: [], mutation_authority: "none",
      },
    });
    await getQboAccountingEvidence("cash");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/accounting/source-evidence/qbo",
      { params: { basis: "cash" } },
    );
  });

  it("rejects a substituted accounting basis", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { accounting_basis: "accrual" } });
    await expect(getQboAccountingEvidence("cash")).rejects.toThrow(/authority is invalid/i);
  });
});
