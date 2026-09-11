import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import {
  getQboAccountingEvidence,
  validateQboAccountingEvidence,
  type QboAccountingEvidenceWorkspace,
} from "./qboAccountingEvidence";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("QBO accounting source evidence API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requests read-only evidence with an explicit accounting basis", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: packet() });
    await getQboAccountingEvidence("cash");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/accounting/source-evidence/qbo",
      { params: { basis: "cash" } },
    );
  });

  const packet = (): QboAccountingEvidenceWorkspace => ({
    contract_version: "qbo-accounting-source-evidence/v1",
    source: "quickbooks_online",
    source_company_label: "Real company not verified",
    source_company_id_masked: "unavailable",
    provider_authorization: "unverified",
    evidence_mode: "unavailable",
    completeness: "unavailable",
    entity_counts: {},
    page_counts: {},
    catalog_dispositions: [],
    accounting_basis: "cash",
    as_of: null,
    acquired_at: null,
    refresh_state: "unavailable",
    snapshot_id: null,
    snapshot_digest: null,
    is_live: false,
    limitations: ["production_oauth_authority_unavailable"],
    accounts: [],
    invoices: [],
    bills: [],
    ar: {
      total_open: { amount: null, currency: null, state: "unavailable" },
      current: { amount: null, currency: null, state: "unavailable" },
      overdue: { amount: null, currency: null, state: "unavailable" },
    },
    payments: [],
    vendors: [],
    reports: [],
    conflicts: [],
    mutation_authority: "none",
  });

  it("fails closed on basis substitution or mutation authority", () => {
    expect(() => validateQboAccountingEvidence(packet(), "accrual")).toThrow(
      /authority is invalid/i,
    );
    expect(() =>
      validateQboAccountingEvidence(
        { ...packet(), mutation_authority: "write" as never },
        "cash",
      ),
    ).toThrow(/authority is invalid/i);
  });

  it("rejects unsealed live claims and inconsistent missing amounts", () => {
    expect(() =>
      validateQboAccountingEvidence(
        {
          ...packet(),
          provider_authorization: "verified_current",
          evidence_mode: "current_authorized_snapshot",
        },
        "cash",
      ),
    ).toThrow(/not verified and sealed/i);
    expect(() =>
      validateQboAccountingEvidence(
        {
          ...packet(),
          ar: {
            ...packet().ar,
            total_open: { amount: null, currency: "USD", state: "available" },
          },
        },
        "cash",
      ),
    ).toThrow(/availability is inconsistent/i);
  });
});
