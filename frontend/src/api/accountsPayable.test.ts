import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { createAccountingVendor, getAPAging } from "./accountsPayable";

vi.mock("./client", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
describe("accounts payable API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("requests immutable aging inputs at an explicit cutoff", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] });
    await getAPAging("2026-08-26");
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/accounts-payable/aging", { params: { as_of: "2026-08-26" } });
  });
  it("creates accounting vendor identity without sensitive fields", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "v" } });
    const input = { code: "V001", legal_name: "Vendor", display_name: "Vendor", provenance: "manual" };
    await createAccountingVendor(input);
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/accounts-payable/vendors", input);
  });
});
